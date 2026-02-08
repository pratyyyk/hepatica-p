from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from app.api.deps import RequestUser, assert_patient_owned_by_user, get_request_user
from app.core.config import Settings, get_settings
from app.core.enums import FibrosisStage
from app.core.rate_limit import limiter, user_or_ip_key
from app.db.models import ClinicalAssessment, FibrosisPrediction, ScanAsset
from app.db.session import get_db
from app.schemas.assessment import (
    ClinicalAssessmentCreate,
    ClinicalAssessmentRead,
    FibrosisAssessmentCreate,
    FibrosisAssessmentRead,
    TopPrediction,
)
from app.services.antivirus import run_antivirus_scan
from app.services.audit import write_audit_log
from app.services.dicom import maybe_convert_dicom
from app.services.fibrosis_inference import FibrosisModelRuntime, fetch_scan_bytes
from app.services.quality import evaluate_quality
from app.services.stage1 import run_stage1
from app.services.timeline import append_timeline_event

router = APIRouter(prefix="/assessments", tags=["assessments"])
settings = get_settings()


@router.post("/clinical", response_model=ClinicalAssessmentRead)
@limiter.limit(settings.rate_limit_mutating_per_ip, key_func=get_remote_address)
@limiter.limit(settings.rate_limit_mutating_per_user, key_func=user_or_ip_key)
def run_clinical_assessment(
    request: Request,
    response: Response,
    payload: ClinicalAssessmentCreate,
    db: Session = Depends(get_db),
    req_user: RequestUser = Depends(get_request_user),
):
    assert_patient_owned_by_user(db, payload.patient_id, req_user.db_user.id)

    result = run_stage1(
        age=payload.age,
        ast=payload.ast,
        alt=payload.alt,
        platelets=payload.platelets,
        ast_uln=payload.ast_uln,
        bmi=payload.bmi,
        type2dm=payload.type2dm,
    )

    row = ClinicalAssessment(
        patient_id=payload.patient_id,
        performed_by=req_user.db_user.id,
        ast=payload.ast,
        alt=payload.alt,
        platelets=payload.platelets,
        ast_uln=payload.ast_uln,
        age=payload.age,
        bmi=payload.bmi,
        type2dm=payload.type2dm,
        fib4=result.fib4,
        apri=result.apri,
        risk_tier=result.risk_tier.value,
        probability=result.probability,
        model_version=result.model_version,
    )
    db.add(row)
    db.flush()

    append_timeline_event(
        db,
        patient_id=payload.patient_id,
        event_type="CLINICAL_ASSESSMENT_COMPLETED",
        event_payload={
            "assessment_id": row.id,
            "risk_tier": row.risk_tier,
            "probability": row.probability,
        },
        created_by=req_user.db_user.id,
    )
    write_audit_log(
        db,
        user_id=req_user.db_user.id,
        action="CLINICAL_ASSESSMENT_CREATED",
        resource_type="clinical_assessment",
        resource_id=row.id,
        metadata={"risk_tier": row.risk_tier},
    )

    db.commit()
    db.refresh(row)
    return ClinicalAssessmentRead(
        id=row.id,
        patient_id=row.patient_id,
        fib4=row.fib4,
        apri=row.apri,
        risk_tier=row.risk_tier,
        probability=row.probability,
        model_version=row.model_version,
        created_at=row.created_at,
    )


@router.post("/fibrosis", response_model=FibrosisAssessmentRead)
@limiter.limit(settings.rate_limit_mutating_per_ip, key_func=get_remote_address)
@limiter.limit(settings.rate_limit_mutating_per_user, key_func=user_or_ip_key)
def run_fibrosis_assessment(
    request: Request,
    response: Response,
    payload: FibrosisAssessmentCreate,
    db: Session = Depends(get_db),
    req_user: RequestUser = Depends(get_request_user),
    cfg: Settings = Depends(get_settings),
):
    assert_patient_owned_by_user(db, payload.patient_id, req_user.db_user.id)

    scan_asset = db.get(ScanAsset, payload.scan_asset_id)
    if not scan_asset or scan_asset.patient_id != payload.patient_id:
        raise HTTPException(status_code=404, detail="Scan asset not found")

    try:
        image_bytes = fetch_scan_bytes(object_key=scan_asset.object_key, settings=cfg)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    av_ok, av_reason = run_antivirus_scan(image_bytes)
    if not av_ok:
        scan_asset.status = "SECURITY_REJECTED"
        db.commit()
        raise HTTPException(
            status_code=422,
            detail={"reason": "Antivirus scan failed", "code": av_reason},
        )

    try:
        image_bytes = maybe_convert_dicom(
            image_bytes=image_bytes,
            content_type=scan_asset.content_type,
        )
    except ValueError as exc:
        scan_asset.status = "FORMAT_REJECTED"
        db.commit()
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    quality = evaluate_quality(image_bytes)
    if not quality.is_valid:
        scan_asset.status = "QUALITY_REJECTED"
        db.commit()
        raise HTTPException(
            status_code=422,
            detail={"reason": "Image quality check failed", "codes": quality.reason_codes},
        )

    runtime = FibrosisModelRuntime(settings=cfg)
    pred = runtime.predict(image_bytes)

    top2_payload = [
        {"stage": item[0].value, "probability": round(item[1], 6)} for item in pred.top2
    ]

    row = FibrosisPrediction(
        patient_id=payload.patient_id,
        scan_asset_id=payload.scan_asset_id,
        performed_by=req_user.db_user.id,
        model_version=pred.model_version,
        softmax_vector={stage.value: prob for stage, prob in pred.softmax_vector.items()},
        top1_stage=pred.top1[0].value,
        top1_probability=pred.top1[1],
        top2=top2_payload,
        confidence_flag=pred.confidence_flag.value,
        escalation_flag=pred.escalation_flag.value,
        quality_metrics=quality.metrics,
    )
    scan_asset.status = "PROCESSED"

    db.add(row)
    db.flush()

    append_timeline_event(
        db,
        patient_id=payload.patient_id,
        event_type="FIBROSIS_PREDICTION_COMPLETED",
        event_payload={
            "prediction_id": row.id,
            "top1_stage": row.top1_stage,
            "top1_probability": row.top1_probability,
            "confidence_flag": row.confidence_flag,
            "escalation_flag": row.escalation_flag,
            "created_at": datetime.utcnow().isoformat(),
        },
        created_by=req_user.db_user.id,
    )

    write_audit_log(
        db,
        user_id=req_user.db_user.id,
        action="FIBROSIS_PREDICTION_CREATED",
        resource_type="fibrosis_prediction",
        resource_id=row.id,
        metadata={
            "top1_stage": row.top1_stage,
            "confidence_flag": row.confidence_flag,
            "escalation_flag": row.escalation_flag,
        },
    )

    db.commit()
    db.refresh(row)

    return FibrosisAssessmentRead(
        prediction_id=row.id,
        patient_id=row.patient_id,
        scan_asset_id=row.scan_asset_id,
        model_version=row.model_version,
        softmax_vector={FibrosisStage(k): v for k, v in row.softmax_vector.items()},
        top1=TopPrediction(stage=FibrosisStage(row.top1_stage), probability=row.top1_probability),
        top2=[TopPrediction(stage=FibrosisStage(x["stage"]), probability=x["probability"]) for x in row.top2],
        confidence_flag=row.confidence_flag,
        escalation_flag=row.escalation_flag,
        quality_metrics=row.quality_metrics,
        created_at=row.created_at,
    )

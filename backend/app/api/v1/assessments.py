from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response
from pydantic import ValidationError
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
from app.services.model_registry import (
    format_model_version,
    get_active_model,
    resolve_local_artifact_path,
)
from app.services.quality import evaluate_quality
from app.services.stage1 import Stage1Result, run_stage1
from app.services.stage1_ml_inference import Stage1ModelUnavailableError, predict_stage1_ml
from app.services.timeline import append_timeline_event

router = APIRouter(prefix="/assessments", tags=["assessments"])
settings = get_settings()


@router.post("/clinical", response_model=ClinicalAssessmentRead)
@limiter.limit(settings.rate_limit_mutating_per_ip, key_func=get_remote_address)
@limiter.limit(settings.rate_limit_mutating_per_user, key_func=user_or_ip_key)
def run_clinical_assessment(
    request: Request,
    response: Response,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    req_user: RequestUser = Depends(get_request_user),
    cfg: Settings = Depends(get_settings),
):
    try:
        parsed_payload = ClinicalAssessmentCreate.model_validate(payload)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc

    patient = assert_patient_owned_by_user(db, parsed_payload.patient_id, req_user.db_user.id)

    rule_result = run_stage1(
        age=parsed_payload.age,
        ast=parsed_payload.ast,
        alt=parsed_payload.alt,
        platelets=parsed_payload.platelets,
        ast_uln=parsed_payload.ast_uln,
        bmi=parsed_payload.bmi,
        type2dm=parsed_payload.type2dm,
    )
    result = rule_result

    if cfg.stage1_ml_enabled:
        active_stage1_model = get_active_model(db, cfg.stage1_registry_model_name)
        stage1_model_version = (
            format_model_version(
                active_stage1_model,
                default_name=cfg.stage1_registry_model_name,
                default_version="v1",
            )
            if active_stage1_model is not None
            else None
        )
        stage1_artifact_dir = resolve_local_artifact_path(
            active_stage1_model,
            cfg.stage1_model_artifact_dir,
        )
        try:
            ml_result = predict_stage1_ml(
                patient_sex=patient.sex,
                age=parsed_payload.age,
                bmi=parsed_payload.bmi,
                type2dm=parsed_payload.type2dm,
                ast=parsed_payload.ast,
                alt=parsed_payload.alt,
                platelets=parsed_payload.platelets,
                ast_uln=parsed_payload.ast_uln,
                artifact_dir=stage1_artifact_dir,
                model_version_override=stage1_model_version,
            )
            result = Stage1Result(
                fib4=rule_result.fib4,
                apri=rule_result.apri,
                risk_tier=ml_result.risk_tier,
                probability=ml_result.probability,
                model_version=ml_result.model_version,
            )
        except Stage1ModelUnavailableError as exc:
            if cfg.stage1_require_model_non_dev and not cfg.is_local_dev:
                raise HTTPException(
                    status_code=503,
                    detail=f"Stage 1 ML model unavailable: {exc}",
                ) from exc

    row = ClinicalAssessment(
        patient_id=parsed_payload.patient_id,
        performed_by=req_user.db_user.id,
        ast=parsed_payload.ast,
        alt=parsed_payload.alt,
        platelets=parsed_payload.platelets,
        ast_uln=parsed_payload.ast_uln,
        age=parsed_payload.age,
        bmi=parsed_payload.bmi,
        type2dm=parsed_payload.type2dm,
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
        patient_id=parsed_payload.patient_id,
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
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    req_user: RequestUser = Depends(get_request_user),
    cfg: Settings = Depends(get_settings),
):
    try:
        parsed_payload = FibrosisAssessmentCreate.model_validate(payload)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc

    assert_patient_owned_by_user(db, parsed_payload.patient_id, req_user.db_user.id)

    scan_asset = db.get(ScanAsset, parsed_payload.scan_asset_id)
    if not scan_asset or scan_asset.patient_id != parsed_payload.patient_id:
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

    gate = cfg.resolved_stage2_quality_gate
    quality_warned = False
    quality = evaluate_quality(image_bytes)
    if not quality.is_valid:
        if gate == "strict":
            scan_asset.status = "QUALITY_REJECTED"
            db.commit()
            detail: dict[str, object] = {"reason": "Image quality check failed", "codes": quality.reason_codes}
            if cfg.is_local_dev:
                # Safe for local demos/debugging; keep non-dev responses minimal.
                detail["metrics"] = quality.metrics
            raise HTTPException(status_code=422, detail=detail)
        # Demo mode: allow the flow to complete but keep a clear signal in stored metrics.
        quality_warned = True

    active_stage2_model = get_active_model(db, cfg.stage2_registry_model_name)
    stage2_model_version = format_model_version(
        active_stage2_model,
        default_name=cfg.stage2_registry_model_name,
        default_version="v1",
    )
    stage2_artifact_path = resolve_local_artifact_path(
        active_stage2_model,
        cfg.model_artifact_path,
    )

    try:
        runtime = FibrosisModelRuntime(
            settings=cfg,
            model_artifact_path=stage2_artifact_path,
            model_version=stage2_model_version,
        )
        pred = runtime.predict(image_bytes)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    top2_payload = [
        {"stage": item[0].value, "probability": round(item[1], 6)} for item in pred.top2
    ]

    row = FibrosisPrediction(
        patient_id=parsed_payload.patient_id,
        scan_asset_id=parsed_payload.scan_asset_id,
        performed_by=req_user.db_user.id,
        model_version=pred.model_version,
        softmax_vector={stage.value: prob for stage, prob in pred.softmax_vector.items()},
        top1_stage=pred.top1[0].value,
        top1_probability=pred.top1[1],
        top2=top2_payload,
        confidence_flag=pred.confidence_flag.value,
        escalation_flag=pred.escalation_flag.value,
        quality_metrics={
            **quality.metrics,
            "reason_codes": quality.reason_codes,
            "is_valid": quality.is_valid,
            "gate": gate,
        },
    )
    scan_asset.status = "PROCESSED_WITH_WARNINGS" if quality_warned else "PROCESSED"

    db.add(row)
    db.flush()

    append_timeline_event(
        db,
        patient_id=parsed_payload.patient_id,
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

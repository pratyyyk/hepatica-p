from __future__ import annotations

from pathlib import Path

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import ValidationError
from slowapi.util import get_remote_address
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import RequestUser, assert_patient_owned_by_user, get_request_user
from app.core.config import Settings, get_settings
from app.core.enums import FibrosisStage
from app.core.rate_limit import limiter, user_or_ip_key
from app.db.models import ClinicalAssessment, FibrosisPrediction, Report, ScanAsset
from app.db.models import RiskAlert, Stage3Assessment, Stage3Explanation
from app.db.session import get_db
from app.schemas.report import ReportCreate, ReportRead
from app.services.audit import write_audit_log
from app.services.dicom import maybe_convert_dicom
from app.services.fibrosis_inference import fetch_scan_bytes
from app.services.knowledge import retrieve_chunks, synthesize_blocks
from app.services.report import build_report_payload, render_pdf, upload_pdf
from app.services.stage3 import Stage3Error, run_stage3_assessment
from app.services.timeline import append_timeline_event

router = APIRouter(prefix="/reports", tags=["reports"])
settings = get_settings()


def _build_pdf_url(request: Request, report_id: str) -> str:
    base = str(request.base_url).rstrip("/")
    return f"{base}/api/v1/reports/{report_id}/pdf"


@router.post("", response_model=ReportRead)
@limiter.limit(settings.rate_limit_mutating_per_ip, key_func=get_remote_address)
@limiter.limit(settings.rate_limit_mutating_per_user, key_func=user_or_ip_key)
def create_report(
    request: Request,
    response: Response,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    req_user: RequestUser = Depends(get_request_user),
    cfg: Settings = Depends(get_settings),
):
    try:
        parsed_payload = ReportCreate.model_validate(payload)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc

    patient = assert_patient_owned_by_user(db, parsed_payload.patient_id, req_user.db_user.id)

    clinical = None
    fibrosis = None
    stage3 = None
    stage3_explanation = None
    stage3_failure_reason: str | None = None

    if parsed_payload.clinical_assessment_id:
        clinical = db.get(ClinicalAssessment, parsed_payload.clinical_assessment_id)
        if not clinical or clinical.patient_id != parsed_payload.patient_id:
            raise HTTPException(status_code=404, detail="Clinical assessment not found")
    if clinical is None:
        clinical = db.scalar(
            select(ClinicalAssessment)
            .where(ClinicalAssessment.patient_id == parsed_payload.patient_id)
            .order_by(ClinicalAssessment.created_at.desc())
        )

    if parsed_payload.fibrosis_prediction_id:
        fibrosis = db.get(FibrosisPrediction, parsed_payload.fibrosis_prediction_id)
        if not fibrosis or fibrosis.patient_id != parsed_payload.patient_id:
            raise HTTPException(status_code=404, detail="Fibrosis prediction not found")
    if fibrosis is None:
        fibrosis = db.scalar(
            select(FibrosisPrediction)
            .where(FibrosisPrediction.patient_id == parsed_payload.patient_id)
            .order_by(FibrosisPrediction.created_at.desc())
        )

    if parsed_payload.stage3_assessment_id:
        stage3 = db.get(Stage3Assessment, parsed_payload.stage3_assessment_id)
        if not stage3 or stage3.patient_id != parsed_payload.patient_id:
            raise HTTPException(status_code=404, detail="Stage 3 assessment not found")
    elif cfg.stage3_enabled and (clinical is not None or fibrosis is not None):
        try:
            stage3, stage3_explanation, _created_alerts = run_stage3_assessment(
                db=db,
                cfg=cfg,
                patient_id=parsed_payload.patient_id,
                performed_by=req_user.db_user.id,
                clinical_assessment_id=clinical.id if clinical else None,
                fibrosis_prediction_id=fibrosis.id if fibrosis else None,
                stiffness_measurement_id=None,
            )
        except Stage3Error as exc:
            # Report generation should still succeed even if Stage 3 cannot be computed.
            stage3 = None
            stage3_failure_reason = str(exc)
    if stage3 is None:
        stage3 = db.scalar(
            select(Stage3Assessment)
            .where(Stage3Assessment.patient_id == parsed_payload.patient_id)
            .order_by(Stage3Assessment.created_at.desc())
        )

    scan_asset = None
    if fibrosis and fibrosis.scan_asset_id:
        scan_asset = db.get(ScanAsset, fibrosis.scan_asset_id)
    if scan_asset is None:
        scan_asset = db.scalar(
            select(ScanAsset)
            .where(ScanAsset.patient_id == parsed_payload.patient_id)
            .order_by(ScanAsset.created_at.desc())
        )

    scan_preview_bytes: bytes | None = None
    scan_preview: dict[str, str | bool | None] = {
        "scan_asset_id": scan_asset.id if scan_asset else None,
        "content_type": scan_asset.content_type if scan_asset else None,
        "status": scan_asset.status if scan_asset else None,
        "included_in_pdf": False,
        "reason": "No uploaded scan available for this patient." if scan_asset is None else None,
    }
    if scan_asset is not None:
        try:
            raw_scan = fetch_scan_bytes(object_key=scan_asset.object_key, settings=cfg)
            scan_preview_bytes = maybe_convert_dicom(
                image_bytes=raw_scan,
                content_type=scan_asset.content_type,
            )
            scan_preview["included_in_pdf"] = True
            scan_preview["reason"] = "Latest uploaded scan included in PDF preview."
        except Exception:
            scan_preview["reason"] = (
                "Scan preview could not be embedded due to retrieval or "
                "format conversion limitations."
            )

    stage = fibrosis.top1_stage if fibrosis else None
    stage_enum = FibrosisStage(stage) if stage else None
    query = f"fibrosis stage {stage or 'unknown'} follow-up guidance"
    retrieved = retrieve_chunks(db=db, query=query, settings=cfg, top_k=5)
    knowledge_blocks = synthesize_blocks(
        fibrosis_stage=stage_enum,
        retrieved=retrieved,
    )

    if stage3 is not None and stage3_explanation is None:
        stage3_explanation = db.scalar(
            select(Stage3Explanation).where(Stage3Explanation.stage3_assessment_id == stage3.id)
        )
    stage3_alert_rows = list(
        db.scalars(
            select(RiskAlert)
            .where(RiskAlert.patient_id == parsed_payload.patient_id)
            .order_by(RiskAlert.created_at.desc())
            .limit(10)
        ).all()
    )

    report_json = build_report_payload(
        patient={
            "id": patient.id,
            "external_id": patient.external_id,
            "sex": patient.sex,
            "age": patient.age,
        },
        clinical=(
            {
                "id": clinical.id,
                "fib4": clinical.fib4,
                "apri": clinical.apri,
                "risk_tier": clinical.risk_tier,
                "probability": clinical.probability,
                "model_version": clinical.model_version,
            }
            if clinical
            else None
        ),
        fibrosis=(
            {
                "id": fibrosis.id,
                "top1_stage": fibrosis.top1_stage,
                "top1_probability": fibrosis.top1_probability,
                "confidence_flag": fibrosis.confidence_flag,
                "escalation_flag": fibrosis.escalation_flag,
                "softmax_vector": fibrosis.softmax_vector,
                "model_version": fibrosis.model_version,
            }
            if fibrosis
            else None
        ),
        stage3=(
            {
                "id": stage3.id,
                "composite_risk_score": stage3.composite_risk_score,
                "progression_risk_12m": stage3.progression_risk_12m,
                "decomp_risk_12m": stage3.decomp_risk_12m,
                "risk_tier": stage3.risk_tier,
                "model_version": stage3.model_version,
                "feature_snapshot_json": stage3.feature_snapshot_json,
            }
            if stage3
            else None
        ),
        stage3_explanation=(
            {
                "local_feature_contrib_json": stage3_explanation.local_feature_contrib_json,
                "global_reference_version": stage3_explanation.global_reference_version,
                "trend_points_json": stage3_explanation.trend_points_json,
            }
            if stage3_explanation
            else None
        ),
        stage3_alerts=[
            {
                "id": alert.id,
                "alert_type": alert.alert_type,
                "severity": alert.severity,
                "status": alert.status,
                "score": alert.score,
                "threshold": alert.threshold,
                "created_at": alert.created_at.isoformat() if alert.created_at else None,
            }
            for alert in stage3_alert_rows
        ],
        knowledge_blocks=knowledge_blocks,
        scan_preview=scan_preview,
        stage3_enabled=cfg.stage3_enabled,
        stage3_failure_reason=stage3_failure_reason,
    )

    row = Report(
        patient_id=parsed_payload.patient_id,
        created_by=req_user.db_user.id,
        clinical_assessment_id=clinical.id if clinical else None,
        fibrosis_prediction_id=fibrosis.id if fibrosis else None,
        pdf_object_key=None,
        report_json=report_json,
        disclaimer=report_json["disclaimer"],
    )
    db.add(row)
    db.flush()

    pdf_bytes = render_pdf(report_json, scan_preview_bytes=scan_preview_bytes)
    object_key = upload_pdf(report_id=row.id, pdf_bytes=pdf_bytes, settings=cfg)
    row.pdf_object_key = object_key

    append_timeline_event(
        db,
        patient_id=parsed_payload.patient_id,
        event_type="REPORT_GENERATED",
        event_payload={"report_id": row.id, "pdf_object_key": object_key},
        created_by=req_user.db_user.id,
    )

    write_audit_log(
        db,
        user_id=req_user.db_user.id,
        action="REPORT_GENERATED",
        resource_type="report",
        resource_id=row.id,
        metadata={"pdf_object_key": object_key},
    )

    db.commit()
    db.refresh(row)

    return ReportRead(
        report_id=row.id,
        patient_id=row.patient_id,
        pdf_download_url=_build_pdf_url(request, row.id),
        report_json=row.report_json,
        created_at=row.created_at,
    )


@router.get("/{report_id}/pdf")
@limiter.limit(settings.rate_limit_read_per_user, key_func=user_or_ip_key)
def get_report_pdf(
    request: Request,
    response: Response,
    report_id: str,
    db: Session = Depends(get_db),
    req_user: RequestUser = Depends(get_request_user),
    cfg: Settings = Depends(get_settings),
):
    row = db.get(Report, report_id)
    if not row:
        raise HTTPException(status_code=404, detail="Report not found")

    assert_patient_owned_by_user(db, row.patient_id, req_user.db_user.id)

    if not row.pdf_object_key:
        raise HTTPException(status_code=404, detail="Report PDF not available")

    object_key = row.pdf_object_key
    filename = f"hepatica-report-{row.id}.pdf"
    content_disposition = f'inline; filename="{filename}"'

    local_path = Path(object_key)
    if local_path.is_absolute() and local_path.exists():
        return FileResponse(
            path=str(local_path),
            media_type="application/pdf",
            filename=filename,
            headers={"Content-Disposition": content_disposition},
        )

    s3 = boto3.client("s3", region_name=cfg.aws_region)
    try:
        obj = s3.get_object(Bucket=cfg.s3_report_bucket, Key=object_key)
        body = obj["Body"]
        return StreamingResponse(
            body,
            media_type="application/pdf",
            headers={"Content-Disposition": content_disposition},
        )
    except (BotoCoreError, ClientError) as exc:
        raise HTTPException(status_code=404, detail="Report PDF not available") from exc


@router.get("/{report_id}", response_model=ReportRead)
@limiter.limit(settings.rate_limit_read_per_user, key_func=user_or_ip_key)
def get_report(
    request: Request,
    response: Response,
    report_id: str,
    db: Session = Depends(get_db),
    req_user: RequestUser = Depends(get_request_user),
    cfg: Settings = Depends(get_settings),
):
    row = db.get(Report, report_id)
    if not row:
        raise HTTPException(status_code=404, detail="Report not found")

    assert_patient_owned_by_user(db, row.patient_id, req_user.db_user.id)

    return ReportRead(
        report_id=row.id,
        patient_id=row.patient_id,
        pdf_download_url=_build_pdf_url(request, row.id) if row.pdf_object_key else None,
        report_json=row.report_json,
        created_at=row.created_at,
    )

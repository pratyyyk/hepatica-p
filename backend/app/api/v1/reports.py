from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from slowapi.util import get_remote_address
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import RequestUser, assert_patient_owned_by_user, get_request_user
from app.core.config import Settings, get_settings
from app.core.enums import FibrosisStage
from app.core.rate_limit import limiter, user_or_ip_key
from app.db.models import ClinicalAssessment, FibrosisPrediction, Report
from app.db.session import get_db
from app.schemas.report import ReportCreate, ReportRead
from app.services.audit import write_audit_log
from app.services.knowledge import retrieve_chunks, synthesize_blocks
from app.services.report import build_download_url, build_report_payload, render_pdf, upload_pdf
from app.services.timeline import append_timeline_event

router = APIRouter(prefix="/reports", tags=["reports"])
settings = get_settings()


@router.post("", response_model=ReportRead)
@limiter.limit(settings.rate_limit_mutating_per_ip, key_func=get_remote_address)
@limiter.limit(settings.rate_limit_mutating_per_user, key_func=user_or_ip_key)
def create_report(
    request: Request,
    response: Response,
    payload: ReportCreate,
    db: Session = Depends(get_db),
    req_user: RequestUser = Depends(get_request_user),
    cfg: Settings = Depends(get_settings),
):
    patient = assert_patient_owned_by_user(db, payload.patient_id, req_user.db_user.id)

    clinical = None
    fibrosis = None

    if payload.clinical_assessment_id:
        clinical = db.get(ClinicalAssessment, payload.clinical_assessment_id)
        if not clinical or clinical.patient_id != payload.patient_id:
            raise HTTPException(status_code=404, detail="Clinical assessment not found")
    if clinical is None:
        clinical = db.scalar(
            select(ClinicalAssessment)
            .where(ClinicalAssessment.patient_id == payload.patient_id)
            .order_by(ClinicalAssessment.created_at.desc())
        )

    if payload.fibrosis_prediction_id:
        fibrosis = db.get(FibrosisPrediction, payload.fibrosis_prediction_id)
        if not fibrosis or fibrosis.patient_id != payload.patient_id:
            raise HTTPException(status_code=404, detail="Fibrosis prediction not found")
    if fibrosis is None:
        fibrosis = db.scalar(
            select(FibrosisPrediction)
            .where(FibrosisPrediction.patient_id == payload.patient_id)
            .order_by(FibrosisPrediction.created_at.desc())
        )

    stage = fibrosis.top1_stage if fibrosis else None
    stage_enum = FibrosisStage(stage) if stage else None
    query = f"fibrosis stage {stage or 'unknown'} follow-up guidance"
    retrieved = retrieve_chunks(db=db, query=query, settings=cfg, top_k=5)
    knowledge_blocks = synthesize_blocks(
        fibrosis_stage=stage_enum,
        retrieved=retrieved,
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
        knowledge_blocks=knowledge_blocks,
    )

    row = Report(
        patient_id=payload.patient_id,
        created_by=req_user.db_user.id,
        clinical_assessment_id=clinical.id if clinical else None,
        fibrosis_prediction_id=fibrosis.id if fibrosis else None,
        pdf_object_key=None,
        report_json=report_json,
        disclaimer=report_json["disclaimer"],
    )
    db.add(row)
    db.flush()

    pdf_bytes = render_pdf(report_json)
    object_key = upload_pdf(report_id=row.id, pdf_bytes=pdf_bytes, settings=cfg)
    row.pdf_object_key = object_key

    append_timeline_event(
        db,
        patient_id=payload.patient_id,
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
        pdf_download_url=build_download_url(object_key=row.pdf_object_key, settings=cfg),
        report_json=row.report_json,
        created_at=row.created_at,
    )


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
        pdf_download_url=(
            build_download_url(object_key=row.pdf_object_key, settings=cfg)
            if row.pdf_object_key
            else None
        ),
        report_json=row.report_json,
        created_at=row.created_at,
    )

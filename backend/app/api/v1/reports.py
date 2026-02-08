from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import RequestUser, get_request_user
from app.core.config import Settings, get_settings
from app.core.enums import FibrosisStage
from app.db.models import ClinicalAssessment, FibrosisPrediction, Patient, Report
from app.db.session import get_db
from app.schemas.report import ReportCreate, ReportRead
from app.services.audit import write_audit_log
from app.services.knowledge import retrieve_chunks, synthesize_blocks
from app.services.report import build_download_url, build_report_payload, render_pdf, upload_pdf
from app.services.timeline import append_timeline_event

router = APIRouter(prefix="/reports", tags=["reports"])


@router.post("", response_model=ReportRead)
def create_report(
    payload: ReportCreate,
    db: Session = Depends(get_db),
    req_user: RequestUser = Depends(get_request_user),
    settings: Settings = Depends(get_settings),
):
    patient = db.get(Patient, payload.patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    clinical = None
    fibrosis = None

    if payload.clinical_assessment_id:
        clinical = db.get(ClinicalAssessment, payload.clinical_assessment_id)
    if clinical is None:
        clinical = db.scalar(
            select(ClinicalAssessment)
            .where(ClinicalAssessment.patient_id == payload.patient_id)
            .order_by(ClinicalAssessment.created_at.desc())
        )

    if payload.fibrosis_prediction_id:
        fibrosis = db.get(FibrosisPrediction, payload.fibrosis_prediction_id)
    if fibrosis is None:
        fibrosis = db.scalar(
            select(FibrosisPrediction)
            .where(FibrosisPrediction.patient_id == payload.patient_id)
            .order_by(FibrosisPrediction.created_at.desc())
        )

    stage = fibrosis.top1_stage if fibrosis else None
    stage_enum = FibrosisStage(stage) if stage else None
    query = f"fibrosis stage {stage or 'unknown'} follow-up guidance"
    retrieved = retrieve_chunks(db=db, query=query, settings=settings, top_k=5)
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
    object_key = upload_pdf(report_id=row.id, pdf_bytes=pdf_bytes, settings=settings)
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
        pdf_download_url=build_download_url(object_key=row.pdf_object_key, settings=settings),
        report_json=row.report_json,
        created_at=row.created_at,
    )


@router.get("/{report_id}", response_model=ReportRead)
def get_report(
    report_id: str,
    db: Session = Depends(get_db),
    req_user: RequestUser = Depends(get_request_user),
    settings: Settings = Depends(get_settings),
):
    row = db.get(Report, report_id)
    if not row:
        raise HTTPException(status_code=404, detail="Report not found")

    return ReportRead(
        report_id=row.id,
        patient_id=row.patient_id,
        pdf_download_url=(
            build_download_url(object_key=row.pdf_object_key, settings=settings)
            if row.pdf_object_key
            else None
        ),
        report_json=row.report_json,
        created_at=row.created_at,
    )

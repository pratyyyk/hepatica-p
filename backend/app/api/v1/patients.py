from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, Response, status
from pydantic import ValidationError
from slowapi.util import get_remote_address
from sqlalchemy import delete, desc, select
from sqlalchemy.orm import Session

from app.api.deps import RequestUser, assert_patient_owned_by_user, get_request_user
from app.core.config import get_settings
from app.core.rate_limit import limiter, user_or_ip_key
from app.db.models import (
    ClinicalAssessment,
    FibrosisPrediction,
    Patient,
    Report,
    RiskAlert,
    ScanAsset,
    Stage3Assessment,
    Stage3Explanation,
    StiffnessMeasurement,
    TimelineEvent,
)
from app.db.session import get_db
from app.schemas.patient import PatientCreate, PatientRead
from app.services.audit import write_audit_log
from app.services.timeline import append_timeline_event

router = APIRouter(prefix="/patients", tags=["patients"])
settings = get_settings()


@router.get("", response_model=list[PatientRead])
@limiter.limit(settings.rate_limit_read_per_user, key_func=user_or_ip_key)
def list_patients(
    request: Request,
    response: Response,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=10_000),
    db: Session = Depends(get_db),
    req_user: RequestUser = Depends(get_request_user),
):
    rows = db.scalars(
        select(Patient)
        .where(Patient.created_by == req_user.db_user.id)
        .order_by(desc(Patient.created_at))
        .limit(limit)
        .offset(offset)
    ).all()
    return list(rows)


@router.post("", response_model=PatientRead, status_code=status.HTTP_201_CREATED)
@limiter.limit(settings.rate_limit_mutating_per_ip, key_func=get_remote_address)
@limiter.limit(settings.rate_limit_mutating_per_user, key_func=user_or_ip_key)
def create_patient(
    request: Request,
    response: Response,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    req_user: RequestUser = Depends(get_request_user),
):
    try:
        parsed_payload = PatientCreate.model_validate(payload)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc

    existing = db.scalar(select(Patient).where(Patient.external_id == parsed_payload.external_id))
    if existing:
        raise HTTPException(status_code=409, detail="Patient external_id already exists")

    patient = Patient(
        external_id=parsed_payload.external_id,
        sex=parsed_payload.sex,
        age=parsed_payload.age,
        bmi=parsed_payload.bmi,
        type2dm=parsed_payload.type2dm,
        notes=parsed_payload.notes,
        created_by=req_user.db_user.id,
    )
    db.add(patient)
    db.flush()

    append_timeline_event(
        db,
        patient_id=patient.id,
        event_type="PATIENT_CREATED",
        event_payload={"external_id": patient.external_id},
        created_by=req_user.db_user.id,
    )
    write_audit_log(
        db,
        user_id=req_user.db_user.id,
        action="PATIENT_CREATED",
        resource_type="patient",
        resource_id=patient.id,
        metadata={"external_id": patient.external_id},
    )

    db.commit()
    db.refresh(patient)
    return patient


@router.get("/{patient_id}", response_model=PatientRead)
@limiter.limit(settings.rate_limit_read_per_user, key_func=user_or_ip_key)
def get_patient(
    request: Request,
    response: Response,
    patient_id: str,
    db: Session = Depends(get_db),
    req_user: RequestUser = Depends(get_request_user),
):
    patient = assert_patient_owned_by_user(db, patient_id, req_user.db_user.id)

    write_audit_log(
        db,
        user_id=req_user.db_user.id,
        action="PATIENT_READ",
        resource_type="patient",
        resource_id=patient.id,
        metadata={},
    )
    db.commit()
    return patient


@router.delete("/{patient_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit(settings.rate_limit_mutating_per_ip, key_func=get_remote_address)
@limiter.limit(settings.rate_limit_mutating_per_user, key_func=user_or_ip_key)
def delete_patient(
    request: Request,
    response: Response,
    patient_id: str,
    db: Session = Depends(get_db),
    req_user: RequestUser = Depends(get_request_user),
):
    patient = assert_patient_owned_by_user(db, patient_id, req_user.db_user.id)

    stage3_ids = db.scalars(
        select(Stage3Assessment.id).where(Stage3Assessment.patient_id == patient.id)
    ).all()

    if stage3_ids:
        db.execute(
            delete(Stage3Explanation).where(
                Stage3Explanation.stage3_assessment_id.in_(stage3_ids)
            )
        )

    db.execute(delete(RiskAlert).where(RiskAlert.patient_id == patient.id))
    db.execute(delete(Report).where(Report.patient_id == patient.id))
    db.execute(delete(TimelineEvent).where(TimelineEvent.patient_id == patient.id))
    db.execute(delete(Stage3Assessment).where(Stage3Assessment.patient_id == patient.id))
    db.execute(delete(FibrosisPrediction).where(FibrosisPrediction.patient_id == patient.id))
    db.execute(delete(ScanAsset).where(ScanAsset.patient_id == patient.id))
    db.execute(delete(ClinicalAssessment).where(ClinicalAssessment.patient_id == patient.id))
    db.execute(delete(StiffnessMeasurement).where(StiffnessMeasurement.patient_id == patient.id))

    patient_external_id = patient.external_id
    db.delete(patient)
    write_audit_log(
        db,
        user_id=req_user.db_user.id,
        action="PATIENT_DELETED",
        resource_type="patient",
        resource_id=patient_id,
        metadata={"external_id": patient_external_id},
    )
    db.commit()

    return Response(status_code=status.HTTP_204_NO_CONTENT)

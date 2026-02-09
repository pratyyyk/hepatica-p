from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response, status
from pydantic import ValidationError
from slowapi.util import get_remote_address
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import RequestUser, assert_patient_owned_by_user, get_request_user
from app.core.config import get_settings
from app.core.rate_limit import limiter, user_or_ip_key
from app.db.models import Patient
from app.db.session import get_db
from app.schemas.patient import PatientCreate, PatientRead
from app.services.audit import write_audit_log
from app.services.timeline import append_timeline_event

router = APIRouter(prefix="/patients", tags=["patients"])
settings = get_settings()


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

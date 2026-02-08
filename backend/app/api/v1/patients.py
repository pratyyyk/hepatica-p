from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import RequestUser, get_request_user
from app.db.models import Patient
from app.db.session import get_db
from app.schemas.patient import PatientCreate, PatientRead
from app.services.audit import write_audit_log
from app.services.timeline import append_timeline_event

router = APIRouter(prefix="/patients", tags=["patients"])


@router.post("", response_model=PatientRead, status_code=status.HTTP_201_CREATED)
def create_patient(
    payload: PatientCreate,
    db: Session = Depends(get_db),
    req_user: RequestUser = Depends(get_request_user),
):
    existing = db.scalar(select(Patient).where(Patient.external_id == payload.external_id))
    if existing:
        raise HTTPException(status_code=409, detail="Patient external_id already exists")

    patient = Patient(
        external_id=payload.external_id,
        sex=payload.sex,
        age=payload.age,
        bmi=payload.bmi,
        type2dm=payload.type2dm,
        notes=payload.notes,
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
def get_patient(
    patient_id: str,
    db: Session = Depends(get_db),
    req_user: RequestUser = Depends(get_request_user),
):
    patient = db.get(Patient, patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

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

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.security import AuthContext, dev_auth_route_available, require_doctor
from app.db.models import Patient, User
from app.db.session import get_db
from app.services.audit import record_auth_failure


@dataclass
class RequestUser:
    auth: AuthContext
    db_user: User


def get_request_user(
    auth: AuthContext = Depends(require_doctor),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> RequestUser:
    db_user = db.get(User, auth.user_id)
    if db_user is None:
        db_user = db.scalar(select(User).where(User.email == auth.email))

    if db_user is None:
        if auth.session_id is None and dev_auth_route_available(settings):
            db_user = User(email=auth.email, full_name=auth.email, role="DOCTOR")
            db.add(db_user)
            db.commit()
            db.refresh(db_user)
        else:
            raise HTTPException(status_code=401, detail="Authenticated user is not provisioned")

    return RequestUser(auth=auth, db_user=db_user)


def assert_patient_owned_by_user(db: Session, patient_id: str, user_id: str) -> Patient:
    patient = db.scalar(
        select(Patient).where(
            Patient.id == patient_id,
            Patient.created_by == user_id,
        )
    )
    if not patient:
        record_auth_failure(
            reason="OWNERSHIP_DENIED",
            metadata={"patient_id": patient_id, "user_id": user_id},
        )
        raise HTTPException(status_code=404, detail="Patient not found")
    return patient

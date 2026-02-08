from dataclasses import dataclass

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import AuthContext, require_doctor
from app.db.models import User
from app.db.session import get_db


@dataclass
class RequestUser:
    auth: AuthContext
    db_user: User


def get_request_user(
    auth: AuthContext = Depends(require_doctor),
    db: Session = Depends(get_db),
) -> RequestUser:
    existing = db.scalar(select(User).where(User.email == auth.email))
    if existing is None:
        existing = User(email=auth.email, full_name=auth.email, role="DOCTOR")
        db.add(existing)
        db.commit()
        db.refresh(existing)
    return RequestUser(auth=auth, db_user=existing)

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import User
from app.db.session import get_db
from app.schemas.auth import DevLoginRequest, DevLoginResponse
from app.services.audit import write_audit_log

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/dev-login", response_model=DevLoginResponse)
def dev_login(payload: DevLoginRequest, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == payload.email))
    if user is None:
        user = User(email=payload.email, full_name=payload.full_name or payload.email, role="DOCTOR")
        db.add(user)
        db.flush()

    write_audit_log(
        db,
        user_id=user.id,
        action="LOGIN",
        resource_type="user",
        resource_id=user.id,
        metadata={"email": user.email, "mode": "dev-login"},
    )
    db.commit()

    return DevLoginResponse(user_id=user.id, email=user.email, role=user.role)

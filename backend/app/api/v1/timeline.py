from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import RequestUser, assert_patient_owned_by_user, get_request_user
from app.core.config import get_settings
from app.core.rate_limit import limiter, user_or_ip_key
from app.db.models import TimelineEvent
from app.db.session import get_db
from app.schemas.timeline import TimelineEventRead, TimelineRead

router = APIRouter(prefix="/patients", tags=["timeline"])
settings = get_settings()


@router.get("/{patient_id}/timeline", response_model=TimelineRead)
@limiter.limit(settings.rate_limit_read_per_user, key_func=user_or_ip_key)
def get_patient_timeline(
    request: Request,
    response: Response,
    patient_id: str,
    db: Session = Depends(get_db),
    req_user: RequestUser = Depends(get_request_user),
):
    assert_patient_owned_by_user(db, patient_id, req_user.db_user.id)

    events = db.scalars(
        select(TimelineEvent)
        .where(TimelineEvent.patient_id == patient_id)
        .order_by(TimelineEvent.created_at.asc())
    ).all()

    return TimelineRead(
        patient_id=patient_id,
        events=[
            TimelineEventRead(
                id=e.id,
                patient_id=e.patient_id,
                event_type=e.event_type,
                event_payload=e.event_payload,
                created_at=e.created_at,
            )
            for e in events
        ],
    )

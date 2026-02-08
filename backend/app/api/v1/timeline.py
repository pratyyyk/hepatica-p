from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import RequestUser, get_request_user
from app.db.models import Patient, TimelineEvent
from app.db.session import get_db
from app.schemas.timeline import TimelineEventRead, TimelineRead

router = APIRouter(prefix="/patients", tags=["timeline"])


@router.get("/{patient_id}/timeline", response_model=TimelineRead)
def get_patient_timeline(
    patient_id: str,
    db: Session = Depends(get_db),
    req_user: RequestUser = Depends(get_request_user),
):
    patient = db.get(Patient, patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

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

from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.models import TimelineEvent


def append_timeline_event(
    db: Session,
    *,
    patient_id: str,
    event_type: str,
    event_payload: dict,
    created_by: str | None,
) -> TimelineEvent:
    event = TimelineEvent(
        patient_id=patient_id,
        event_type=event_type,
        event_payload=event_payload,
        created_by=created_by,
    )
    db.add(event)
    db.flush()
    return event

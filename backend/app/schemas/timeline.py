from datetime import datetime

from pydantic import BaseModel


class TimelineEventRead(BaseModel):
    id: str
    patient_id: str
    event_type: str
    event_payload: dict
    created_at: datetime


class TimelineRead(BaseModel):
    patient_id: str
    events: list[TimelineEventRead]

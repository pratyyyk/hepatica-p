from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PatientCreate(BaseModel):
    external_id: str = Field(min_length=3, max_length=64)
    sex: str | None = Field(default=None, max_length=16)
    age: int | None = Field(default=None, ge=0, le=120)
    bmi: float | None = Field(default=None, ge=10, le=80)
    type2dm: bool = False
    notes: str | None = Field(default=None, max_length=2000)


class PatientRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    external_id: str
    sex: str | None
    age: int | None
    bmi: float | None
    type2dm: bool
    notes: str | None
    created_at: datetime

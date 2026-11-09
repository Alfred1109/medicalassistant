"""Patient self-reports against a confirmed, published prescription snapshot."""
from datetime import datetime, timezone
from enum import Enum
from typing import List
from uuid import UUID

from bson import ObjectId
from pydantic import BaseModel, ConfigDict, Field, field_validator


class PatientExecutionStatus(str, Enum):
    COMPLETED = "completed"
    PARTIAL = "partial"
    NOT_DONE = "not_done"


class PatientFeedbackCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    event_id: UUID
    version_id: str
    prescription_item_id: str
    execution_status: PatientExecutionStatus
    feelings: str = Field(min_length=1, max_length=2000)
    performed_at: datetime

    @field_validator("version_id", "prescription_item_id")
    @classmethod
    def valid_identifier(cls, value):
        if not ObjectId.is_valid(value):
            raise ValueError("a valid snapshot identifier is required")
        return str(ObjectId(value))

    @field_validator("performed_at")
    @classmethod
    def utc_milliseconds(cls, value):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("performed_at must include a timezone")
        value = value.astimezone(timezone.utc)
        return value.replace(microsecond=value.microsecond // 1000 * 1000)


class PatientFeedbackResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    event_id: str
    plan_id: str
    version_id: str
    prescription_item_id: str
    execution_status: PatientExecutionStatus
    feelings: str
    performed_at: datetime
    recorded_by: str
    created_at: datetime


class PatientFeedbackResult(BaseModel):
    feedback: PatientFeedbackResponse
    created: bool


class PatientFeedbackPage(BaseModel):
    items: List[PatientFeedbackResponse]
    total: int = Field(ge=0)
    skip: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)

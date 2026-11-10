"""Explicit clinical drafts and immutable patient-visible publication contracts."""
import re
from datetime import datetime, timezone
from typing import Literal
from urllib.parse import urlsplit
from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator, model_validator
from app.schemas.rehab_plan_structure import (
    PrescriptionSchedule, DietInterventionFields, MedicationInterventionFields,
    PsychologyInterventionFields,
)


class PublicationContent(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=5000)
    goal: str = Field(min_length=1, max_length=2000)
    start_date: datetime
    end_date: datetime | None = None
    frequency: str | None = Field(default=None, max_length=500)
    patient_instructions: str | None = Field(default=None, max_length=5000)

    @field_validator("start_date", "end_date")
    @classmethod
    def aware_utc(cls, value):
        if value is not None:
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("publication dates require an explicit timezone")
            return value.astimezone(timezone.utc)
        return value

    @model_validator(mode="after")
    def chronological(self):
        if self.end_date is not None and self.end_date < self.start_date:
            raise ValueError("end_date must not precede start_date")
        return self


class PublicationItem(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    item_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{24}$")
    intervention_type: Literal["diet", "exercise", "medication", "psychology"]
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    schedule: PrescriptionSchedule | None = None
    contraindications: list[str] | None = Field(default=None, max_length=100)
    applicability_conditions: list[str] | None = Field(default=None, max_length=100)
    patient_instructions: str | None = Field(default=None, max_length=5000)
    guidance_video_url: str | None = Field(default=None, max_length=500)
    diet_fields: DietInterventionFields | None = None
    medication_fields: MedicationInterventionFields | None = None
    psychology_fields: PsychologyInterventionFields | None = None

    @field_validator("guidance_video_url")
    @classmethod
    def guidance_video(cls, value):
        if value is None:
            return None
        if re.fullmatch(r"/api/rehabilitation/exercises/media/[0-9a-f]{32}\.(mp4|webm)", value):
            return value
        parsed = urlsplit(value)
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            return value
        raise ValueError("guidance video must be an uploaded file or an http(s) address")

    @model_validator(mode="after")
    def matching_fields_and_positive_schedule(self):
        for kind in ("diet", "medication", "psychology"):
            if getattr(self, kind + "_fields") is not None and self.intervention_type != kind:
                raise ValueError("intervention-specific fields must match the intervention type")
        if self.schedule:
            for name in ("sets", "reps", "repetitions", "duration_minutes", "days_per_week"):
                value = getattr(self.schedule, name)
                if value is not None and (value <= 0 or (name == "days_per_week" and value > 7)):
                    raise ValueError("schedule quantities must be positive and days_per_week cannot exceed seven")
        return self


class OperationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    request_id: str = Field(min_length=8, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")


class SavePublicationDraft(OperationRequest):
    expected_draft_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{24}$")
    expected_draft_revision: int | None = Field(default=None, ge=0, strict=True)
    content: PublicationContent
    items: list[PublicationItem] = Field(default_factory=list, max_length=200)

    @model_validator(mode="after")
    def expectation_pair(self):
        if (self.expected_draft_id is None) != (self.expected_draft_revision is None):
            raise ValueError("draft identity and revision must be supplied together")
        identities = [item.item_id for item in self.items if item.item_id]
        if len(set(identities)) != len(identities):
            raise ValueError("duplicate prescription item")
        return self


class PublishDraft(OperationRequest):
    draft_id: str = Field(pattern=r"^[0-9a-f]{24}$")
    expected_draft_revision: int = Field(ge=0, strict=True)
    expected_publication_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{24}$")
    confirmed: StrictBool
    confirmation_note: str = Field(min_length=1, max_length=2000)

    @field_validator("confirmed")
    @classmethod
    def explicit_confirmation(cls, value):
        if value is not True:
            raise ValueError("the clinician must explicitly confirm the complete publication")
        return value


class WithdrawPublication(OperationRequest):
    action: Literal["withdraw", "cancel", "archive"] = "withdraw"
    expected_publication_id: str = Field(pattern=r"^[0-9a-f]{24}$")
    reason: str = Field(min_length=1, max_length=2000)

"""Process fact DTOs. No clinical scores, targets or threshold judgments."""
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field


class StatusCount(BaseModel):
    status: str
    count: int = Field(ge=0)


class PublicationCount(BaseModel):
    state: Literal["published", "unpublished", "withdrawn", "stopped", "invalid_reference"]
    count: int = Field(ge=0)


class ProcessSummary(BaseModel):
    selected_total: int = Field(ge=0)
    scope_total: int = Field(ge=0)
    missing_date_count: int = Field(ge=0)
    invalid_date_count: int = Field(ge=0)
    unresolved_patient_count: int = Field(ge=0)
    by_status: list[StatusCount]


class FollowupProcessSummary(ProcessSummary):
    in_review_count: int = Field(ge=0)


class PlanProcessSummary(ProcessSummary):
    publication_states: list[PublicationCount]


class ProcessWindow(BaseModel):
    start_date: datetime | None
    end_date: datetime | None
    followup_date_field: Literal["scheduled_date"] = "scheduled_date"
    plan_date_field: Literal["created_at"] = "created_at"


class QualityProcessOverview(BaseModel):
    generated_at: datetime
    scope_kind: Literal["assigned_patients", "all_source_records", "selected_patient"]
    read_consistency: Literal["independent_live_reads"] = "independent_live_reads"
    publication_validation: Literal["reference_and_required_structure"] = "reference_and_required_structure"
    window: ProcessWindow
    followups: FollowupProcessSummary
    plans: PlanProcessSummary


class QualityProcessItem(BaseModel):
    source_type: Literal["followup", "rehab_plan"]
    source_id: str
    source_reference_state: Literal["valid", "unaddressable"]
    patient_id: str | None
    status: str
    date: datetime | None
    date_quality: Literal["valid", "missing", "invalid"]
    patient_reference_state: Literal["valid", "missing", "invalid", "not_found", "ambiguous"]
    issue_eligible: bool
    publication_state: Literal["published", "unpublished", "withdrawn", "stopped", "invalid_reference"] | None = None


class QualityProcessPage(BaseModel):
    items: list[QualityProcessItem]
    total: int = Field(ge=0)
    skip: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    date_field: Literal["scheduled_date", "created_at"]

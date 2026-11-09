"""Human-confirmed process quality issues; no inferred clinical abnormality."""
from typing import Literal

from bson import ObjectId
from pydantic import BaseModel, ConfigDict, Field, field_validator

IssueStatus = Literal["open", "in_progress", "pending_review", "closed"]
SourceType = Literal["followup", "rehab_plan"]


class Operation(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    request_id: str = Field(min_length=8, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")


class QualityIssueCreate(Operation):
    patient_id: str
    source_type: SourceType
    source_id: str
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=5000)
    evidence_refs: list[str] = Field(min_length=1, max_length=20)

    @field_validator("patient_id", "source_id")
    @classmethod
    def object_identifier(cls, value):
        if not ObjectId.is_valid(value):
            raise ValueError("invalid object identifier")
        return str(ObjectId(value))

    @field_validator("evidence_refs")
    @classmethod
    def references(cls, values):
        return validate_references(values)


def validate_references(values):
    if any(not value.strip() or len(value.strip()) > 256 for value in values):
        raise ValueError("evidence references must contain 1 to 256 characters")
    return list(dict.fromkeys(value.strip() for value in values))


class Mutation(Operation):
    expected_version: int = Field(ge=0, strict=True)


class AssignQualityIssue(Mutation):
    assignee_id: str
    note: str = Field(min_length=1, max_length=2000)

    @field_validator("assignee_id")
    @classmethod
    def object_identifier(cls, value):
        if not ObjectId.is_valid(value):
            raise ValueError("invalid assignee identifier")
        return str(ObjectId(value))


class ConfirmQualityIssue(Mutation):
    note: str = Field(min_length=1, max_length=2000)


class ResolveQualityIssue(Mutation):
    resolution: str = Field(min_length=1, max_length=5000)
    evidence_refs: list[str] = Field(min_length=1, max_length=20)

    @field_validator("evidence_refs")
    @classmethod
    def references(cls, values):
        return validate_references(values)


class ReviewQualityIssue(Mutation):
    decision: Literal["approve", "return"]
    note: str = Field(min_length=1, max_length=2000)
    evidence_refs: list[str] = Field(min_length=1, max_length=20)

    @field_validator("evidence_refs")
    @classmethod
    def references(cls, values):
        return validate_references(values)

"""Plan-level cycle administration and clinician closeout contracts."""
from datetime import date
from pydantic import BaseModel, ConfigDict, Field, model_validator


class _CycleDates(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    title: str = Field(min_length=1, max_length=120)
    start_date: date
    end_date: date

    @model_validator(mode="after")
    def ordered_dates(self):
        if self.end_date < self.start_date:
            raise ValueError("end_date must not precede start_date")
        return self


class TrainingCycleCreate(_CycleDates):
    request_id: str = Field(min_length=8, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")


class TrainingCycleUpdate(_CycleDates):
    request_id: str = Field(min_length=8, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    expected_revision: int = Field(ge=0, strict=True)


class TrainingCycleAcceptance(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    request_id: str = Field(min_length=8, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    expected_revision: int = Field(ge=0, strict=True)
    note: str = Field(min_length=1, max_length=2000)

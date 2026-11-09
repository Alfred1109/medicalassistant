"""DTOs for patients without authentication or role-assignment fields."""
from datetime import datetime
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator, model_validator


class SourcePatientIdentity(BaseModel):
    """One global source patient, independent of project subjects and accounts."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    origin: str
    system: Literal["form-platform-11344"]
    environment: Literal["pilot", "production"]
    patient_id: StrictInt = Field(gt=0)

    @field_validator("origin")
    @classmethod
    def canonical_origin(cls, value):
        parsed = urlsplit(value)
        if (not parsed.hostname or parsed.username or parsed.password or parsed.path
                or parsed.query or parsed.fragment or parsed.scheme not in {"http", "https"}):
            raise ValueError("an exact source origin is required")
        if parsed.scheme == "http" and parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("HTTP is restricted to an isolated loopback source")
        try:
            port = parsed.port
        except ValueError:
            raise ValueError("invalid source port") from None
        host = parsed.hostname.lower()
        if ":" in host:
            host = "[" + host + "]"
        suffix = "" if port is None or (parsed.scheme, port) in {("https", 443), ("http", 80)} else ":" + str(port)
        return parsed.scheme + "://" + host + suffix

    @model_validator(mode="after")
    def production_requires_https(self):
        if self.environment == "production" and not self.origin.startswith("https://"):
            raise ValueError("a production source requires HTTPS")
        return self


class ClinicalPatientResponse(BaseModel):
    """No email/password is necessary to exist as a clinical patient."""

    model_config = ConfigDict(extra="forbid")

    id: str
    status: Literal["active", "inactive"]
    name: str | None = None
    demographic_info: dict[str, Any] = Field(default_factory=dict)
    medical_info: dict[str, Any] = Field(default_factory=dict)
    emergency_contact: dict[str, Any] = Field(default_factory=dict)
    practitioners: list[str] = Field(default_factory=list)
    health_managers: list[str] = Field(default_factory=list)
    source: SourcePatientIdentity | None = None
    legacy_user_id: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


def patient_response(document):
    """Explicit projection avoids exposing any fields from a legacy account."""
    return ClinicalPatientResponse(
        id=document["patient_id"], status=document["status"], name=document.get("name"),
        demographic_info=document.get("demographic_info") or {},
        medical_info=document.get("medical_info") or {},
        emergency_contact=document.get("emergency_contact") or {},
        practitioners=[str(value) for value in document.get("practitioners", [])],
        health_managers=[str(value) for value in document.get("health_managers", [])],
        source=document.get("source"), legacy_user_id=document.get("legacy_user_id"),
        created_at=document.get("created_at"), updated_at=document.get("updated_at"))

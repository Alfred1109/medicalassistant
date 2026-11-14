"""Bounded business export with selected credentials removed; patient data remains."""
import json
from datetime import datetime, timezone

EXPORT_COLLECTIONS = (
    "users", "organizations", "tags", "system_settings", "user_preferences",
    "consent_templates", "consent_documents", "followup_records", "rehab_plans",
    "exercises", "notifications", "audit_logs",
)
SECRET_KEYS = {"password", "password_hash", "hashed_password", "refresh_tokens", "avatar_bytes",
               "access_token", "secret", "api_key"}


ROW_LIMIT = 2000

def _clean(value):
    if isinstance(value, dict):
        return {key: _clean(item) for key, item in value.items() if key not in SECRET_KEYS}
    if isinstance(value, list):
        return [_clean(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if type(value).__name__ == "ObjectId":
        return str(value)
    return value


async def data_export_bytes(db) -> bytes:
    exported = {"generated_at": datetime.now(timezone.utc).isoformat(), "collections": {}}
    truncated = []
    for name in EXPORT_COLLECTIONS:
        rows = []
        has_more = False
        async for row in db[name].find({}):
            if len(rows) == ROW_LIMIT:
                has_more = True
                break
            rows.append(_clean(row))
        if has_more:
            truncated.append(name)
        exported["collections"][name] = {"count": len(rows), "capped": len(rows) >= ROW_LIMIT,
                                          "truncated": has_more, "rows": rows}
    exported["manifest"] = {
        "format": "rehab-business-export-v1", "artifact_type": "limited_credentials_filtered_business_export",
        "restorable": False, "consistency": "best_effort_sequential_reads",
        "collection_scope": list(EXPORT_COLLECTIONS), "per_collection_row_limit": ROW_LIMIT,
        "truncated_collections": truncated, "redacted_fields": sorted(SECRET_KEYS),
        "contains_patient_information": True,
        "privacy_notice": "Only selected credential fields are removed; patient-identifying information remains. This is not anonymized data.",
        "limitations": ["Selected collections only", "BSON types are converted to JSON",
                        "Indexes, files and recovery configuration are not included",
                        "Not a full backup and cannot be used for database recovery"],
    }
    return json.dumps(exported, ensure_ascii=False).encode()

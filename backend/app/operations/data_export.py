"""Bounded business export with selected credentials removed; patient data remains."""
import json
from datetime import datetime, timezone

from app.patients.repository import domain_mode as read_patient_domain_mode

# T53（域感知导出）：集合清单本身仍按 legacy 全量形态保留——canonical 模式下
# patients 读取分派与集合清单调整属患者域波次工作（users 将只承载账号，
# 患者临床记录在 clinical_patients / patient_account_links，届时需按波次把
# clinical_patients、patient_account_links 纳入清单并重新评估 users 的导出
# 语义），本模块只做感知记录（manifest.patient_domain_mode），不在此提前
# 改清单。legacy 模式下 users 即患者文档，当前清单语义不变。
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


async def _patient_domain_mode(db) -> str:
    """观察当前患者域开关（patients/repository.py 的 patient_domain_state）。

    导出是只读运维操作，域状态不可用绝不阻断导出：状态文档缺失/显式 legacy
    如实返回 legacy；状态损坏（未知 mode、错误 schema_version）或传输层读取
    失败一律标注 unknown，由 manifest 诚实披露，而不是猜测域或让导出失败。
    （域状态损坏走 PatientDomainError，传输层失败走 PyMongoError，均由
    repository.domain_mode 抛出，此处统一降级为 unknown。）
    """
    try:
        return await read_patient_domain_mode(db)
    except Exception:
        return "unknown"


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
        # T53（B4）：患者域感知——观察导出时刻的 patient_domain_state。
        # legacy: users 即患者文档（当前清单语义）；canonical: 患者临床记录在
        # clinical_patients / patient_account_links，users 仅账号，EXPORT_COLLECTIONS
        # 的域内调整属患者域波次工作（见文件头注释），未调整前 canonical 导出
        # 的患者覆盖范围不完整，以本字段为准解读。
        "patient_domain_mode": await _patient_domain_mode(db),
        "privacy_notice": "Only selected credential fields are removed; patient-identifying information remains. This is not anonymized data.",
        "limitations": ["Selected collections only", "BSON types are converted to JSON",
                        "Indexes, files and recovery configuration are not included",
                        "Not a full backup and cannot be used for database recovery",
                        "patient_domain_mode records the observed patient domain state; "
                        "under canonical mode the collection scope still reflects the "
                        "legacy wave until the domain-specific wave adjusts it "
                        "(unknown means the domain state could not be observed)"],
    }
    return json.dumps(exported, ensure_ascii=False).encode()

"""集成填报任务（Mongo 文档结构）。

试点隔离模型：medicalassistant 本地记录一次嵌入填报任务及其远端会话引用。
后续随访领域模型收敛时迁移（FU01/FU02 不在本轮）。

状态机：
    session_created → waiting_fill → submitted → confirmed
        └──────────────────────→ cancelled / failed
"""

from datetime import datetime
from typing import Any, Dict, Optional

# 任务状态
TASK_STATUS_SESSION_CREATED = "session_created"   # 远端会话已创建，尚未打开嵌入页
TASK_STATUS_WAITING_FILL = "waiting_fill"         # 嵌入页已打开（postMessage/轮询发现嵌入）
TASK_STATUS_SUBMITTED = "submitted"               # 远端报告已提交，尚未本地确认
TASK_STATUS_CONFIRMED = "confirmed"               # 已向远端核实答卷真实提交（待审阅）
TASK_STATUS_CANCELLED = "cancelled"               # 已取消（远端会话一并取消）
TASK_STATUS_FAILED = "failed"                     # 远端调用失败或会话失效

TASK_STATUSES = {
    TASK_STATUS_SESSION_CREATED, TASK_STATUS_WAITING_FILL, TASK_STATUS_SUBMITTED,
    TASK_STATUS_CONFIRMED, TASK_STATUS_CANCELLED, TASK_STATUS_FAILED,
}

COLLECTION_NAME = "integration_fill_tasks"


def utcnow() -> datetime:
    return datetime.utcnow()


class IntegrationFillTask:
    """integration_fill_tasks 集合的文档读写（字典驱动，便于 motor 直用）。"""

    def __init__(self, doc: Dict[str, Any]):
        self.doc = doc

    @classmethod
    def new_task(cls, *, patient_id: str, operator_id: str, operator_role: str,
                 remote_refs: Dict[str, Any], allowed_origin: str,
                 ma_task_ref: Optional[str], visit_code: Optional[str],
                 visit_name: Optional[str], ttl_seconds: Optional[int]) -> "IntegrationFillTask":
        now = utcnow()
        doc: Dict[str, Any] = {
            # 患者归属（本地患者用户 ID）
            "patient_id": patient_id,
            # 操作者主体引用：本地医生 + 远端操作者账号 ID（显式传入，不做自动映射）
            "operator": {
                "user_id": operator_id,
                "role": operator_role,
                "remote_user_id": remote_refs.get("remote_operator_user_id"),
            },
            # 远端 113.44 资源引用（project/center/subject/questionnaire 均为远端整数 ID）
            "remote_refs": {
                "project_id": remote_refs.get("project_id"),
                "center_id": remote_refs.get("center_id"),
                "subject_id": remote_refs.get("subject_id"),
                "questionnaire_id": remote_refs.get("questionnaire_id"),
                "remote_operator_user_id": remote_refs.get("remote_operator_user_id"),
            },
            "allowed_origin": allowed_origin,
            "visit_code": visit_code,
            "visit_name": visit_name,
            "ma_task_ref": ma_task_ref,
            "status": TASK_STATUS_SESSION_CREATED,
            # 远端会话引用：session_uuid 唯一标识；embed_token 只存哈希（明文一次下发不落库）
            "session": {
                "session_uuid": None,
                "embed_token_hash": None,
                "embed_url": None,
                "response_id": None,
                "expires_at": None,
            },
            # 确认证据：远端核实到的答卷状态与摘要
            "confirmation": None,
            "last_error": None,
            "created_at": now,
            "updated_at": now,
            "confirmed_at": None,
        }
        if ttl_seconds is not None:
            doc["ttl_seconds"] = ttl_seconds
        return cls(doc)

    @property
    def id(self) -> Optional[str]:
        raw = self.doc.get("_id")
        return str(raw) if raw is not None else None

    @property
    def status(self) -> str:
        return self.doc.get("status", "")

    def set_status(self, status: str) -> None:
        if status not in TASK_STATUSES:
            raise ValueError(f"未知的任务状态：{status}")
        self.doc["status"] = status
        self.doc["updated_at"] = utcnow()

    def record_remote_session(self, session_body: Dict[str, Any],
                              embed_token_hash: Optional[str]) -> None:
        session = self.doc["session"]
        session["session_uuid"] = session_body.get("session_uuid")
        session["embed_url"] = session_body.get("embed_url")
        session["response_id"] = session_body.get("response_id")
        session["expires_at"] = session_body.get("expires_at")
        session["embed_token_hash"] = embed_token_hash
        self.doc["updated_at"] = utcnow()

    def record_error(self, message: str) -> None:
        self.doc["last_error"] = message
        self.doc["updated_at"] = utcnow()

    def mark_confirmed(self, evidence: Dict[str, Any]) -> None:
        self.doc["confirmation"] = evidence
        self.doc["confirmed_at"] = utcnow()
        self.set_status(TASK_STATUS_CONFIRMED)


def hash_embed_token(token: str) -> str:
    """嵌入令牌只保存哈希；明文仅在创建响应中透传一次，不写日志不落库。"""
    import hashlib
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def serialize_task(doc: Dict[str, Any]) -> Dict[str, Any]:
    """API 输出：驼峰风格、不含任何凭证材料。"""
    session = doc.get("session") or {}
    confirmation = doc.get("confirmation")
    return {
        "id": str(doc["_id"]) if doc.get("_id") is not None else None,
        "patientId": doc.get("patient_id"),
        "operator": {
            "userId": (doc.get("operator") or {}).get("user_id"),
            "role": (doc.get("operator") or {}).get("role"),
        },
        "remoteRefs": {k: doc.get("remote_refs", {}).get(k) for k in (
            "project_id", "center_id", "subject_id", "questionnaire_id")},
        "visitCode": doc.get("visit_code"),
        "visitName": doc.get("visit_name"),
        "maTaskRef": doc.get("ma_task_ref"),
        "status": doc.get("status"),
        "session": {
            "sessionUuid": session.get("session_uuid"),
            "responseId": session.get("response_id"),
            "expiresAt": session.get("expires_at"),
        },
        "confirmation": confirmation,
        "lastError": doc.get("last_error"),
        "createdAt": doc.get("created_at").isoformat() + "Z" if doc.get("created_at") else None,
        "updatedAt": doc.get("updated_at").isoformat() + "Z" if doc.get("updated_at") else None,
        "confirmedAt": doc.get("confirmed_at").isoformat() + "Z" if doc.get("confirmed_at") else None,
    }


def serialize_embed_url(doc: Dict[str, Any]) -> Dict[str, Any]:
    session = doc.get("session") or {}
    return {
        "taskId": str(doc["_id"]) if doc.get("_id") is not None else None,
        "embedUrl": session.get("embed_url"),
        "sessionUuid": session.get("session_uuid"),
        "expiresAt": session.get("expires_at"),
        "allowedOrigin": doc.get("allowed_origin"),
    }

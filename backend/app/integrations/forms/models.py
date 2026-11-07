"""随访填报任务（FU01 正式模型，原试点 IntegrationFillTask 归位）。

设计稿 §3.3（docs/wp3-fu01-domain-design-draft-2026-11-07.md）：任务本质是
集成协议对象（embed_token、allowed_origin、远端会话均为协议状态），故保留在
integrations/forms/ 域内，不搬入业务模型目录；业务侧通过 `followup_visit_id`
外键 + 随访服务层唯一入口使用。

数据兼容（§3.1 零迁移）：
- 集合名保持 `integration_fill_tasks` 不变，存量/试点文档形状原样可读；
- 旧单会话字段 `session` 保留为「最新会话镜像」（兼容读取：旧字段优先），
  新 `fill_sessions[]` 数组渐进启用（每次会话追加一项，确认证据落会话条目）。

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

# 集合名不变：试点/存量数据零迁移（设计稿 §3.1）
COLLECTION_NAME = "integration_fill_tasks"


def utcnow() -> datetime:
    return datetime.utcnow()


def active_session(doc: Dict[str, Any]) -> Dict[str, Any]:
    """兼容读取任务的活动会话：旧单 `session` 字段优先，缺省回退 `fill_sessions` 末项。

    存量文档只有 `session`；新文档写入时两处镜像同步，故两条路径取到同一会话。
    """
    legacy = doc.get("session")
    if isinstance(legacy, dict) and legacy.get("session_uuid"):
        return legacy
    sessions = doc.get("fill_sessions")
    if isinstance(sessions, list) and sessions and isinstance(sessions[-1], dict):
        return sessions[-1]
    return legacy if isinstance(legacy, dict) else {}


class FollowUpFillTask:
    """integration_fill_tasks 集合的文档读写（字典驱动，便于 motor 直用）。"""

    def __init__(self, doc: Dict[str, Any]):
        self.doc = doc

    @classmethod
    def new_task(cls, *, patient_id: str, operator_id: str, operator_role: str,
                 remote_refs: Dict[str, Any], allowed_origin: str,
                 ma_task_ref: Optional[str], visit_code: Optional[str],
                 visit_name: Optional[str], ttl_seconds: Optional[int],
                 followup_visit_id: Optional[str] = None) -> "FollowUpFillTask":
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
            # FU01 S4：关联随访节点（正式外键；ma_task_ref 保留为远端自由引用兼容透传）
            "followup_visit_id": followup_visit_id,
            "status": TASK_STATUS_SESSION_CREATED,
            # 远端会话引用：session_uuid 唯一标识；embed_token 只存哈希（明文一次下发不落库）
            # `session` 为最新会话镜像（旧字段优先兼容读取），`fill_sessions` 为多会话正典
            "session": {
                "session_uuid": None,
                "embed_token_hash": None,
                "embed_url": None,
                "response_id": None,
                "expires_at": None,
            },
            "fill_sessions": [],
            # 确认证据：远端核实到的答卷状态与摘要（fill_sessions[].confirmation 同步落一份）
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
        entry = {
            "session_uuid": session_body.get("session_uuid"),
            "embed_url": session_body.get("embed_url"),
            "response_id": session_body.get("response_id"),
            "expires_at": session_body.get("expires_at"),
            "embed_token_hash": embed_token_hash,
            "confirmation": None,
        }
        sessions = self.doc.get("fill_sessions")
        if not isinstance(sessions, list):
            sessions = []
            self.doc["fill_sessions"] = sessions
        sessions.append(entry)
        # 旧单会话字段镜像（兼容读取：旧字段优先）
        self.doc["session"] = {k: entry[k] for k in (
            "session_uuid", "embed_token_hash", "embed_url", "response_id", "expires_at")}
        self.doc["updated_at"] = utcnow()

    def record_error(self, message: str) -> None:
        self.doc["last_error"] = message
        self.doc["updated_at"] = utcnow()

    def mark_confirmed(self, evidence: Dict[str, Any]) -> None:
        self.doc["confirmation"] = evidence
        self.doc["confirmed_at"] = utcnow()
        self.set_status(TASK_STATUS_CONFIRMED)
        # 会话化：确认证据同步落到 fill_sessions 末项（§3.2）；存量文档
        # 缺 fill_sessions 时以旧 session 字段补建条目，读取路径不变
        sessions = self.doc.get("fill_sessions")
        if not isinstance(sessions, list) or not sessions:
            sessions = [dict(self.doc.get("session") or {})]
            self.doc["fill_sessions"] = sessions
        entry = sessions[-1]
        entry["confirmation"] = evidence
        entry["response_id"] = evidence.get("response_id")
        if isinstance(self.doc.get("session"), dict):
            self.doc["session"]["response_id"] = evidence.get("response_id")


# 试点旧名兼容别名：调用方（service/tests）渐进切换，行为完全一致
IntegrationFillTask = FollowUpFillTask


def hash_embed_token(token: str) -> str:
    """嵌入令牌只保存哈希；明文仅在创建响应中透传一次，不写日志不落库。"""
    import hashlib
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def serialize_task(doc: Dict[str, Any]) -> Dict[str, Any]:
    """API 输出：驼峰风格、不含任何凭证材料。"""
    session = active_session(doc)
    confirmation = doc.get("confirmation")
    followup_visit_id = doc.get("followup_visit_id")
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
        # 新增字段（可选）：关联随访节点；无关联任务为 None，试点前端不受影响
        "followupVisitId": str(followup_visit_id) if followup_visit_id else None,
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
    session = active_session(doc)
    return {
        "taskId": str(doc["_id"]) if doc.get("_id") is not None else None,
        "embedUrl": session.get("embed_url"),
        "sessionUuid": session.get("session_uuid"),
        "expiresAt": session.get("expires_at"),
        "allowedOrigin": doc.get("allowed_origin"),
    }

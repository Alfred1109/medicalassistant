"""随访节点的共享语义（中性层）。

随访节点的两个语义被两侧共用：

- 并发语义：乐观并发版本过滤与冲突异常（所有节点写者共享同一版本口径）；
- 证据链语义：当前证据判定与提交快照归档（手工录入与外部表单填报同规则）。

表单集成层（integrations/forms）与随访服务层（services）此前互相 import：
集成层从服务层取并发/证据语义，服务层又从集成层取「答卷已审核上下文」
校验——形成环。共享语义下沉到底座后，两个方向都只依赖 core，
环被打断（服务层→集成层是主方向，保留）。
"""
from copy import deepcopy
from enum import Enum

from bson import ObjectId

from app.core.exceptions import AppBaseException


class FollowUpStatus(str, Enum):
    PENDING_SCHEDULE = "pending_schedule"
    SCHEDULED = "scheduled"
    AWAITING_FILL = "awaiting_fill"
    IN_REVIEW = "in_review"
    COMPLETED = "completed"
    CANCELED = "canceled"
    MISSED = "missed"
    OVERDUE = "overdue"
    LOST = "lost"
    RESCHEDULED = "rescheduled"


# legacy-shape: 历史状态拼写仅用于读取与统计，不扩展节点写入/流转契约。
FOLLOWUP_STATUS_ALIASES = {"done": "completed", "finished": "completed",
                           "cancelled": "canceled", "void": "canceled", "pending": "pending_schedule"}
FOLLOWUP_STATUSES = tuple(status.value for status in FollowUpStatus) + tuple(FOLLOWUP_STATUS_ALIASES)
FOLLOWUP_COMPLETION_POLICY = "conservative_non_void"
FOLLOWUP_COMPLETION_NOTE = "待临床确认：非作废节点均计入分母，仅完成节点计入分子，未终态及未知状态均按未完成统计。"


def followup_completion(counts, params=None):
    """One conservative, explicitly provisional policy shared by all metric readers.

    Only the documented default is supported; a future clinical policy requires
    an explicit implementation rather than silently accepting arbitrary params.
    """
    policy = (params or {}).get("completion_policy", FOLLOWUP_COMPLETION_POLICY)
    if policy != FOLLOWUP_COMPLETION_POLICY:
        raise ValueError("不支持的随访完成率口径")
    completed = total = excluded = 0
    for status, count in counts.items():
        canonical = FOLLOWUP_STATUS_ALIASES.get(status, status)
        if canonical == FollowUpStatus.CANCELED.value:
            excluded += count
            continue
        total += count
        if canonical == FollowUpStatus.COMPLETED.value:
            completed += count
    return {"policy": policy, "total": total, "completed": completed, "excluded": excluded,
            "value": round(completed / total, 4) if total else None,
            "note": FOLLOWUP_COMPLETION_NOTE}


# ---------------------------------------------------------------- 并发语义

def followup_conflict(message="随访已发生变更，请重新读取后操作"):
    return AppBaseException(message, status_code=409, error_code="FOLLOWUP_CONFLICT")


# legacy-shape: 存量形态，不随域切换删除
def followup_version_filter(doc):
    """兼容无版本的存量节点；所有节点写者共享同一乐观并发版本。"""
    return {"_id": doc["_id"], "status": doc["status"], "deleted": {"$ne": True},
            "mutation_version": doc.get("mutation_version", 0) or {"$in": [0, None]}}


# ---------------------------------------------------------------- 证据链语义

def followup_evidence_value(doc, key):
    if key in doc:
        return doc[key]
    # legacy-shape: 存量证据在 metadata 中，患者域切换不改变其读取契约。
    return (doc.get("metadata") or {}).get("result" if key == "follow_up_result" else key)


def current_followup_evidence(doc):
    """Resolve only unambiguous current evidence; never choose between mixed legacy sources."""
    manual = (followup_evidence_value(doc, "completion_data") or {}).get("source") == "manual_entry"
    external = followup_evidence_value(doc, "effective_response") or {}
    external_valid = bool(external.get("task_id") and external.get("response_id") is not None)
    marker = doc.get("current_evidence") or {}
    if manual and external:
        return {"source": "ambiguous"}
    source = "manual_entry" if manual else "external_form" if external_valid else "unknown"
    if marker.get("source") and marker["source"] != source:
        return {"source": "ambiguous"}
    if source == "unknown":
        return {"source": source}
    # legacy-shape: 无 current_evidence 标记的存量证据须显式注明，不随域切换删除。
    return {**marker, "source": source, **({"legacy": True} if not marker else {})}


def _submission_snapshot(doc):
    return {key: deepcopy(followup_evidence_value(doc, key)) for key in (
        "completion_data", "effective_response", "answers", "notes", "actual_date", "follow_up_result")}


# legacy-shape: 存量形态，不随域切换删除
def submission_history_with_legacy(doc):
    """Archive pre-marker evidence before replacing or returning it, without rewriting history."""
    history = deepcopy(doc.get("submission_history") or [])
    if (not (doc.get("current_evidence") or {}).get("submission_id")
            and (followup_evidence_value(doc, "completion_data") or followup_evidence_value(doc, "effective_response"))):
        history.append({"submission_id": str(ObjectId()), "source": "legacy_snapshot",
                        "observed_version": doc.get("mutation_version", 0) or 0,
                        "evidence_state": current_followup_evidence(doc),
                        "snapshot": _submission_snapshot(doc)})
    return history


def followup_submission_fields(doc, values, *, source, submitted_by, submitted_at, confirmation=None):
    """One current source plus append-only evidence snapshots, shared by manual and form writers."""
    marker = {"submission_id": str(ObjectId()), "source": source,
              "submitted_version": (doc.get("mutation_version", 0) or 0) + 1}
    snapshot = _submission_snapshot({**doc, **values})
    entry = {**marker, "submitted_by": submitted_by, "submitted_at": submitted_at,
             "snapshot": snapshot}
    if confirmation is not None:
        entry["confirmation"] = deepcopy(confirmation)
    return {"current_evidence": marker,
            "submission_history": [*submission_history_with_legacy(doc), entry]}

"""review 状态机收敛（R4-A1，批次 2 第 4 项）。

三份注释复制的 review 实现（clinical/workspace.review_report 原始版、
icf_service.review_assessment、icf_service.review_icf_report）收敛出共同
骨架：备注必填校验、mutation_version CAS、reviewed_snapshot 绑定、
review_history 追加、导出门闩判定。域差异以参数/回调表达：

- 快照构造留回调（snapshot_of）：clinical 的快照含 findings/extracted_values
  /sha256 等域形状，ICF 报告是 payload 深拷贝——状态机不认识内容形状。
- 错误码/文案参数化（conflict_code/conflict_message）：ICF 评估
  ICF_ASSESSMENT_CONFLICT、ICF 报告 ICF_REPORT_CONFLICT、clinical
  REPORT_CONFLICT 各域保留。
- 时间戳与历史事件形状由调用方注入（now / history_event），状态机只负责
  组装 $set、执行 CAS、追加历史与判定导出门闩。

冻结消费方登记（不迁移）：
- clinical/workspace.review_report 是三份实现的**原始版本**，且耦合
  clinical_reports 专属形态（content_revision 门闩、legacy_review 兼容分支、
  _write_report 事务与 _fence_report_access 授权栅栏）。属冻结消费方，
  不迁移本状态机——见 workspace.review_report 处的收敛状态注释。

review_assessment 的简化形态（无 reviewed_snapshot/review_history）通过
不传 snapshot_of/history_event 表达，与原实现字段集逐字一致。
"""
from copy import deepcopy

from fastapi import HTTPException

# 三处实现同源的 review 事件 action 标识
REVIEW_ACTION = "review"


def review_note(note):
    """备注必填校验（REVIEW_NOTE_REQUIRED 三处同源）：strip 后为空即 422。"""
    text = (note or "").strip()
    if not text:
        raise HTTPException(422, detail={"code": "REVIEW_NOTE_REQUIRED"})
    return text


def check_review_version(expected_version, current_version, *, code, message):
    """提交前版本预检：expected 必须是 int 且等于当前版本，否则 409。"""
    if type(expected_version) is not int or expected_version != current_version:
        raise review_conflict(code, message)


def review_conflict(code, message):
    return HTTPException(409, detail={"code": code, "message": message})


def review_event(actor_id, note, accepted, at, extra=None):
    """review_history 事件基座（action/actor_id/note/accepted 四键三处同源），
    域专属字段（clinical 的 content_revision/snapshot）经 extra 追加。"""
    event = {"action": REVIEW_ACTION, "at": at, "actor_id": actor_id,
             "note": note, "accepted": accepted}
    if extra:
        event.update(extra)
    return event


def append_review_history(row, event):
    """既有历史深拷贝后追加事件（不改动 row 内嵌列表的原对象）。"""
    return deepcopy(row.get("review_history") or []) + [event]


async def commit_versioned_change(collection, row, *, expected_version, changes,
                                  conflict_error, version_field="mutation_version",
                                  history_field=None, event=None, session=None,
                                  allow_missing_version=False):
    """Single-document CAS shared by review and disposition workflows.

    Each domain owns its states, authorization and operation receipts. Missing legacy
    versions can explicitly opt into zero-compatible missing/null first writes.
    """
    stored = row.get(version_field)
    current = 0 if stored is None else stored
    if (type(current) is not int or current < 0 or type(expected_version) is not int
            or expected_version != current):
        raise conflict_error()
    selector = {"_id": row["_id"], version_field: stored if allow_missing_version else expected_version}
    update = {"$set": {**changes, version_field: expected_version + 1}}
    if history_field is not None and event is not None:
        update["$push"] = {history_field: event}
    options = {"session": session} if session is not None else {}
    result = await collection.update_one(selector, update, **options)
    if result.matched_count != 1:
        raise conflict_error()


async def commit_review(collection, row, *, expected_version, accepted, note,
                        actor_id, now, code, message,
                        snapshot_of=None, history_event=None, extra_set=None):
    """CAS mutation_version 提交 review 状态迁移，返回落库的 $set 字段。

    - 统一 $set：review_status（reviewed/rejected）、review_note、reviewer_id、
      reviewed_at、mutation_version+1、updated_at。
    - snapshot_of 回调非 None 时绑定 reviewed_snapshot：通过保存当前内容
      快照、拒绝置 None（审核通过与导出门闩的绑定语义，见 export_gate）。
    - history_event 非 None 时整体替换 review_history 为「旧历史深拷贝 +
      新事件」（调用方经 append_review_history 构造）。
    - extra_set 折入调用方专属字段（保留给未来的域形态差异）。
    - CAS：`{"_id": row["_id"], "mutation_version": expected_version}` 未命中
      即并发已变化，抛 409（code/message 由调用方域决定）。调用方必须已通过
      check_review_version 预检——预检与 CAS 双保险语义与原始实现一致。
    """
    values = {"review_status": "reviewed" if accepted else "rejected",
              "review_note": note, "reviewer_id": actor_id, "reviewed_at": now,
              "mutation_version": expected_version + 1, "updated_at": now}
    if snapshot_of is not None:
        snapshot = snapshot_of(row)
        values["reviewed_snapshot"] = snapshot if accepted else None
    if history_event is not None:
        values["review_history"] = history_event
    if extra_set:
        values.update(extra_set)
    await commit_versioned_change(collection, row, expected_version=expected_version,
        changes=values, conflict_error=lambda: review_conflict(code, message))
    return values


def export_gate(row, snapshot):
    """导出门闩判定：review_status == reviewed 且 reviewed_snapshot 与当前
    内容快照一致（内容在审核后被改动即关闭导出）。ICF 报告的 exportable
    投影与 _require_exportable、clinical 的 _reviewed_findings 门闩共用本判定。"""
    return (row.get("review_status") == "reviewed"
            and row.get("reviewed_snapshot") == snapshot)

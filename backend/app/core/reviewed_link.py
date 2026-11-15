"""人工关联（reviewed link）公共基座（W2-E / R4-1.3）。

仓库里有若干处「人工关联」设施——把两个实体经人工核实后绑在一起，并在
链接文档内留下审计证据：

| 设施 | 关联的两端 | 实现位置 |
|---|---|---|
| 患者↔账号 | 临床患者 ↔ 本地登录账号 | `app/patients/repository.py` |
| 源患者↔本地患者 | 本地患者 ↔ 授权问卷平台患者 | `app/integrations/forms/patient_links.py` |
| 源表单↔用途 | 问卷表单版本 ↔ 本地用途 | `app/integrations/forms/form_bindings.py` |
| 外部身份↔本地账号 | OIDC subject ↔ 本地账号 | `app/integrations/identity/bindings.py` |

这些设施各自实现了**同构的四件事**：

1. **review 校验**：人工核实凭证（reviewer + evidence_reference）必填、限长；
2. **insert + 冲突映射**：唯一槽位已被占用即冲突，绝不隐式替换；
3. **disable 三态判定**：可禁用 / 不可禁用（已停用或冲突态）/ 不存在；
4. **审计条目 schema 适配**：链接文档内嵌追加式审计 list。

本模块**只**收敛这四件事，且一律参数化。各设施保留自己的：

- 源引用校验（远端版本/患者引用是否可信、origin 是否可信）；
- 反向复核（账号有效、患者有效、远端主体存在等）；
- 错误码与错误类型（`PatientDomainError` / `HTTPException` / `ValueError`）。

错误码族是设施契约，基座不产生任何错误码——调用方以无参工厂
（`missing_error` / `invalid_error` / `conflict_error`）把自己的错误实例
交给基座抛出。

**历史文档不动**：既有链接文档的审计条目有两种并存口径（operation 与
action），由 `audit_entry` 显式支持，不做数据迁移。
"""
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError


def validate_review(reviewer, evidence_reference, *, missing_error, invalid_error,
                    max_reviewer=200, max_evidence=1024):
    """校验人工核实凭证（review 校验），返回去空白后的 (reviewer, evidence_reference)。

    - missing_error / invalid_error：无参工厂，返回要抛出的异常。设施自带错误码
      （如 `PATIENT_REVIEW_REQUIRED` / `INVALID_PATIENT_REVIEW_REFERENCE`），
      基座不产生错误码。
    """
    if (not isinstance(reviewer, str) or not reviewer.strip()
            or not isinstance(evidence_reference, str) or not evidence_reference.strip()):
        raise missing_error()
    reviewer = reviewer.strip()
    evidence_reference = evidence_reference.strip()
    if len(reviewer) > max_reviewer or len(evidence_reference) > max_evidence:
        raise invalid_error()
    return reviewer, evidence_reference


async def insert_link(collection, document, *, conflict_queries, conflict_error, session=None):
    """写入人工关联文档：唯一槽位已被占用即冲突（预检 + 唯一索引双保险）。

    - conflict_queries：冲突判定查询列表，任一命中即冲突。设施把自身的互斥
      口径（同一患者/同一账号/同一来源键）写成查询，基座只负责「命中 → 冲突」
      的映射。
    - conflict_error：无参工厂，返回要抛出的异常（设施自带错误码）。

    并发竞态由唯一索引收口：`DuplicateKeyError` 与预检命中映射到同一个冲突
    错误，不向调用方暴露底层异常。
    """
    for query in conflict_queries:
        if await collection.find_one(query, session=session) is not None:
            raise conflict_error()
    try:
        await collection.insert_one(document, session=session)
    except DuplicateKeyError:
        raise conflict_error() from None
    return document


async def disable_link(collection, *, selector, active_filter, set_fields, audit_entry,
                       conflict_error, not_found_error=None, session=None):
    """把处于活跃态的关联文档置为终态并追加一条审计（disable 三态判定）。

    - selector：关联文档的身份范围，用于「不存在」判定；
    - active_filter：可禁用的附加条件（origin / 状态等，设施自有口径）；
    - set_fields：终态字段；
    - audit_entry：本次状态变更的审计条目；
    - conflict_error：文档存在但不可禁用（已停用 / 冲突态）时抛；
    - not_found_error：文档不存在时抛。省略则「不存在」也按 `conflict_error`
      抛（部分设施不区分这两者）。
    - session：可选事务会话。

    三态语义：可禁用 → 原子条件更新命中并回读更新后的文档；不可禁用 → 文档
    存在但不满足 `active_filter`；不存在 → 查无此文档。文档永不删除、永不复活。
    """
    updated = await collection.find_one_and_update(
        {**selector, **active_filter},
        {"$set": set_fields, "$push": {"audit": audit_entry}},
        return_document=ReturnDocument.AFTER, session=session)
    if updated is not None:
        return updated
    existing = await collection.find_one(selector, session=session)
    if existing is None and not_found_error is not None:
        raise not_found_error()
    raise conflict_error()


def audit_entry(*, at, operation=None, action=None, actor_id=None, reviewer=None,
                evidence_reference=None, extra=None):
    """组装一条关联审计条目（审计条目 schema 适配）。

    两种既有口径并存（历史文档不动）：

    - operation 口径（患者↔账号）：
      `{"reviewer", "evidence_reference", "operation", "at"}`
    - action + actor 口径（源患者↔本地患者、源表单↔用途）：
      `{"action", "actor_id", "at", "evidence_reference"}`
    - action + reviewer 口径（外部身份↔本地账号）：
      `{"action", "reviewer", "evidence_reference", "at"}`，不写 `actor_id`。

    传 `operation` 走 operation 口径（`reviewer` 必填）。传 `action` 时：
    只给 `reviewer`、不给 `actor_id` 走身份绑定口径；否则走 actor 口径。
    `evidence_reference` 缺省则不写该键。`extra` 追加设施专属字段
    （如 revoke 的 reason、身份绑定的 approved_role / authorization_revision）。
    """
    if operation is not None:
        entry = {"reviewer": reviewer, "evidence_reference": evidence_reference,
                 "operation": operation, "at": at}
    elif action is not None and reviewer is not None and actor_id is None:
        entry = {"action": action, "reviewer": reviewer}
        if evidence_reference is not None:
            entry["evidence_reference"] = evidence_reference
        entry["at"] = at
    elif action is not None:
        entry = {"action": action, "actor_id": actor_id, "at": at}
        if evidence_reference is not None:
            entry["evidence_reference"] = evidence_reference
    else:
        raise ValueError("audit entry requires operation or action")
    if extra:
        entry.update(extra)
    return entry

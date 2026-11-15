"""Pure Mongo query construction for process facts; no clinical scoring rules."""
from app.core.patient_access import patient_domain_mode
from app.patients.repository import PATIENTS

FOLLOWUP_STATUSES = ("pending_schedule", "scheduled", "awaiting_fill", "in_review",
                     "completed", "canceled", "missed", "overdue", "lost", "rescheduled")
PLAN_STATUSES = ("draft", "active", "completed", "cancelled", "canceled", "archived")
PUBLICATION_STATES = ("published", "unpublished", "withdrawn", "stopped", "invalid_reference")

# 患者引用核验载体按患者域分派（T66）：legacy 读 users（按 role 区分），
# canonical 读 clinical_patients（patients/repository.py PATIENTS 常量）。
# $lookup 集合与判定条件无法在管道执行中分派，由调用方在构造管道前解析
# 域（resolve_patient_domain），经 monitoring_pipeline(patient_domain=...) 传入。
PATIENT_USERS_COLLECTION = "users"
CANONICAL_PATIENTS_COLLECTION = PATIENTS

# monitoring_pipeline 接受的患者域取值；其余取值一律拒绝（不猜测域）。
PATIENT_REFERENCE_DOMAINS = ("legacy", "canonical")


async def resolve_patient_domain(db, *, session=None):
    """供异步调用方在构造管道前解析患者域（fail-closed）。

    monitoring_pipeline 是纯同步构造器，无法自行读取域开关；管道构造点
    （followup_service / rehab_publication_service 的 quality_process_snapshot
    链路）均处异步上下文，调用方先经本入口解析，再把结果以 patient_domain=
    传入。域状态读取失败/未知状态按 core/patient_access.patient_domain_mode
    原语义 fail-closed 上抛（503）——引用判定结果直接进入质控问题生成/
    复核决策，猜域回退会产出错误的 valid/not_found 结论，与统计展示类
    fail-safe unknown（analytics 口径，见 patient_domain_mode_safe）刻意不同。

    评估结论（redundancy review 批次 1）：本入口已是 patient_domain_mode 的
    直调薄层（fail-closed 语义保持，无重复包装可删）；仅把原函数内延迟
    import 收敛为模块级（core.patient_access 只依赖 patients/exceptions，
    无环）。函数本身保留为管道构造链路的具名域解析入口（调用方在
    followup_service / rehab_publication_service，属禁改在途文件）。
    """
    return await patient_domain_mode(db, session=session)


def _nonempty_string(value):
    return {"$and": [{"$eq": [{"$type": value}, "string"]},
        {"$gt": [{"$strLenCP": {"$trim": {"input": {"$cond": [{"$eq": [{"$type": value}, "string"]}, value, ""]}}}}, 0]}]}


def _required_publication_structure():
    items = {"$cond": [{"$eq": [{"$type": "$items_snapshot"}, "array"]}, "$items_snapshot", []]}
    return {"$and": [
        {"$eq": [{"$type": "$snapshot"}, "object"]},
        *[_nonempty_string("$snapshot." + field) for field in ("name", "description", "goal")],
        {"$eq": [{"$type": "$snapshot.start_date"}, "date"]},
        {"$or": [{"$in": [{"$type": "$snapshot.end_date"}, ["missing", "null"]]},
            {"$and": [{"$eq": [{"$type": "$snapshot.end_date"}, "date"]},
                       {"$gte": ["$snapshot.end_date", "$snapshot.start_date"]}]}]},
        {"$eq": [{"$type": "$published_at"}, "date"]},
        _nonempty_string("$published_by"), _nonempty_string("$confirmation_note"),
        {"$in": [{"$type": "$publication_revision"}, ["int", "long"]]},
        {"$gt": ["$publication_revision", 0]},
        {"$gt": [{"$size": items}, 0]}, {"$lte": [{"$size": items}, 200]},
        {"$allElementsTrue": [{"$map": {"input": items, "as": "item", "in": {"$and": [
            {"$eq": [{"$type": "$$item"}, "object"]}, _nonempty_string("$$item.name"),
            {"$in": ["$$item.intervention_type", ["diet", "exercise", "medication", "psychology"]]},
            {"$regexMatch": {"input": {"$cond": [{"$eq": [{"$type": "$$item.item_id"}, "string"]}, "$$item.item_id", ""]}, "regex": "^[0-9a-f]{24}$"}},
        ]}}}]},
    ]}


def _status_expression(known):
    return {"$switch": {"branches": [
        {"case": {"$in": [{"$type": "$status"}, ["missing", "null"]]}, "then": "__missing__"},
        {"case": {"$ne": [{"$type": "$status"}, "string"]}, "then": "__invalid__"},
        {"case": {"$in": ["$status", list(known)]}, "then": "$status"},
    ], "default": "__unknown__"}}


def _publication_stages(versions_collection):
    return [
        {"$set": {"_qc_pointer": {"$convert": {"input": {"$cond": [{"$eq": [{"$type": "$published_version_id"}, "string"]}, "$published_version_id", None]}, "to": "objectId", "onError": None, "onNull": None}}}},
        {"$lookup": {"from": versions_collection, "let": {"pointer": "$_qc_pointer", "plan": {"$convert": {"input": "$_id", "to": "string", "onError": None}}, "patient": "$patient_id"},
            "pipeline": [{"$match": {"$expr": {"$and": [
                {"$ne": ["$$pointer", None]}, {"$ne": ["$$plan", None]}, {"$eq": ["$_id", "$$pointer"]},
                {"$eq": ["$plan_id", "$$plan"]}, {"$eq": ["$patient_id", "$$patient"]},
                {"$eq": ["$workflow", "patient_publication"]}, {"$eq": ["$status", "published"]},
                _required_publication_structure(),
            ]}}}, {"$project": {"_id": 1}}], "as": "_qc_version"}},
        {"$lookup": {"from": versions_collection, "let": {"plan": {"$convert": {"input": "$_id", "to": "string", "onError": None}}, "patient": "$patient_id", "history": "$has_publication_history"},
            "pipeline": [{"$match": {"$expr": {"$and": [
                {"$eq": ["$$history", True]}, {"$ne": ["$$plan", None]}, {"$eq": ["$plan_id", "$$plan"]},
                {"$eq": ["$patient_id", "$$patient"]}, {"$eq": ["$workflow", "patient_publication"]},
                {"$eq": ["$status", "withdrawn"]}, _required_publication_structure(),
            ]}}}, {"$limit": 1}, {"$project": {"_id": 1}}], "as": "_qc_withdrawn"}},
        {"$set": {"_qc_publication": {"$switch": {"branches": [
            {"case": {"$in": ["$status", ["cancelled", "canceled", "archived"]]}, "then": "stopped"},
            {"case": {"$eq": [{"$size": "$_qc_version"}, 1]}, "then": "published"},
            {"case": {"$in": [{"$type": "$published_version_id"}, ["missing", "null"]]},
             "then": {"$cond": [{"$eq": ["$has_publication_history", True]},
                 {"$cond": [{"$eq": [{"$size": "$_qc_withdrawn"}, 1]}, "withdrawn", "invalid_reference"]}, "unpublished"]}},
        ], "default": "invalid_reference"}}}},
    ]


def _patient_reference_stages(patient_domain="legacy"):
    """患者引用核验阶段，按患者域（patient_domain）分派 $lookup 载体与判定条件。

    - legacy（users）：双键查找（_id 原值或 ObjectId 形态），valid = 命中恰
      一篇（含停用用户）；开单资格另要求 is_active。即 legacy 停用用户的
      引用仍是 valid，只是 issue_eligible=False。
    - canonical（clinical_patients）：主键 patient_id 字符串直查（迁移与
      create_from_source 均保证 patient_id == str(_id)，唯一索引
      clinical_patient_id_unique 保证同一 patient_id 至多一篇）。clinical
      文档没有 role/is_active，可用性载体是 status。判定口径变化（T66）：
      valid 要求命中恰一篇且 status=="active" 且引用一致——停用临床记录按
      不可用处理，如实落入 not_found（canonical 绝不复活 legacy 关系，见
      patients/repository.py 模块头），而非 legacy 的 valid-but-ineligible。
    - ambiguous 分支两域都保留：canonical 下由唯一索引天然不可达（保留分支
      以维持与 legacy 判定枚举同构，并在索引缺失/误配的库上仍给出诚实信号，
      不做静默假设）。
    """
    # domain-dispatch: 迁移完成后可删
    if patient_domain == "legacy":
        return [
            {"$set": {"_qc_patient_oid": {"$convert": {"input": "$patient_id", "to": "objectId", "onError": None, "onNull": None}}}},
            {"$lookup": {"from": PATIENT_USERS_COLLECTION, "let": {"raw": "$patient_id", "oid": "$_qc_patient_oid"}, "pipeline": [
                {"$match": {"role": "patient", "$expr": {"$or": [
                    {"$eq": ["$_id", "$$raw"]}, {"$and": [{"$ne": ["$$oid", None]}, {"$eq": ["$_id", "$$oid"]}]}
                ]}}}, {"$project": {"_id": 1, "is_active": 1}}], "as": "_qc_patient"}},
            {"$set": {"_qc_patient_reference": {"$switch": {"branches": [
                {"case": {"$in": [{"$type": "$patient_id"}, ["missing", "null"]]}, "then": "missing"},
                {"case": {"$ne": [{"$type": "$patient_id"}, "string"]}, "then": "invalid"},
                {"case": {"$gt": [{"$size": "$_qc_patient"}, 1]}, "then": "ambiguous"},
                {"case": {"$eq": [{"$size": "$_qc_patient"}, 1]}, "then": "valid"},
            ], "default": "not_found"}}}},
            {"$set": {"_qc_issue_eligible": {"$and": [
                {"$eq": [{"$size": "$_qc_patient"}, 1]},
                {"$eq": [{"$type": "$patient_id"}, "string"]},
                {"$ne": ["$_qc_patient_oid", None]},
                {"$eq": ["$patient_id", {"$toString": "$_qc_patient_oid"}]},
                {"$eq": [{"$arrayElemAt": ["$_qc_patient.is_active", 0]}, True]},
                {"$eq": [{"$type": "$_id"}, "objectId"]},
            ]}}},
        ]
    # domain-dispatch: 迁移完成后可删
    if patient_domain == "canonical":
        return [
            # canonical 主键即 patient_id 字符串，无需 legacy 的 ObjectId 双键
            # 转换（_qc_patient_oid 为 legacy users._id 导航工件，canonical 不设）
            {"$lookup": {"from": CANONICAL_PATIENTS_COLLECTION, "let": {"raw": "$patient_id"}, "pipeline": [
                {"$match": {"$expr": {"$eq": ["$patient_id", "$$raw"]}}},
                {"$project": {"_id": 1, "patient_id": 1, "status": 1}}], "as": "_qc_patient"}},
            {"$set": {"_qc_patient_reference": {"$switch": {"branches": [
                {"case": {"$in": [{"$type": "$patient_id"}, ["missing", "null"]]}, "then": "missing"},
                {"case": {"$ne": [{"$type": "$patient_id"}, "string"]}, "then": "invalid"},
                # 唯一索引 clinical_patient_id_unique 使 size>1 不可达；分支保留
                # （同构 + 索引误配时仍诚实报 ambiguous），不静默吞掉
                {"case": {"$gt": [{"$size": "$_qc_patient"}, 1]}, "then": "ambiguous"},
                {"case": {"$and": [
                    {"$eq": [{"$size": "$_qc_patient"}, 1]},
                    # clinical 文档无 is_active，可用性载体是 status=="active"
                    {"$eq": [{"$arrayElemAt": ["$_qc_patient.status", 0]}, "active"]},
                    # 引用一致：命中文档主键即 patient_id 本身（$match 已保证，
                    # 显式复核以维持「valid = 存在且一致」的可读口径）
                    {"$eq": [{"$arrayElemAt": ["$_qc_patient.patient_id", 0]}, "$patient_id"]},
                ]}, "then": "valid"},
            # default 覆盖：未命中（size==0）与命中但 status!="active"
            # （停用临床记录按不可用处理，绝不复活）——canonical 口径下
            # 不存在 legacy 的 valid-but-ineligible 状态
            ], "default": "not_found"}}}},
            {"$set": {"_qc_issue_eligible": {"$and": [
                {"$eq": [{"$size": "$_qc_patient"}, 1]},
                {"$eq": [{"$type": "$patient_id"}, "string"]},
                {"$eq": [{"$arrayElemAt": ["$_qc_patient.status", 0]}, "active"]},
                # 引用一致性由 $match（patient_id == $$raw）保证，无需 legacy
                # 的 oid/toString 复核；来源文档 _id 为 ObjectId 的要求不变
                {"$eq": [{"$type": "$_id"}, "objectId"]},
            ]}}},
        ]
    raise ValueError(f"unsupported patient_domain: {patient_domain!r}"
                     f"（合法取值: {PATIENT_REFERENCE_DOMAINS}；"
                     "调用方须经 resolve_patient_domain 解析后传入，不猜测域）")


def monitoring_pipeline(kind, patient_ids, *, start_date=None, end_date=None, skip=0, limit=20,
                        include_items=False, versions_collection="rehab_plan_versions",
                        patient_domain="legacy"):
    """Scope is applied before every count, lookup and page; windows are half open.

    Missing/invalid date counts cover the entire authorized source scope. They
    cannot be attributed to a date window and are never silently assigned one.

    patient_domain（T66）：患者引用核验的载体域（"legacy"=users / "canonical"=
    clinical_patients）。默认 "legacy" 保持既有调用方（未传该参的
    quality_process_snapshot 链路）行为逐字不变；canonical 须由异步调用方在
    构造前经 resolve_patient_domain 解析后显式传入——本构造器是纯同步函数，
    不读域开关，也不猜测域（其余取值一律 ValueError）。
    """
    if patient_domain not in PATIENT_REFERENCE_DOMAINS:
        raise ValueError(f"unsupported patient_domain: {patient_domain!r}"
                         f"（合法取值: {PATIENT_REFERENCE_DOMAINS}）")
    field = "scheduled_date" if kind == "followup" else "created_at"
    known = FOLLOWUP_STATUSES if kind == "followup" else PLAN_STATUSES
    base = {"deleted": {"$ne": True}}
    if patient_ids is not None:
        base["patient_id"] = {"$in": list(patient_ids)}
    date_filter = {}
    if start_date is not None:
        date_filter["$gte"] = start_date
    if end_date is not None:
        date_filter["$lt"] = end_date
    selected = [{"$match": {field: {"$type": "date", **date_filter}}}] if date_filter else []
    selected += [{"$set": {"_qc_status": _status_expression(known)}}]
    metrics = {"statuses": selected + [{"$group": {"_id": "$_qc_status", "count": {"$sum": 1}}}],
               "total": selected + [{"$count": "count"}]}
    if kind == "rehab_plan":
        metrics["publications"] = selected + _publication_stages(versions_collection) + [{"$group": {"_id": "$_qc_publication", "count": {"$sum": 1}}}]
    if include_items:
        projection = {"_id": 0, "source_type": {"$literal": kind}, "source_id": {"$convert": {"input": "$_id", "to": "string", "onError": "[unaddressable]", "onNull": "[unaddressable]"}},
            "source_reference_state": {"$cond": [{"$eq": [{"$type": "$_id"}, "objectId"]}, "valid", "unaddressable"]},
            "patient_id": {"$cond": [{"$eq": [{"$type": "$patient_id"}, "string"]}, "$patient_id", None]},
            "status": "$_qc_status", "date": {"$cond": [{"$eq": [{"$type": "$" + field}, "date"]}, "$" + field, None]},
            "patient_reference_state": "$_qc_patient_reference",
            "issue_eligible": "$_qc_issue_eligible",
            "date_quality": {"$switch": {"branches": [
                {"case": {"$eq": [{"$type": "$" + field}, "date"]}, "then": "valid"},
                {"case": {"$in": [{"$type": "$" + field}, ["missing", "null"]]}, "then": "missing"},
            ], "default": "invalid"}}}
        if kind == "rehab_plan":
            projection["publication_state"] = "$_qc_publication"
        metrics["items"] = selected + [{"$sort": {field: -1, "_id": -1}}, {"$skip": skip}, {"$limit": limit}] + (
            _publication_stages(versions_collection) if kind == "rehab_plan" else []) + [{"$project": projection}]
    metrics.update(scope=[{"$count": "count"}],
                   patient_references=[{"$group": {"_id": "$_qc_patient_reference", "count": {"$sum": 1}}}],
                   dates=[{"$group": {"_id": {"$type": "$" + field}, "count": {"$sum": 1}}}])
    return [{"$match": base}] + _patient_reference_stages(patient_domain) + [{"$facet": metrics}]

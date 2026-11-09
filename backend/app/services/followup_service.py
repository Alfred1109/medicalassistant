"""随访服务（FU01 S2 唯一随访服务入口）

从 HealthRecordService 拆出的随访方法组（设计稿 docs/wp3-fu01-domain-design-draft-2026-11-07.md
§五 S2）：create / get / update / list / upcoming / by-health-record / complete /
cancel / reschedule 全部收敛到本服务，路由层（health_record_router、doctor_router、
health_manager_router）一律转调本服务，禁止直连 followup_records 集合。

共享辅助（_FOLLOWUP_FORMAL_FIELDS / followup_from_mongo / map_followup_record_to_response）
随方法组下沉到本模块——它们耦合 models.FollowUpRecord 的存储形状与 MedicalTimeline
落库行为，属于服务层实现细节，不放 schemas（schemas 保持纯契约）；
health_record_service 保留健康档案域，随访统计经本服务转调。

取消/改期语义（设计稿 §2.2）：cancel(reschedule_date) = 关闭当前节点（status=canceled，
拼写与 FollowUpStatus.CANCELED 归一）并新建节点（previous_visit_id 关联），
不再在原节点上把状态改写为 rescheduled（原 models.cancel_followup 缺陷）。

FU01 S5（审阅与证据链，设计稿 §4.3，D-2 默认决策见实施记录 2026-11-09）：
- complete 端点降级为「无表单随访的手工结果录入」：写 answers/notes 后节点转
  in_review（不再直达 completed），completion_data 带显式 source=manual_entry 标记
  （区别于外部表单填报），写审计，进入与填报答卷相同的待审阅流程；
- completed 只能由 review 审阅通过置达；手工录入清除旧 effective_response
  当前引用，保留历史任务（有效答卷只能来自任务 confirm 路径）。

FU01 S6（复评链与有效答卷，设计稿 §4.4）：re_evaluate 新建节点复制处方配置并
写 previous/next_visit_id 链，原节点不覆盖不改写（A06）；select_effective_response
实现有效答卷选择规则（已确认、未作废、属本节点、取最新修订）。

D-3 状态机（结构先行，口径待 FU03 确认）：mark_overdue（逾期可补救）与
mark_lost（失访终态认定）只提供状态转换与证据字段，不实现定时调度与阈值口径。
"""
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta, timezone
from copy import deepcopy
from hashlib import sha256
import re
from bson import encode
from app.core.exceptions import AppBaseException
from app.db.transactions import run_followup_transaction
from app.schemas.audit_log import AuditLogCreate
from motor.motor_asyncio import AsyncIOMotorDatabase
from bson import ObjectId

from app.models.health_record import FollowUpRecord, MedicalTimeline
from app.schemas.followup import (
    FollowUpRecordCreate, FollowUpRecordUpdate, FollowUpRecordResponse,
    CompleteFollowUpRequest, CancelFollowUpRequest, RescheduleFollowUpRequest,
    ReviewDecision, ReviewFollowUpRequest, ReEvaluateFollowUpRequest,
    FollowUpWorkbenchItem, FollowUpWorkbenchPage,
)


# FollowUpRecordDB 存储模型的正式扩展字段（FU01 S1/S3 起直接落顶层，全部 Optional）。
# 存量文档（e7e8706 缝合层约定）对应数据在 metadata.* 下，读取时兼容回退；
# models.FollowUpRecord.from_mongo 按显式关键字构造，顶层未知键会抛 TypeError，
# 故读取前先摘出（见 followup_from_mongo）。
_FOLLOWUP_FORMAL_FIELDS = (
    "provider_id", "template_id", "reminder_before",
    "completion_data", "cancellation_data", "next_follow_up_id",
    "follow_up_result",
    # FU01 S3 节点字段增强（schemas/followup.py FollowUpRecordDB）+ 迁移打标，
    # 同样只在读取侧摘出挂回，models.FollowUpRecord 构造器不认识这些顶层键
    "visit_code", "form_binding", "fill_task_ids", "effective_response",
    "review", "previous_visit_id", "next_visit_id",
    "legacy_source", "deleted", "deleted_at", "deleted_by",
    "mutation_version", "cancellation_operation", "completion_operation", "reschedule_operation",
    "review_operation", "re_evaluate_operation",
    "current_evidence", "submission_history",
    "_reminder_fence",  # Internal concurrency fence, never a clinical revision.
    "_access_fence",  # Internal source/authorization fence, not patient content.
)


# 填报任务集合名（与 integrations/forms/models.COLLECTION_NAME 一致；
# 不做模块级导入以避免 forms service -> followup_service 的既有依赖成环）
_FILL_TASKS_COLLECTION = "integration_fill_tasks"

# 有效答卷认可的远端状态（设计稿 §2.1 ③：已提交、未作废；restored=作废后恢复，
# 视为有效；draft 不应出现在 confirmed 任务的确认证据中，防御性排除）
_EFFECTIVE_REMOTE_STATUSES = {"submitted", "restored", None}


def followup_conflict(message="随访已发生变更，请重新读取后操作"):
    return AppBaseException(message, status_code=409, error_code="FOLLOWUP_CONFLICT")


def _as_optional_str(value):
    """ObjectId / str 兼容转 Optional[str]（响应契约字段均为 str）。"""
    return None if value is None else str(value)


def followup_version_filter(doc):
    """兼容无版本的存量节点；所有节点写者共享同一乐观并发版本。"""
    return {"_id": doc["_id"], "status": doc["status"], "deleted": {"$ne": True},
            "mutation_version": doc.get("mutation_version", 0) or {"$in": [0, None]}}


def _request_fingerprint(kind, payload):
    # BSON 编码统一日期为UTC毫秒，与实际Mongo持久化精度保持一致。
    return sha256(encode({"kind": kind, "payload": payload})).hexdigest()


def _evidence_value(doc, key):
    if key in doc:
        return doc[key]
    return (doc.get("metadata") or {}).get("result" if key == "follow_up_result" else key)


def current_followup_evidence(doc):
    """Resolve only unambiguous current evidence; never choose between mixed legacy sources."""
    manual = (_evidence_value(doc, "completion_data") or {}).get("source") == "manual_entry"
    external = _evidence_value(doc, "effective_response") or {}
    external_valid = bool(external.get("task_id") and external.get("response_id") is not None)
    marker = doc.get("current_evidence") or {}
    if manual and external:
        return {"source": "ambiguous"}
    source = "manual_entry" if manual else "external_form" if external_valid else "unknown"
    if marker.get("source") and marker["source"] != source:
        return {"source": "ambiguous"}
    if source == "unknown":
        return {"source": source}
    return {**marker, "source": source, **({"legacy": True} if not marker else {})}


def _submission_snapshot(doc):
    return {key: deepcopy(_evidence_value(doc, key)) for key in (
        "completion_data", "effective_response", "answers", "notes", "actual_date", "follow_up_result")}


def submission_history_with_legacy(doc):
    """Archive pre-marker evidence before replacing or returning it, without rewriting history."""
    history = deepcopy(doc.get("submission_history") or [])
    if (not (doc.get("current_evidence") or {}).get("submission_id")
            and (_evidence_value(doc, "completion_data") or _evidence_value(doc, "effective_response"))):
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


def select_effective_response(fill_task_docs):
    """有效答卷选择规则（FU01 S6，设计稿 §2.1 ③、§五 S6）。

    规则：任务已确认（confirmed = 远端已提交且经本地核实）、答卷未作废
    （remote_status 非 voided）、任务属于目标节点（调用方负责过滤），
    取最新修订（revision 降序），修订相同取最晚 submitted_at。

    返回选定结果及可解释的选择依据；无有效答卷返回 None。
    纯函数：只读入参，不触库、不回写节点（effective_response 仍只能由
    任务 confirm 路径写入，见 integrations/forms/service.py）。
    """
    candidates = []
    for doc in fill_task_docs or []:
        if doc.get("status") != "confirmed":
            continue  # 已提交但未核实（submitted）不算数，设计稿 §2.2 耦合规则
        sessions = doc.get("fill_sessions") or []
        confirmations = [s.get("confirmation") for s in sessions if s.get("confirmation")]
        if not confirmations:
            continue
        confirmation = confirmations[-1]  # 同任务多会话取最后一次确认
        remote_status = confirmation.get("remote_status")
        if remote_status not in _EFFECTIVE_REMOTE_STATUSES:
            continue  # 已作废（voided）答卷不参与选定
        candidates.append({
            "task_id": str(doc.get("_id")),
            "response_id": confirmation.get("response_id"),
            "revision": confirmation.get("revision") or 0,
            "submitted_at": confirmation.get("submitted_at"),
            "remote_status": remote_status,
            "visit_code": confirmation.get("visit_code"),
        })
    if not candidates:
        return None
    # 修订降序、提交时间降序（ISO 字符串字典序与时间序一致）
    best = max(candidates, key=lambda c: (c["revision"], str(c["submitted_at"] or "")))
    return {
        **best,
        "selection_basis": {
            "rule": "confirmed+not_voided+latest_revision",
            "candidates_considered": len(candidates),
            "candidate_task_ids": [c["task_id"] for c in candidates],
        },
    }


# -------- 读取/映射兼容层（FU01 S1 引入，S2 起随随访域迁入本模块） --------

def followup_from_mongo(mongo_doc) -> Optional[FollowUpRecord]:
    """从 followup_records 集合文档构建 FollowUpRecord。

    models.FollowUpRecord.from_mongo 按显式关键字参数构造，文档出现存储模型
    未声明的顶层键会抛 TypeError；S1 起正式扩展字段（_FOLLOWUP_FORMAL_FIELDS）
    直接落顶层，读取时先摘出、再 setattr 挂回实例，供映射层按
    「正式字段优先、metadata.* 回退」取值（存量 demo 文档不迁移、不破坏）。
    """
    if not mongo_doc:
        return None
    doc = dict(mongo_doc)
    formal = {}
    for field in _FOLLOWUP_FORMAL_FIELDS:
        if field in doc:
            formal[field] = doc.pop(field)
    record = FollowUpRecord.from_mongo(doc)
    for field, value in formal.items():
        setattr(record, field, value)
    return record


def map_followup_record_to_response(followup_record: FollowUpRecord) -> FollowUpRecordResponse:
    """将随访记录对象映射为响应对象

    扩展数据取值兼容（FU01 S1）：正式字段（顶层）优先，
    缺省回退存量文档的 metadata.*（e7e8706 缝合层约定），对外响应形状不变。

    Args:
        followup_record: 随访记录对象

    Returns:
        FollowUpRecordResponse: 随访记录响应对象
    """
    metadata = followup_record.metadata or {}

    def formal_or_meta(field: str, meta_key: str):
        if hasattr(followup_record, field):
            return getattr(followup_record, field)
        return metadata.get(meta_key)

    reminder_before = formal_or_meta("reminder_before", "reminder_before")
    if reminder_before is None:
        # 存量文档无正式字段与 metadata.reminder_before 时沿用原兜底（提醒设置）
        reminder_before = followup_record.reminder_settings.get("days_before") if hasattr(followup_record, 'reminder_settings') and followup_record.reminder_settings else None

    return FollowUpRecordResponse(
        id=followup_record._id,
        patient_id=followup_record.patient_id,
        created_by=followup_record.created_by,
        follow_up_type=followup_record.follow_up_type,
        scheduled_date=followup_record.scheduled_date,
        provider_id=formal_or_meta("provider_id", "provider_id") or followup_record.created_by,  # 无正式字段时使用创建者
        description=followup_record.notes,  # 存储字段 notes -> 响应字段 description
        questions=followup_record.questions,
        related_records=followup_record.health_record_ids,
        metadata=followup_record.metadata,
        created_at=followup_record.created_at,
        updated_at=followup_record.updated_at,
        status=followup_record.status,
        mutation_version=getattr(followup_record, "mutation_version", 0) or 0,
        actual_date=followup_record.actual_date,
        answers=followup_record.answers,
        notes=followup_record.notes,
        follow_up_result=formal_or_meta("follow_up_result", "result"),
        next_follow_up_id=formal_or_meta("next_follow_up_id", "next_follow_up_id"),
        template_id=formal_or_meta("template_id", "template_id"),
        reminder_before=reminder_before,
        completion_data=formal_or_meta("completion_data", "completion_data"),
        cancellation_data=formal_or_meta("cancellation_data", "cancellation_data"),
        # FU01 S5/S6 响应扩展：审阅证据链、有效答卷、复评链与节点关联键
        # （ObjectId 兼容转 str；fill_task_ids 反向索引以字符串列表出参）
        visit_code=formal_or_meta("visit_code", "visit_code"),
        review=formal_or_meta("review", "review"),
        effective_response=formal_or_meta("effective_response", "effective_response"),
        fill_task_ids=[str(v) for v in (getattr(followup_record, "fill_task_ids", None) or [])],
        previous_visit_id=_as_optional_str(formal_or_meta("previous_visit_id", "previous_visit_id")),
        next_visit_id=_as_optional_str(formal_or_meta("next_visit_id", "next_visit_id")),
        current_evidence=current_followup_evidence({
            "completion_data": formal_or_meta("completion_data", "completion_data"),
            "effective_response": formal_or_meta("effective_response", "effective_response"),
            "current_evidence": getattr(followup_record, "current_evidence", None),
        }) if followup_record.status in {"in_review", "completed"} else None,
        submission_history=getattr(followup_record, "submission_history", None) or [],
    )


class FollowupService:
    """随访服务类：followup_records 集合的唯一业务入口（FU01 S2）"""

    def __init__(self, db: AsyncIOMotorDatabase):
        """初始化服务类

        Args:
            db: MongoDB数据库连接
        """
        self.db = db
        # 随访记录集合（唯一集合名 followup_records）
        self.followup_records = db[FollowUpRecord.collection_name]
        # 医疗时间线集合（随访节点联动时间线）
        self.medical_timelines = db[MedicalTimeline.collection_name]

    # -------- 创建 / 查询 --------

    async def quality_source(self, followup_id, session=None):
        """Internal source reference for authorized quality workflows."""
        if not ObjectId.is_valid(followup_id):
            return None
        return await self.followup_records.find_one({"_id": ObjectId(followup_id),
            "deleted": {"$ne": True}}, session=session)

    async def fence_quality_source(self, document, session):
        value = document.get("_access_fence", 0)
        if type(value) is not int or value < 0:
            raise AppBaseException("随访并发状态异常", status_code=503,
                                   error_code="QUALITY_SOURCE_FENCE_INVALID")
        result = await self.followup_records.update_one({"_id": document["_id"],
            "deleted": {"$ne": True}}, {"$inc": {"_access_fence": 1}}, session=session)
        if result.matched_count != 1:
            raise AppBaseException("随访来源已变化，请重新读取", status_code=409,
                                   error_code="QUALITY_SOURCE_CHANGED")

    async def quality_process_snapshot(self, patient_ids, **options):
        from app.services.quality_process_queries import monitoring_pipeline
        rows = await self.followup_records.aggregate(
            monitoring_pipeline("followup", patient_ids, **options)).to_list(length=1)
        return rows[0] if rows else {}

    async def ensure_reminder_scan_index(self):
        await self.followup_records.create_index([("status", 1), ("scheduled_date", 1)], name="reminder_due_scan")

    async def get_reminder_source(self, followup_id, *, session=None):
        """Internal source read; external callers still apply object authorization."""
        return await self.followup_records.find_one({"_id": ObjectId(followup_id)}, session=session)

    def reminder_candidate_cursor(self, now):
        return self.followup_records.find({"deleted": {"$ne": True},
            "status": {"$in": ["scheduled", "awaiting_fill"]},
            "scheduled_date": {"$gt": now, "$lte": now + timedelta(hours=24)}}).sort(
                [("scheduled_date", 1), ("_id", 1)])

    async def fence_reminder_source(self, document, session):
        value = document.get("_reminder_fence", 0)
        if type(value) is not int or value < 0:
            raise AppBaseException("提醒并发字段无效", status_code=503,
                                   error_code="REMINDER_INVALID_FENCE")
        await self.followup_records.update_one({"_id": document["_id"]},
            {"$inc": {"_reminder_fence": 1}}, session=session)

    async def list_workbench(
        self, *, patient_ids: Optional[List[str]], patient_id: Optional[str] = None,
        status: Optional[List[str]] = None, follow_up_type: Optional[str] = None,
        start_date: Optional[datetime] = None, end_date: Optional[datetime] = None,
        patient_name: Optional[str] = None, skip: int = 0, limit: int = 20,
        sort_order: str = "desc",
    ) -> FollowUpWorkbenchPage:
        """Query the authorized workbench once, with an exact filtered total.

        Date bounds are [start_date, end_date). The caller derives patient_ids
        from the authenticated actor; None is reserved for an authorized admin.
        Patient names are projected separately and never grant clinical access.
        """
        if skip < 0 or not 1 <= limit <= 100 or sort_order not in {"asc", "desc"}:
            raise ValueError("invalid workbench pagination")
        if patient_id and patient_ids is not None and patient_id not in patient_ids:
            raise AppBaseException("无权访问该患者的随访记录", status_code=403,
                                   error_code="PATIENT_NOT_ASSIGNED")
        scope = [patient_id] if patient_id else patient_ids
        query = {"deleted": {"$ne": True}}
        if scope is not None:
            query["patient_id"] = {"$in": scope}
        if status:
            query["status"] = {"$in": status}
        if follow_up_type:
            query["follow_up_type"] = follow_up_type
        dates = {}
        if start_date is not None:
            dates["$gte"] = start_date
        if end_date is not None:
            dates["$lt"] = end_date
        if dates:
            query["scheduled_date"] = dates

        if patient_name:
            # Escape input so names containing regex syntax remain literal.
            patient_query = {"role": "patient", "name": {
                "$regex": re.escape(patient_name), "$options": "i"}}
            if scope is not None:
                identifiers = [value for item in scope for value in
                               ([item, ObjectId(item)] if ObjectId.is_valid(item) else [item])]
                patient_query["_id"] = {"$in": identifiers}
            matches = await self.db.users.find(patient_query, {"_id": 1}).to_list(length=None)
            matched_ids = {str(row["_id"]) for row in matches}
            if scope is not None:
                matched_ids.intersection_update(scope)
            query["patient_id"] = {"$in": sorted(matched_ids)}

        direction = 1 if sort_order == "asc" else -1
        # Count and page consume the same filtered aggregation stream.
        result = await self.followup_records.aggregate([
            {"$match": query},
            {"$sort": {"scheduled_date": direction, "_id": direction}},
            {"$facet": {"items": [{"$skip": skip}, {"$limit": limit}],
                        "count": [{"$count": "total"}]}}
        ]).to_list(length=1)
        batch = result[0] if result else {"items": [], "count": []}
        documents = batch["items"]
        ids = {str(row["patient_id"]) for row in documents}
        identifiers = [value for item in ids for value in
                       ([item, ObjectId(item)] if ObjectId.is_valid(item) else [item])]
        names = {}
        if identifiers:
            patients = await self.db.users.find(
                {"role": "patient", "_id": {"$in": identifiers}}, {"name": 1}
            ).to_list(length=None)
            names = {str(row["_id"]): row.get("name") for row in patients}
        items = [FollowUpWorkbenchItem(
            **map_followup_record_to_response(followup_from_mongo(row)).model_dump(),
            patient_name=names.get(str(row["patient_id"]))) for row in documents]
        return FollowUpWorkbenchPage(items=items,
            total=batch["count"][0]["total"] if batch["count"] else 0,
            skip=skip, limit=limit)

    async def _list_records(
        self, query: Dict[str, Any], *, skip: int = 0, limit: int = 100,
        direction: int = 1,
    ) -> List[FollowUpRecordResponse]:
        """执行已构造并限定患者范围的查询，统一排序、分页及旧文档映射。"""
        cursor = self.followup_records.find(query).sort("scheduled_date", direction).skip(skip).limit(limit)
        documents = await cursor.to_list(length=limit)
        return [map_followup_record_to_response(followup_from_mongo(doc)) for doc in documents]


    async def create_followup_record(self, followup_data: FollowUpRecordCreate) -> FollowUpRecordResponse:
        """创建随访记录

        Args:
            followup_data: 随访记录创建请求数据

        Returns:
            FollowUpRecordResponse: 创建成功的随访记录响应
        """
        # 按生效 schema（schemas/followup.py FollowUpRecordCreate）约定：
        # description -> 存储字段 notes，related_records -> 存储字段 health_record_ids，
        # created_by 缺省时回退到必填的 provider_id（路由层缺省回退当前用户）。
        # S1 起扩展数据停止写 metadata.*：provider_id / template_id / reminder_before
        # 直接落顶层正式字段（FollowUpRecordDB 已声明，全部 Optional）。
        followup_metadata = dict(followup_data.metadata or {})

        # 创建随访记录对象
        followup_record = FollowUpRecord(
            patient_id=followup_data.patient_id,
            created_by=followup_data.created_by or followup_data.provider_id,
            follow_up_type=followup_data.follow_up_type,
            scheduled_date=followup_data.scheduled_date,
            notes=followup_data.description,
            # questions 为 pydantic 模型，须转 dict 才能落库
            questions=[q.model_dump() for q in followup_data.questions],
            health_record_ids=followup_data.related_records,
            metadata=followup_metadata
        )
        # 正式扩展字段落顶层（存储模型 __init__ 未声明，to_mongo 复制 __dict__ 带出）
        followup_record.provider_id = followup_data.provider_id
        if followup_data.template_id:
            followup_record.template_id = followup_data.template_id
        if followup_data.reminder_before is not None:
            followup_record.reminder_before = followup_data.reminder_before

        # 插入数据库
        result = await self.followup_records.insert_one(followup_record.to_mongo())

        # 更新ID
        followup_record._id = str(result.inserted_id)

        # 创建关联的时间线项目
        timeline_item = MedicalTimeline.from_follow_up(followup_record)
        await self.medical_timelines.insert_one(timeline_item.to_mongo())

        # 返回响应
        return map_followup_record_to_response(followup_record)

    async def get_followup_record(self, followup_id: str) -> Optional[FollowUpRecordResponse]:
        """获取随访记录

        Args:
            followup_id: 随访记录ID

        Returns:
            Optional[FollowUpRecordResponse]: 随访记录响应，不存在则返回None
        """
        if not ObjectId.is_valid(followup_id):
            return None
        # 查询数据库
        followup_doc = await self.followup_records.find_one({"_id": ObjectId(followup_id)})
        if not followup_doc:
            return None

        # 创建对象并返回响应
        followup_record = followup_from_mongo(followup_doc)
        return map_followup_record_to_response(followup_record)

    async def list_followup_records(
        self,
        patient_id: str,
        status: Optional[List[str]] = None,
        follow_up_type: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        skip: int = 0,
        limit: int = 100
    ) -> List[FollowUpRecordResponse]:
        """列出患者的随访记录

        Args:
            patient_id: 患者ID
            status: 状态列表过滤
            follow_up_type: 随访类型过滤
            start_date: 开始日期过滤
            end_date: 结束日期过滤
            skip: 分页偏移量
            limit: 每页数量

        Returns:
            List[FollowUpRecordResponse]: 随访记录响应列表
        """
        # 构建查询条件
        query = {"patient_id": patient_id, "deleted": {"$ne": True}}

        if status:
            query["status"] = {"$in": status}

        if follow_up_type:
            query["follow_up_type"] = follow_up_type

        date_query = {}
        if start_date:
            date_query["$gte"] = start_date
        if end_date:
            date_query["$lte"] = end_date

        if date_query:
            query["scheduled_date"] = date_query

        return await self._list_records(query, skip=skip, limit=limit)

    async def list_followups_for_provider(
        self,
        provider_id: str,
        status: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
        patient_ids: Optional[List[str]] = None,
    ) -> List[FollowUpRecordResponse]:
        """列出责任医护（创建人维度）的随访记录

        doctor_router GET /follow-ups 的转调入口：与 canonical 列表接口
        （list_followup_records）同源同形状，仅查询维度不同
        （服务层写入的创建人字段是 created_by）。

        Args:
            provider_id: 责任医护ID（按 created_by 匹配）
            status: 单状态过滤
            skip: 分页偏移量
            limit: 每页数量

        Returns:
            List[FollowUpRecordResponse]: 随访记录响应列表
        """
        query = {"created_by": provider_id, "deleted": {"$ne": True}}
        if patient_ids is not None:
            query["patient_id"] = {"$in": patient_ids}
        if status:
            query["status"] = status

        return await self._list_records(query, skip=skip, limit=limit)

    async def list_all_followups(
        self,
        patient_id: Optional[str] = None,
        status: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
        patient_ids: Optional[List[str]] = None,
    ) -> List[FollowUpRecordResponse]:
        """列出随访记录（健康管理师全量视图，可按患者/状态过滤）

        health_manager_router GET /follow-ups 的转调入口。

        Args:
            patient_id: 患者ID，不提供则返回全部患者的随访
            status: 单状态过滤
            skip: 分页偏移量
            limit: 每页数量

        Returns:
            List[FollowUpRecordResponse]: 随访记录响应列表
        """
        query = {"deleted": {"$ne": True}}
        if patient_ids is not None:
            query["patient_id"] = {"$in": patient_ids}
        if patient_id:
            if patient_ids is not None and patient_id not in patient_ids:
                return []
            query["patient_id"] = patient_id
        if status:
            query["status"] = status

        return await self._list_records(query, skip=skip, limit=limit)

    async def get_upcoming_followups(self, patient_id: Optional[str] = None, days: int = 7, patient_ids: Optional[List[str]] = None) -> List[FollowUpRecordResponse]:
        """获取即将到来的随访记录

        Args:
            patient_id: 患者ID，不提供则获取所有患者的即将到来的随访
            days: 未来几天内的随访

        Returns:
            List[FollowUpRecordResponse]: 随访记录响应列表
        """
        # 构建查询条件
        query = {
            "status": {"$in": ["scheduled", "rescheduled"]},
            "scheduled_date": {
                "$gte": datetime.utcnow(),
                "$lte": datetime.utcnow() + timedelta(days=days)
            },
            "deleted": {"$ne": True}
        }

        if patient_ids is not None:
            query["patient_id"] = {"$in": patient_ids}
        if patient_id:
            if patient_ids is not None and patient_id not in patient_ids:
                return []
            query["patient_id"] = patient_id

        return await self._list_records(query)

    async def count_upcoming(self, patient_id: str, since: Optional[datetime] = None) -> int:
        """统计患者即将到来的随访数量（健康档案统计域转调入口）

        Args:
            patient_id: 患者ID
            since: 起始时间，缺省为当前时刻

        Returns:
            int: 已排期且 scheduled_date 不早于 since 的随访数量
        """
        query = {
            "patient_id": patient_id,
            "status": "scheduled",
            "deleted": {"$ne": True},
        }
        if since is not None:
            query["scheduled_date"] = {"$gte": since}
        return await self.followup_records.count_documents(query)

    async def get_followups_by_health_record(self, record_id: str, patient_id: Optional[str] = None) -> List[FollowUpRecordResponse]:
        """获取与健康档案关联的随访记录

        Args:
            record_id: 健康档案ID

        Returns:
            List[FollowUpRecordResponse]: 随访记录响应列表
        """
        # 查询数据库
        query = {"health_record_ids": record_id, "deleted": {"$ne": True}}
        if patient_id is not None:
            query["patient_id"] = patient_id
        return await self._list_records(query, direction=-1)

    # -------- 事务化更新 / 状态流转 --------

    async def _mutate(self, followup_id, operation):
        if not ObjectId.is_valid(followup_id):
            return None

        async def transact(session):
            doc = await self.followup_records.find_one(
                {"_id": ObjectId(followup_id), "deleted": {"$ne": True}}, session=session)
            if doc is None:
                return None
            return await operation(doc, session)

        return await run_followup_transaction(self.db, transact)

    @staticmethod
    def _require_open(doc, *, allow_review=False):
        allowed = {"scheduled", "awaiting_fill", "rescheduled"}
        if allow_review:
            allowed.add("in_review")
        if doc["status"] not in allowed:
            raise followup_conflict("当前随访状态不允许此操作")

    async def _write_node(self, doc, values, session):
        result = await self.followup_records.update_one(
            followup_version_filter(doc), {"$set": values, "$inc": {"mutation_version": 1}},
            session=session)
        if result.matched_count != 1:
            raise followup_conflict()
        return {**doc, **values, "mutation_version": doc.get("mutation_version", 0) + 1}

    async def _write_timeline(self, doc, session):
        record = followup_from_mongo(doc)
        timeline = MedicalTimeline.from_follow_up(record)
        query = {"related_ids": str(doc["_id"]), "item_type": "follow_up"}
        if not await self.medical_timelines.find_one(query, session=session):
            await self.medical_timelines.insert_one(timeline.to_mongo(), session=session)
            return
        await self.medical_timelines.update_one(
            query,
            {"$set": {"description": timeline.description,
                      "occurred_at": timeline.occurred_at,
                      "metadata.status": doc["status"]}}, session=session)

    async def _write_audit(self, resource_id, user_id, action, details, session):
        """在同一事务内写审计日志（audit_logs 集合，落库形状与 AuditLogService 一致）。

        FU01 S5（D-2 默认决策）：手工录入与审阅动作必须记审计且与节点写入
        原子提交——审计不得先于业务写提交（失败残留），也不得落后（丢失）。
        集合惰性获取：HealthRecordService 组合本服务时传入的是无 audit_logs
        预置键的假库，只有审计路径需要该集合。
        """
        log_dict = AuditLogCreate(
            user_id=str(user_id) if user_id is not None else "unknown",
            action=action, resource_type="followup_record",
            resource_id=str(resource_id), status="success", details=details,
        ).model_dump()
        log_dict["created_at"] = datetime.now(timezone.utc)
        await self.db["audit_logs"].insert_one(log_dict, session=session)

    async def _create_successor(self, doc, date, notes, session, provider_id=None):
        """只继承新访视的处方配置；答案、结果、审阅和任务引用从空状态开始。

        visit_code 不继承：同一患者各节点 visit_code 唯一（设计稿 §4.4 验收口径），
        复评/改期新节点由 S4 填报联动按其自身 visit_code 关联。
        provider_id：缺省继承原节点责任医护，显式传入时覆盖（S6 复评可换人）。
        """
        source = followup_from_mongo(doc)
        record = FollowUpRecord(
            patient_id=source.patient_id, created_by=source.created_by,
            follow_up_type=source.follow_up_type, scheduled_date=date, notes=notes,
            questions=deepcopy(source.questions), health_record_ids=deepcopy(source.health_record_ids),
            reminder_settings=deepcopy(source.reminder_settings))
        legacy = source.metadata or {}
        for field in ("provider_id", "template_id", "reminder_before", "form_binding"):
            value = getattr(source, field, None)
            if value is None:
                value = legacy.get(field)
            if value is not None:
                setattr(record, field, deepcopy(value))
        if provider_id is not None:
            record.provider_id = provider_id
        record.previous_visit_id = str(doc["_id"])
        record.mutation_version = 0
        child = record.to_mongo()
        await self.followup_records.insert_one(child, session=session)
        timeline = MedicalTimeline.from_follow_up(record)
        await self.medical_timelines.insert_one(timeline.to_mongo(), session=session)
        return str(child["_id"])

    async def update_followup_record(self, followup_id, followup_data):
        async def operation(doc, session):
            self._require_open(doc, allow_review=True)
            if followup_data.status and followup_data.status.value != doc["status"]:
                raise followup_conflict("随访状态变更必须使用对应的领域操作接口")
            values = {"updated_at": datetime.utcnow()}
            mapping = {"description": "notes", "related_records": "health_record_ids"}
            for key, value in followup_data.model_dump(exclude_unset=True).items():
                if value is not None:
                    values[mapping.get(key, key)] = value.value if hasattr(value, "value") else value
            updated = await self._write_node(doc, values, session)
            if followup_data.status:
                await self._write_timeline(updated, session)
            return map_followup_record_to_response(followup_from_mongo(updated))
        return await self._mutate(followup_id, operation)

    async def complete_followup(self, followup_id, data, *, operator_id=None):
        """无表单随访的手工结果录入（FU01 S5，原 complete 端点降级语义）。

        D-2 默认决策（2026-11-09，见设计稿实施记录）：允许手工录入随访结果，
        但——
        - 节点只转 in_review（待医护审阅），completed 只能由 review 审阅通过
          置达（设计稿 §4.2「旧 complete 端点不得再直达 completed」）；
        - completion_data 带显式 source=manual_entry，区别于外部表单填报；
        - 清除旧 effective_response 当前引用并归档旧证据，保留 fill_task_ids；
          有效答卷只能来自任务 confirm 路径，手工录入不冒充表单答卷；
        - 同一事务写审计（action=followup_manual_entry）。
        - expected_version 绑定读取时的内容；同轮请求重试只返回直接产生的
          版本，退回后必须重新读取。相同内容的新轮录入使用新的版本号。
        """
        # 未显式提交的actual_date由服务端生成；不参与重试指纹。
        fingerprint = _request_fingerprint("complete", {
            "request": data.model_dump(exclude_unset=True), "operator_id": operator_id})
        async def operation(doc, session):
            version = doc.get("mutation_version", 0) or 0
            if (doc.get("completion_operation") == fingerprint
                    and version == data.expected_version + 1):
                return map_followup_record_to_response(followup_from_mongo(doc))
            if version != data.expected_version:
                raise followup_conflict("随访内容已更新，请重新读取后提交录入")
            self._require_open(doc, allow_review=True)
            now = datetime.utcnow()
            values = {
                "status": "in_review", "actual_date": data.actual_date,
                "answers": [a.model_dump() for a in data.answers],
                "notes": data.notes or doc.get("notes", ""), "updated_at": now,
                "completion_data": {"completed_at": now, "result": data.follow_up_result,
                                    "notes": data.notes, "source": "manual_entry"},
                "follow_up_result": data.follow_up_result, "completion_operation": fingerprint,
                "effective_response": None,
            }
            values.update(followup_submission_fields(doc, values, source="manual_entry",
                submitted_by=operator_id, submitted_at=now))
            # 更新父节点获得写冲突保护后，才建立后继及时间线；全部同一事务。
            updated = await self._write_node(doc, values, session)
            if data.next_follow_up_date:
                child_id = await self._create_successor(
                    doc, data.next_follow_up_date, f"基于上次随访({followup_id})创建的后续随访", session)
                await self.followup_records.update_one(
                    {"_id": doc["_id"]}, {"$set": {"next_follow_up_id": child_id, "next_visit_id": child_id}}, session=session)
                updated.update(next_follow_up_id=child_id, next_visit_id=child_id)
            await self._write_audit(
                followup_id,
                operator_id or doc.get("provider_id") or doc.get("created_by"),
                "followup_manual_entry",
                {"decision": "manual_entry", "source": "manual_entry",
                 "result": data.follow_up_result},
                session)
            await self._write_timeline(updated, session)
            return map_followup_record_to_response(followup_from_mongo(updated))
        return await self._mutate(followup_id, operation)

    async def _verified_external_review_evidence(self, doc, session):
        """Approval uses persisted confirmation bound to this patient/visit, never client evidence."""
        reference = _evidence_value(doc, "effective_response") or {}
        task_id = str(reference.get("task_id") or "")
        if not ObjectId.is_valid(task_id):
            raise followup_conflict("当前答卷缺少有效的本地确认任务，请退回重新提交")
        task = await self.db[_FILL_TASKS_COLLECTION].find_one(
            {"_id": ObjectId(task_id)}, session=session)
        confirmation = (task or {}).get("confirmation") or {}
        if (not task or task.get("status") != "confirmed"
                or str(task.get("patient_id")) != str(doc.get("patient_id"))
                or str(task.get("followup_visit_id")) != str(doc["_id"])
                or confirmation.get("response_id") != reference.get("response_id")
                or confirmation.get("remote_status") not in {"submitted", "restored"}):
            raise followup_conflict("当前答卷与本地确认证据不一致，请退回重新提交")
        visit_code = doc.get("visit_code")
        if visit_code and any(value != visit_code for value in (
                task.get("visit_code"), reference.get("visit_code"),
                confirmation.get("visit_code")) if value is not None):
            raise followup_conflict("当前答卷的访视引用不一致，请退回重新提交")
        return deepcopy(confirmation)

    async def review_followup(self, followup_id, data, *, reviewer_id, reviewer_role="doctor"):
        """医护审阅（FU01 S5，设计稿 §4.3）。

        - 仅 in_review 节点可审阅；completed 只能由 approved 决定置达；
        - 审阅人必须是责任医护（provider_id / created_by）本人或 admin，
          患者归属校验已在路由层执行；
        - 每次审阅追加 review.history[] 证据链（reviewer/decision/comment/evidence）；
        - returned：节点回 awaiting_fill，清除 effective_response（旧任务保持
          confirmed 终态，需新建填报任务重填，设计稿 §2.2 耦合规则）；
        - expected_version 绑定实际读到的内容，避免读取旧内容却批准新内容；
        - 幂等仅限直接结果版本；节点再变更后旧请求返回409，不能跨轮重放。
        """
        fingerprint = _request_fingerprint("review", {
            "expected_version": data.expected_version,
            "decision": data.decision.value, "comment": data.comment,
            "evidence": data.evidence, "reviewer_id": reviewer_id})
        async def operation(doc, session):
            version = doc.get("mutation_version", 0) or 0
            if (doc.get("review_operation") == fingerprint
                    and version == data.expected_version + 1):
                return map_followup_record_to_response(followup_from_mongo(doc))
            if version != data.expected_version:
                raise followup_conflict("随访内容已更新，请重新读取后审阅")
            if doc["status"] != "in_review":
                raise followup_conflict("只有待审阅(in_review)状态的随访可以审阅")
            if (reviewer_role != "admin"
                    and reviewer_id not in {doc.get("provider_id"), doc.get("created_by")}):
                raise AppBaseException("只有责任医护本人或管理员可以审阅该随访",
                                       status_code=403, error_code="FOLLOWUP_REVIEW_FORBIDDEN")
            evidence_state = current_followup_evidence(doc)
            if (data.decision is ReviewDecision.APPROVED
                    and evidence_state["source"] not in {"manual_entry", "external_form"}):
                raise followup_conflict("当前随访证据来源缺失或冲突，请退回并重新提交后审阅")
            verified_confirmation = None
            if (data.decision is ReviewDecision.APPROVED
                    and evidence_state["source"] == "external_form"):
                verified_confirmation = await self._verified_external_review_evidence(doc, session)
            now = datetime.utcnow()
            history = list((doc.get("review") or {}).get("history") or [])
            entry = {
                "review_id": str(ObjectId()), "reviewer_id": reviewer_id,
                "reviewer_role": reviewer_role, "reviewed_at": now,
                "reviewed_version": data.expected_version,
                "current_evidence": evidence_state,
                "decision": data.decision.value, "comment": data.comment,
                "evidence": data.evidence,
            }
            history.append(entry)
            if verified_confirmation is not None:
                entry["verified_confirmation"] = verified_confirmation
            review = {"history": history, "decision": data.decision.value,
                      "reviewed_at": now, "reviewer_id": reviewer_id}
            values = {"review": review, "review_operation": fingerprint, "updated_at": now,
                      "submission_history": submission_history_with_legacy(doc)}
            if data.decision is ReviewDecision.APPROVED:
                # 审阅通过：completed + actual_date=reviewed_at（设计稿 §4.3）
                values["status"] = "completed"
                values["actual_date"] = now
            else:
                # 审阅退回：待重新填报；有效答卷清空，历史保留在各任务确认证据中
                values["status"] = "awaiting_fill"
                values["effective_response"] = None
                values.update(current_evidence=None, completion_data=None, answers=[],
                              follow_up_result=None, actual_date=None)
            updated = await self._write_node(doc, values, session)
            await self._write_audit(
                followup_id, reviewer_id, "followup_review",
                {"decision": data.decision.value, "comment": data.comment,
                 "review_id": entry["review_id"],
                 "evidence": data.evidence}, session)
            await self._write_timeline(updated, session)
            return map_followup_record_to_response(followup_from_mongo(updated))
        return await self._mutate(followup_id, operation)

    async def cancel_followup(self, followup_id, data):
        fingerprint = _request_fingerprint("cancel", data.model_dump())
        async def operation(doc, session):
            if doc.get("cancellation_operation") == fingerprint:
                return map_followup_record_to_response(followup_from_mongo(doc))
            self._require_open(doc)
            if doc.get("next_visit_id") or doc.get("next_follow_up_id"):
                raise followup_conflict("该随访已有后继节点，不能重复创建")
            now = datetime.utcnow()
            values = {
                "status": "canceled", "notes": f"已取消: {data.cancel_reason}",
                "updated_at": now, "cancellation_operation": fingerprint,
                "cancellation_data": {"canceled_at": now, "canceled_by": data.canceled_by,
                                      "reason": data.cancel_reason, "reschedule_date": data.reschedule_date},
            }
            updated = await self._write_node(doc, values, session)
            if data.reschedule_date:
                child_id = await self._create_successor(
                    doc, data.reschedule_date,
                    f"由于取消原随访({followup_id})而重新安排的随访: {data.cancel_reason}", session)
                await self.followup_records.update_one(
                    {"_id": doc["_id"]}, {"$set": {"next_follow_up_id": child_id, "next_visit_id": child_id}}, session=session)
                updated.update(next_follow_up_id=child_id, next_visit_id=child_id)
            await self._write_timeline(updated, session)
            return map_followup_record_to_response(followup_from_mongo(updated))
        return await self._mutate(followup_id, operation)

    async def reschedule_followup(self, followup_id, data):
        fingerprint = _request_fingerprint("reschedule", data.model_dump())
        async def operation(doc, session):
            self._require_open(doc)
            same_date = _request_fingerprint("date", {"date": doc["scheduled_date"]}) == _request_fingerprint("date", {"date": data.new_date})
            if doc.get("reschedule_operation") == fingerprint and same_date:
                return map_followup_record_to_response(followup_from_mongo(doc))
            now = datetime.utcnow()
            metadata = deepcopy(doc.get("metadata") or {})
            metadata.update(reschedule_reason=data.reason, reschedule_time=now)
            values = {"status": "rescheduled", "scheduled_date": data.new_date,
                      "notes": f"{doc.get('notes', '')}\n重新安排原因: {data.reason}",
                      "updated_at": now, "metadata": metadata, "reschedule_operation": fingerprint}
            if data.provider_id is not None:
                values["provider_id"] = data.provider_id
            updated = await self._write_node(doc, values, session)
            await self._write_timeline(updated, session)
            return map_followup_record_to_response(followup_from_mongo(updated))
        return await self._mutate(followup_id, operation)

    # -------- FU01 S6：复评链（设计稿 §4.4）与 D-3 逾期/失访状态机（结构先行） --------

    # 复评允许的来源状态：已结束或可补救的节点；lost 是终态（设计稿 §2.2
    # 状态机无出边），不能从失访认定节点发起复评
    _REEVALUABLE_STATUSES = {"completed", "canceled", "missed", "overdue"}

    async def re_evaluate_followup(self, followup_id, data, *, operator_id=None):
        """复评 = 新建节点（FU01 S6，设计稿 §4.4）。

        - 复制 form_binding / questions / follow_up_type 与责任人、模板、
          提醒配置（_create_successor），写 previous_visit_id；原节点只回写
          next_visit_id / next_follow_up_id 链接字段，不覆盖不改写其余内容（A06）；
        - 原节点须处于可复评状态（completed/canceled/missed/overdue）；
          lost 无出边，不能发起复评；
          进行中的节点应走改期或取消流程；
        - 已有后继节点时拒绝重复创建（并发下由乐观版本保护串行化）；
        - 幂等：相同请求指纹重试返回同一后继节点，不产生分叉。
        """
        fingerprint = _request_fingerprint("re_evaluate", {
            "scheduled_date": data.scheduled_date, "reason": data.reason,
            "provider_id": data.provider_id, "operator_id": operator_id})
        notes = f"复评随访(基于原随访 {followup_id})" + (f": {data.reason}" if data.reason else "")
        async def operation(doc, session):
            if doc.get("re_evaluate_operation") == fingerprint:
                child = await self.followup_records.find_one(
                    {"previous_visit_id": str(doc["_id"])}, session=session)
                if child:
                    return map_followup_record_to_response(followup_from_mongo(child))
            if doc.get("next_visit_id") or doc.get("next_follow_up_id"):
                raise followup_conflict("该随访已有后继节点，不能重复创建")
            if doc["status"] not in self._REEVALUABLE_STATUSES:
                raise followup_conflict("只有已结束的随访节点可以发起复评")
            now = datetime.utcnow()
            # 版本预留写：并发冲突在原节点乐观写处暴露，失败事务连子节点一起回滚
            await self._write_node(doc, {"updated_at": now,
                                         "re_evaluate_operation": fingerprint}, session)
            child_id = await self._create_successor(
                doc, data.scheduled_date, notes, session, provider_id=data.provider_id)
            await self.followup_records.update_one(
                {"_id": doc["_id"]},
                {"$set": {"next_follow_up_id": child_id, "next_visit_id": child_id}}, session=session)
            await self._write_audit(
                followup_id, operator_id or doc.get("provider_id") or doc.get("created_by"),
                "followup_re_evaluate",
                {"child_visit_id": child_id, "reason": data.reason}, session)
            child = await self.followup_records.find_one(
                {"_id": ObjectId(child_id)}, session=session)
            return map_followup_record_to_response(followup_from_mongo(child))
        return await self._mutate(followup_id, operation)

    async def mark_overdue(self, followup_id, *, operator_id=None):
        """逾期状态转换（D-3 结构先行，阈值口径待 FU03）：open 状态 → overdue。

        overdue = 超窗口未填、可补救（可经补填/催办回到 awaiting_fill，
        失访认定走 mark_lost）。定时检查与提醒重试属 FU03，本方法只提供
        状态机转换与证据字段；幂等：已是 overdue 直接返回当前节点。
        """
        async def operation(doc, session):
            if doc["status"] == "overdue":
                return map_followup_record_to_response(followup_from_mongo(doc))
            self._require_open(doc)
            now = datetime.utcnow()
            metadata = deepcopy(doc.get("metadata") or {})
            metadata["overdue"] = {"marked_at": now, "operator_id": operator_id}
            updated = await self._write_node(
                doc, {"status": "overdue", "metadata": metadata, "updated_at": now}, session)
            await self._write_timeline(updated, session)
            return map_followup_record_to_response(followup_from_mongo(updated))
        return await self._mutate(followup_id, operation)

    async def mark_lost(self, followup_id, *, operator_id=None):
        """失访认定（D-3 结构先行，认定人口径待 FU03）：仅 overdue → lost（终态）。

        幂等：已是 lost 直接返回当前节点；非 overdue 节点拒绝认定。
        """
        async def operation(doc, session):
            if doc["status"] == "lost":
                return map_followup_record_to_response(followup_from_mongo(doc))
            if doc["status"] != "overdue":
                raise followup_conflict("只有逾期(overdue)节点可以认定失访(lost)")
            now = datetime.utcnow()
            metadata = deepcopy(doc.get("metadata") or {})
            metadata["lost"] = {"recognized_at": now, "recognized_by": operator_id}
            updated = await self._write_node(
                doc, {"status": "lost", "metadata": metadata, "updated_at": now}, session)
            await self._write_timeline(updated, session)
            return map_followup_record_to_response(followup_from_mongo(updated))
        return await self._mutate(followup_id, operation)

    async def resolve_effective_response(self, followup_id):
        """按有效答卷规则重算节点选定答卷（FU01 S6 验收：选取可解释）。

        只读核验入口：遍历节点 fill_task_ids 反向索引，跨访视任务（
        followup_visit_id 不属本节点）一律排除；选定结果不回写节点——
        effective_response 仍只能由任务 confirm 路径写入。无节点返回 None。
        """
        if not ObjectId.is_valid(followup_id):
            return None
        doc = await self.followup_records.find_one(
            {"_id": ObjectId(followup_id), "deleted": {"$ne": True}})
        if not doc:
            return None
        tasks = []
        for task_id in doc.get("fill_task_ids") or []:
            query_id = (ObjectId(str(task_id))
                        if ObjectId.is_valid(str(task_id)) else task_id)
            task = await self.db[_FILL_TASKS_COLLECTION].find_one({"_id": query_id})
            if task is None:
                continue
            if str(task.get("followup_visit_id") or "") != str(doc["_id"]):
                continue  # 跨访视答卷不可互相污染（设计稿 §4.4）
            tasks.append(task)
        return select_effective_response(tasks)

"""REH01 康复方案域结构收敛服务：方案版本、处方项（稳定 ID）与执行事件（幂等）。

范围限定为结构契约：
- 方案（rehab_plans）与方案版本（rehab_plan_versions）、处方项
  （rehab_prescription_items）、执行事件（rehab_execution_events）分离；
- 处方项拥有服务端分配的稳定 item_id，版本通过 item_ids 引用；
- 执行事件以客户端 event_id 为幂等键，重复提交返回既有事件、不重复计数；
- 对象级授权复用 patient_access 内核（ensure_patient_access）。

所有临床语义（四类干预规则值、阈值、禁忌内容、审核口径、完成率统计口径）
一律留空待定（D05/REH02/REH03 未决策），本服务不编造、不推断任何临床数据。
历史集合（rehab_plans / exercises / rehab_progress）不做迁移，新集合为增量。
"""
from copy import deepcopy
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from bson.objectid import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import DuplicateKeyError, PyMongoError

from app.core.exceptions import AppBaseException
from app.core.patient_access import ensure_patient_access
from app.schemas.rehab_plan_structure import (
    ExecutionEventCreate,
    PlanVersionCreate,
    PrescriptionItemCreate,
)

# 方案快照白名单：进入版本快照的内容字段（不含身份、审核证据与内嵌进度）
_PLAN_SNAPSHOT_FIELDS = (
    "name", "description", "goal", "condition", "frequency",
    "start_date", "end_date", "exercises", "notes",
)


class RehabPlanStructureService:
    """方案版本 / 处方项 / 执行事件的结构化服务（对象级授权内置于每个入口）。"""

    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.plans_collection = db.rehab_plans
        self.versions_collection = db.rehab_plan_versions
        self.items_collection = db.rehab_prescription_items
        self.events_collection = db.rehab_execution_events
        self._indexes_ready = False

    # ── 对象级授权 ────────────────────────────────────────────────────────

    async def _ensure_plan_access(
        self, plan_id: str, operator_id: str, operator_role: str
    ) -> Dict[str, Any]:
        """加载方案文档并校验操作者与方案所属患者的归属关系。

        文档不存在或缺失 patient_id → 404（不暴露存在性）；非归属医护 →
        403 PATIENT_NOT_ASSIGNED（复用 ensure_patient_access，admin 豁免）。
        中心/项目维度授权：方案文档保留 center_id/project_id 字段位（值待定
        D02），跨中心/项目访问规则确认前，对象级授权仅执行患者归属校验，
        不推断跨中心访问边界。
        """
        if not ObjectId.is_valid(plan_id):
            raise AppBaseException("康复计划不存在", status_code=404,
                                   error_code="REHAB_PLAN_NOT_FOUND")
        plan = await self.plans_collection.find_one({"_id": ObjectId(plan_id)})
        if not plan or not plan.get("patient_id"):
            raise AppBaseException("康复计划不存在", status_code=404,
                                   error_code="REHAB_PLAN_NOT_FOUND")
        await ensure_patient_access(self.db, str(plan["patient_id"]),
                                    operator_id, operator_role)
        return plan

    async def _get_version_checked(
        self, plan_id: str, version_id: str, operator_id: str, operator_role: str
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """校验版本归属方案后返回 (plan, version)；跨方案引用按 404 处置。"""
        plan = await self._ensure_plan_access(plan_id, operator_id, operator_role)
        if not ObjectId.is_valid(version_id):
            raise AppBaseException("方案版本不存在", status_code=404,
                                   error_code="REHAB_PLAN_VERSION_NOT_FOUND")
        version = await self.versions_collection.find_one(
            {"_id": ObjectId(version_id), "plan_id": plan_id})
        if not version:
            raise AppBaseException("方案版本不存在", status_code=404,
                                   error_code="REHAB_PLAN_VERSION_NOT_FOUND")
        return plan, version

    async def _get_item_checked(
        self, plan_id: str, item_id: str, operator_id: str, operator_role: str
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """校验处方项归属方案后返回 (plan, item)；跨方案引用按 404 处置。"""
        plan = await self._ensure_plan_access(plan_id, operator_id, operator_role)
        item = await self.items_collection.find_one(
            {"item_id": item_id, "plan_id": plan_id})
        if not item:
            raise AppBaseException("处方项不存在", status_code=404,
                                   error_code="REHAB_PRESCRIPTION_ITEM_NOT_FOUND")
        return plan, item

    # ── 方案版本 ──────────────────────────────────────────────────────────

    async def create_plan_version(
        self, plan_id: str, version_data: PlanVersionCreate, *,
        operator_id: str, operator_role: str,
    ) -> Dict[str, Any]:
        """为方案创建新版本：对当前内容按白名单做一次快照。

        版本号服务端递增；审核相关字段（reviewed_by/reviewed_at/review_note）
        仅保留字段位，审核状态机与签署口径由 REH02 承接，此处一律留空。
        """
        plan = await self._ensure_plan_access(plan_id, operator_id, operator_role)
        snapshot = {
            field: deepcopy(plan.get(field))
            for field in _PLAN_SNAPSHOT_FIELDS if field in plan
        }
        last = await self.versions_collection.find_one(
            {"plan_id": plan_id}, sort=[("version_no", -1)])
        version_no = (last.get("version_no", 0) + 1) if last else 1
        now = datetime.utcnow()
        doc = {
            "plan_id": plan_id,
            "version_no": version_no,
            "status": "draft",  # 版本状态机待定 REH02，仅记录创建来源状态
            "note": version_data.note if version_data else None,
            "snapshot": snapshot,
            "item_ids": [],
            # 中心/项目字段位：随方案文档透传（值待定 D02，本服务不推断）
            "center_id": plan.get("center_id"),
            "project_id": plan.get("project_id"),
            # 医护审核字段位：口径待定 REH02/D05，一律留空
            "reviewed_by": None,
            "reviewed_at": None,
            "review_note": None,
            "created_by": operator_id,
            "created_at": now,
            "updated_at": now,
        }
        try:
            result = await self.versions_collection.insert_one(doc)
        except PyMongoError as exc:
            raise AppBaseException("方案版本保存失败，请稍后重试", status_code=503,
                                   error_code="REHAB_PLAN_VERSION_SAVE_FAILED") from exc
        doc["_id"] = str(result.inserted_id)
        return doc

    async def list_plan_versions(
        self, plan_id: str, *, operator_id: str, operator_role: str,
        skip: int = 0, limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """列出方案的全部版本（版本号倒序）。"""
        await self._ensure_plan_access(plan_id, operator_id, operator_role)
        cursor = (self.versions_collection.find({"plan_id": plan_id})
                  .sort("version_no", -1).skip(skip).limit(limit))
        versions = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            versions.append(doc)
        return versions

    async def get_plan_version(
        self, plan_id: str, version_id: str, *,
        operator_id: str, operator_role: str,
    ) -> Dict[str, Any]:
        """读取单个方案版本。"""
        _, version = await self._get_version_checked(
            plan_id, version_id, operator_id, operator_role)
        version["_id"] = str(version["_id"])
        return version

    # ── 处方项（稳定 item_id）─────────────────────────────────────────────

    async def add_prescription_item(
        self, plan_id: str, version_id: str, item_data: PrescriptionItemCreate, *,
        operator_id: str, operator_role: str,
    ) -> Dict[str, Any]:
        """向方案版本添加处方项；item_id 服务端分配，创建后不变（稳定 ID）。

        适用条件 / 禁忌 / 来源 / 医护审核要求仅透传字段位，内容待定 D05，
        本方法不生成、不补全任何临床内容。
        """
        plan, version = await self._get_version_checked(
            plan_id, version_id, operator_id, operator_role)
        if version.get("workflow") == "patient_publication" or version.get("status") != "draft":
            raise AppBaseException("该版本不能通过旧处方接口修改，请使用康复草稿工作台", status_code=409,
                                   error_code="REHAB_VERSION_IMMUTABLE")
        now = datetime.utcnow()
        doc = item_data.model_dump(exclude_unset=True)
        doc.update({
            # 稳定处方项 ID：由服务端分配，跨版本修订保持不变
            "item_id": str(ObjectId()),
            "plan_id": plan_id,
            "version_id": version_id,
            "version_no": version.get("version_no"),
            "patient_id": str(plan["patient_id"]),
            # 中心/项目字段位（值待定 D02）
            "center_id": plan.get("center_id"),
            "project_id": plan.get("project_id"),
            "created_by": operator_id,
            "created_at": now,
            "updated_at": now,
            "content_revision": 0,
        })
        doc.pop("_id", None)
        try:
            result = await self.items_collection.insert_one(doc)
            await self.versions_collection.update_one(
                {"_id": ObjectId(version_id), "plan_id": plan_id},
                {"$push": {"item_ids": doc["item_id"]},
                 "$set": {"updated_at": now}})
        except PyMongoError as exc:
            raise AppBaseException("处方项保存失败，请稍后重试", status_code=503,
                                   error_code="REHAB_PRESCRIPTION_ITEM_SAVE_FAILED") from exc
        doc["_id"] = str(result.inserted_id)
        return doc

    async def list_prescription_items(
        self, plan_id: str, *, version_id: Optional[str] = None,
        operator_id: str = "", operator_role: str = "",
        skip: int = 0, limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """列出方案的处方项（可按版本过滤）。"""
        await self._ensure_plan_access(plan_id, operator_id, operator_role)
        query: Dict[str, Any] = {"plan_id": plan_id}
        if version_id:
            query["version_id"] = version_id
        cursor = (self.items_collection.find(query)
                  .sort("created_at", -1).skip(skip).limit(limit))
        items = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            items.append(doc)
        return items

    # ── 执行事件（幂等）───────────────────────────────────────────────────

    async def _ensure_event_indexes(self) -> None:
        """建立执行事件幂等唯一索引；失败必须拒绝写入。"""
        if self._indexes_ready:
            return
        try:
            await self.events_collection.create_index(
                [("plan_id", 1), ("event_id", 1)], unique=True,
                name="uniq_plan_event_id")
            self._indexes_ready = True
        except (PyMongoError, AttributeError) as exc:
            raise AppBaseException("执行记录唯一索引不可用，请核查后重试", status_code=503,
                                   error_code="REHAB_EXECUTION_INDEX_UNAVAILABLE") from exc

    async def record_execution_event(
        self, plan_id: str, item_id: str, event_data: ExecutionEventCreate, *,
        operator_id: str, operator_role: str,
    ) -> Dict[str, Any]:
        """记录一次训练执行事件；(plan_id, event_id) 幂等。

        重复提交返回既有事件（created=False），不产生第二条记录、不重复
        参与任何统计分母（统计口径本身待定 REH03）。事件绑定处方项及其
        所在版本；完成/撤回/补做的语义与并发更正历史待定 REH03，本方法
        只做幂等落库。
        """
        if event_data.event_id.startswith("patient-report:"):
            raise AppBaseException("该事件标识仅用于患者执行反馈", status_code=422,
                                   error_code="REHAB_RESERVED_EVENT_ID")
        plan, item = await self._get_item_checked(
            plan_id, item_id, operator_id, operator_role)
        item_version = await self.versions_collection.find_one(
            {"_id": ObjectId(item["version_id"]), "plan_id": plan_id}) if ObjectId.is_valid(str(item.get("version_id", ""))) else None
        if item_version and item_version.get("workflow") == "patient_publication":
            raise AppBaseException("已发布处方的患者执行反馈须使用专用入口", status_code=409,
                                   error_code="REHAB_PUBLICATION_EVENT_REQUIRED")
        await self._ensure_event_indexes()
        existing = await self.events_collection.find_one(
            {"plan_id": plan_id, "event_id": event_data.event_id})
        if existing:
            existing["_id"] = str(existing["_id"])
            return {"event": existing, "created": False}
        now = datetime.utcnow()
        doc = event_data.model_dump(exclude_unset=True)
        doc.update({
            "plan_id": plan_id,
            "prescription_item_id": item_id,
            "version_id": item.get("version_id"),
            "version_no": item.get("version_no"),
            "patient_id": str(plan["patient_id"]),
            # 计划训练实例字段位：实例划分口径待定 REH03，一律留空
            "training_instance": None,
            # 中心/项目字段位（值待定 D02）
            "center_id": plan.get("center_id"),
            "project_id": plan.get("project_id"),
            "recorded_by": operator_id,
            # 更正历史字段位：撤回/更正语义待定 REH03，先留空列表
            "correction_history": [],
            "created_at": now,
            "updated_at": now,
        })
        doc.pop("_id", None)
        try:
            result = await self.events_collection.insert_one(doc)
        except DuplicateKeyError:
            # 并发同 event_id：唯一索引兜底，返回先写入的事件
            existing = await self.events_collection.find_one(
                {"plan_id": plan_id, "event_id": event_data.event_id})
            if existing:
                existing["_id"] = str(existing["_id"])
                return {"event": existing, "created": False}
            raise AppBaseException("执行事件写入冲突，请重新读取", status_code=409,
                                   error_code="REHAB_EXECUTION_EVENT_CONFLICT")
        except PyMongoError as exc:
            raise AppBaseException("执行事件保存失败，请稍后重试", status_code=503,
                                   error_code="REHAB_EXECUTION_EVENT_SAVE_FAILED") from exc
        doc["_id"] = str(result.inserted_id)
        return {"event": doc, "created": True}

    async def list_execution_events(
        self, plan_id: str, *, item_id: Optional[str] = None,
        operator_id: str = "", operator_role: str = "",
        skip: int = 0, limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """列出方案的执行事件（可按处方项过滤，时间倒序）。"""
        await self._ensure_plan_access(plan_id, operator_id, operator_role)
        query: Dict[str, Any] = {"plan_id": plan_id}
        if item_id:
            query["prescription_item_id"] = item_id
        cursor = (self.events_collection.find(query)
                  .sort("created_at", -1).skip(skip).limit(limit))
        events = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            events.append(doc)
        return events

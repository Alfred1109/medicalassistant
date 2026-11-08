"""健康档案服务层契约测试（WP0 服务层两代字段修复，2026-11-07）。

针对 schemas/health_record.py 同名模型重复定义（后定义生效）导致的
服务层第一代/第二代字段混用断裂，按生效（第二代）schema 直测 HealthRecordService
（FU01 S2 起本文件仅覆盖健康档案/健康数据域，随访见 test_followup_service_contract.py）：

1. 创建健康档案：第二代字段齐全，不 AttributeError；落库文档字段与生效模型一致
   （organization_id / visibility 等第一代独有字段停止写入）；
2. 更新健康档案：content 为 str（生效模型），版本历史照常推进；
3. 创建健康数据：data_content 转换正确、pydantic 对象不直接进 $set、device_id 不再是布尔；
4. FU01 S2 说明：随访方法组已拆出至 FollowupService，随访契约见
   test_followup_service_contract.py（本文件仅保留健康档案/健康数据域）。

不连接真实数据库：集合用内存 FakeCollection 打桩，并用 bson.encode 验证落库文档
可被 BSON 序列化（pydantic 模型对象直接进库会抛 InvalidDocument，在此被断言拦截）。
"""

import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

from bson import ObjectId, encode

from app.models.health_record import HealthRecord
from app.schemas.health_record import (
    HealthDataCreate,
    HealthRecordAttachment,
    HealthRecordCreate,
    HealthRecordUpdate,
)
from app.services.health_record_service import HealthRecordService

PATIENT_ID = str(ObjectId())
DOCTOR_ID = str(ObjectId())


def _match(doc: Dict[str, Any], query: Dict[str, Any]) -> bool:
    """极简 Mongo 查询匹配：等值 / $ne / $in / $gte / $lte，列表字段包含匹配。"""
    for key, cond in query.items():
        actual = doc.get(key)
        if isinstance(cond, dict) and cond and all(k.startswith("$") for k in cond):
            for op, val in cond.items():
                if op == "$ne" and actual == val:
                    return False
                if op == "$in" and actual not in val:
                    return False
                if op == "$gte" and (actual is None or actual < val):
                    return False
                if op == "$lte" and (actual is None or actual > val):
                    return False
        elif isinstance(actual, list):
            if cond not in actual:
                return False
        elif actual != cond:
            return False
    return True


class FakeCursor:
    """模拟 motor 协程游标的链式排序/分页接口。"""

    def __init__(self, docs: List[Dict[str, Any]]):
        self._docs = list(docs)

    def sort(self, *args, **kwargs):
        return self

    def skip(self, n: int):
        self._docs = self._docs[n:]
        return self

    def limit(self, n: int):
        self._docs = self._docs[:n]
        return self

    async def to_list(self, length: Optional[int] = None):
        return list(self._docs[:length] if length is not None else self._docs)


class FakeCollection:
    """内存集合打桩：记录落库文档，供断言与 bson.encode 校验。"""

    def __init__(self):
        self.docs: Dict[Any, Dict[str, Any]] = {}

    async def insert_one(self, doc: Dict[str, Any]):
        doc = dict(doc)
        _id = doc.get("_id") or ObjectId()
        doc["_id"] = _id
        self.docs[_id] = doc
        return SimpleNamespace(inserted_id=_id)

    async def find_one(self, query: Dict[str, Any], *args, **kwargs):
        for doc in self.docs.values():
            if _match(doc, query):
                return dict(doc)
        return None

    async def update_one(self, query: Dict[str, Any], update: Dict[str, Any]):
        modified = 0
        for _id, doc in self.docs.items():
            if _match(doc, query):
                self._apply_set(doc, update.get("$set", {}))
                self.docs[_id] = doc
                modified += 1
        return SimpleNamespace(modified_count=modified)

    async def replace_one(self, query: Dict[str, Any], doc: Dict[str, Any]):
        for _id in list(self.docs):
            if _match(self.docs[_id], query):
                self.docs[_id] = dict(doc)
                return SimpleNamespace(modified_count=1)
        return SimpleNamespace(modified_count=0)

    async def count_documents(self, query: Dict[str, Any]):
        return sum(1 for doc in self.docs.values() if _match(doc, query))

    def find(self, query: Dict[str, Any]):
        return FakeCursor([dict(d) for d in self.docs.values() if _match(d, query)])

    def aggregate(self, pipeline: List[Dict[str, Any]]):
        return FakeCursor([])

    @staticmethod
    def _apply_set(doc: Dict[str, Any], set_data: Dict[str, Any]):
        for key, value in set_data.items():
            # 支持 "metadata.status" 等点号路径
            parts = key.split(".")
            target = doc
            for part in parts[:-1]:
                target = target.setdefault(part, {})
            target[parts[-1]] = value


def _make_service():
    # HealthRecordService（FU01 S2）内部组合 FollowupService(db)，
    # 需要预留 followup_records 集合（本文件不打桩其内容，仅占位）
    collections = {name: FakeCollection() for name in (
        HealthRecord.collection_name, "followup_records",
        "health_data", "medical_timelines",
    )}
    service = HealthRecordService(dict(collections))
    return service, collections


class HealthRecordServiceContractTests(unittest.IsolatedAsyncioTestCase):
    """按生效（第二代）schema 直测服务层创建/更新/健康数据契约。"""

    async def asyncSetUp(self):
        self.service, self.collections = _make_service()
        self.health_records = self.collections[HealthRecord.collection_name]
        self.health_data_col = self.collections["health_data"]
        self.timelines = self.collections["medical_timelines"]

    # -------- 创建健康档案 --------

    async def test_create_health_record_uses_effective_schema_fields(self):
        record_data = HealthRecordCreate(
            patient_id=PATIENT_ID,
            record_type="medical_record",
            title="门诊病历",
            content="主诉：右膝术后三周，屈曲受限。",
            created_by=DOCTOR_ID,
            tags=["复诊", "骨科"],
            metadata={"department": "骨科"},
            attachments=[HealthRecordAttachment(
                filename="report.pdf", file_type="application/pdf",
                file_size=1024, file_url="http://example.com/report.pdf",
                uploaded_by=DOCTOR_ID,
            )],
        )

        response = await self.service.create_health_record(record_data)

        self.assertEqual(response.patient_id, PATIENT_ID)
        self.assertEqual(response.title, "门诊病历")
        self.assertEqual(response.content, "主诉：右膝术后三周，屈曲受限。")
        self.assertEqual(response.current_version, 1)

        self.assertEqual(len(self.health_records.docs), 1)
        doc = next(iter(self.health_records.docs.values()))
        # 落库文档可被 BSON 序列化（pydantic 对象直接落库会抛 InvalidDocument）
        encode(doc)
        self.assertIsInstance(doc["content"], str)
        self.assertEqual(doc["tags"], ["复诊", "骨科"])
        self.assertEqual(doc["metadata"], {"department": "骨科"})
        self.assertIsInstance(doc["attachments"], list)
        self.assertIsInstance(doc["attachments"][0], dict)
        self.assertEqual(doc["attachments"][0]["filename"], "report.pdf")
        # 第一代独有字段 organization_id / visibility：不再按请求写入（模型默认值兜底）
        self.assertIsNone(doc.get("organization_id"))
        self.assertEqual(doc.get("visibility"), "all")
        # 时间线项目同步创建
        self.assertEqual(len(self.timelines.docs), 1)
        timeline_doc = next(iter(self.timelines.docs.values()))
        self.assertIn(str(doc["_id"]), timeline_doc["related_ids"])

    async def test_update_health_record_with_effective_schema_fields(self):
        seed = HealthRecord(
            patient_id=PATIENT_ID, record_type="medical_record",
            title="旧标题", content="旧内容", created_by=DOCTOR_ID)
        seed_doc = seed.to_mongo()
        record_id = str(seed_doc["_id"])
        self.health_records.docs[seed_doc["_id"]] = seed_doc

        record_data = HealthRecordUpdate(
            title="新标题",
            content="新内容：恢复良好。",
            tags=["复诊"],
            attachments=[HealthRecordAttachment(
                filename="new.pdf", file_type="application/pdf",
                file_size=2048, file_url="http://example.com/new.pdf",
                uploaded_by=DOCTOR_ID,
            )],
            metadata={"reviewer": DOCTOR_ID},
            change_description="复诊修订",
        )

        response = await self.service.update_health_record(record_id, record_data, updated_by=DOCTOR_ID)

        self.assertIsNotNone(response)
        self.assertEqual(response.title, "新标题")
        self.assertEqual(response.content, "新内容：恢复良好。")
        self.assertEqual(response.current_version, 2)

        doc = self.health_records.docs[ObjectId(record_id)]
        encode(doc)
        self.assertIsInstance(doc["content"], str)
        self.assertEqual(doc["current_version"], 2)
        # 旧内容按模型版本语义进入版本历史
        self.assertEqual(len(doc["versions"]), 1)
        self.assertEqual(doc["versions"][0]["version_number"], 1)
        self.assertEqual(doc["versions"][0]["content"], "旧内容")
        self.assertEqual(doc["title"], "新标题")
        self.assertEqual(doc["metadata"], {"reviewer": DOCTOR_ID})
        self.assertIsInstance(doc["attachments"][0], dict)
        self.assertEqual(doc["attachments"][0]["filename"], "new.pdf")

    # -------- 创建健康数据 --------

    async def test_create_health_data_converts_data_content_and_no_boolean_device_id(self):
        recorded_at = datetime.utcnow() - timedelta(minutes=5)
        data_content = {"type": "heart_rate", "value": 72, "unit": "bpm"}
        data = HealthDataCreate(
            patient_id=PATIENT_ID,
            data_type="vital_sign",
            data_content=data_content,
            source="device",
            recorded_by=DOCTOR_ID,
            recorded_at=recorded_at,
        )

        response = await self.service.create_health_data(data)

        self.assertEqual(response.patient_id, PATIENT_ID)
        self.assertEqual(response.data_content, data_content)
        self.assertEqual(response.source, "device")

        self.assertEqual(len(self.health_data_col.docs), 1)
        doc = next(iter(self.health_data_col.docs.values()))
        encode(doc)
        # data_content -> 存储字段 data
        self.assertEqual(doc["data"], data_content)
        self.assertEqual(doc["data_type"], "vital_sign")
        # device_id 不再是布尔（原 data.source == "device" 笔误已修复）
        self.assertIsNot(doc.get("device_id"), True)
        self.assertIsNot(doc.get("device_id"), False)
        # metadata 为第一代独有字段，停止写入（模型默认空 dict 兜底）
        self.assertEqual(doc.get("metadata"), {})
        # 时间线项目同步创建
        self.assertEqual(len(self.timelines.docs), 1)


if __name__ == "__main__":
    unittest.main()

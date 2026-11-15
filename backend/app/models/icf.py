"""ICF 评估域模型（T71）。

三个集合：
- icf_categories：ICF 类目字典（可配置集合，内置一组康复常用默认类目；
  字典口径待临床确认，可后台维护）。
- icf_assessments：ICF 结构化评估（患者、评估时间、各类目限定值 0-4 或定性、
  评估来源随访/方案/手工、评估人、复用 clinical_reports 的 review 状态语义）。
- icf_reports：面向医护/机构的正式 ICF 报告（结构化 payload + review 状态机，
  与 clinical_reports 的 pending/reviewed/rejected 语义一致）。
- icf_metric_configs：指标定义（改善幅度、达标率等，定义可配置；默认口径
  待临床确认）。

模型只承载文档形状与集合名；业务语义（授权、指标计算、预警触发）在
app.services.icf_service 中实现。
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from bson import ObjectId

# ICF 域分类：身体功能(body functions) / 活动(activity) / 参与(participation)
ICF_DOMAINS = ("body", "activity", "participation")

# 评估来源
ICF_ASSESSMENT_SOURCES = ("followup", "plan", "manual")

# review 状态机（与 clinical_reports 的 review_status 语义一致）
ICF_REVIEW_STATUSES = ("pending", "reviewed", "rejected")


class IcfCategory:
    """ICF 类目字典条目。字典口径待临床确认，可后台维护。"""
    collection_name = "icf_categories"

    def __init__(self, code: str, name: str, domain: str,
                 description: str = "", enabled: bool = True,
                 source: str = "custom", created_by: Optional[str] = None,
                 created_at: Optional[datetime] = None,
                 updated_at: Optional[datetime] = None,
                 metadata: Optional[Dict[str, Any]] = None,
                 _id: Optional[str] = None):
        self.code = code
        self.name = name
        self.domain = domain
        self.description = description
        self.enabled = enabled
        self.source = source  # builtin：内置默认字典；custom：后台维护录入
        self.created_by = created_by
        self.created_at = created_at or datetime.utcnow()
        self.updated_at = updated_at or datetime.utcnow()
        self.metadata = metadata or {}
        self._id = _id or str(ObjectId())

    @classmethod
    def from_mongo(cls, doc):
        if not doc:
            return None
        data = dict(doc)
        data["_id"] = str(data["_id"])
        return cls(**data)

    def to_mongo(self):
        doc = self.__dict__.copy()
        if isinstance(doc.get("_id"), str):
            doc["_id"] = ObjectId(doc["_id"])
        return doc


class IcfAssessment:
    """ICF 结构化评估文档。

    review 字段沿用 clinical_reports 的语义：pending/reviewed/rejected，
    修改内容后 review 重置为 pending（content_revision 递增），
    mutation_version 作为并发 CAS 版本。
    """
    collection_name = "icf_assessments"

    def __init__(self, patient_id: str, assessor_id: str,
                 items: Optional[List[Dict[str, Any]]] = None,
                 source: str = "manual", source_ref: str = "",
                 assessed_at: Optional[datetime] = None, note: str = "",
                 review_status: str = "pending", review_note: str = "",
                 reviewer_id: Optional[str] = None,
                 reviewed_at: Optional[datetime] = None,
                 mutation_version: int = 0, content_revision: int = 1,
                 created_at: Optional[datetime] = None,
                 updated_at: Optional[datetime] = None,
                 metadata: Optional[Dict[str, Any]] = None,
                 _id: Optional[str] = None):
        self.patient_id = patient_id
        self.assessor_id = assessor_id
        self.items = items or []
        self.source = source
        self.source_ref = source_ref
        self.assessed_at = assessed_at or datetime.utcnow()
        self.note = note
        self.review_status = review_status
        self.review_note = review_note
        self.reviewer_id = reviewer_id
        self.reviewed_at = reviewed_at
        self.mutation_version = mutation_version
        self.content_revision = content_revision
        self.created_at = created_at or datetime.utcnow()
        self.updated_at = updated_at or datetime.utcnow()
        self.metadata = metadata or {}
        self._id = _id or str(ObjectId())

    @classmethod
    def from_mongo(cls, doc):
        if not doc:
            return None
        data = dict(doc)
        data["_id"] = str(data["_id"])
        return cls(**data)

    def to_mongo(self):
        doc = self.__dict__.copy()
        if isinstance(doc.get("_id"), str):
            doc["_id"] = ObjectId(doc["_id"])
        return doc


class IcfMetricConfig:
    """指标定义（可配置）：metric_key 唯一，params 为阈值等参数。

    默认口径（见 icf_service.DEFAULT_METRIC_CONFIGS）待临床确认。
    """
    collection_name = "icf_metric_configs"

    def __init__(self, metric_key: str, name: str, description: str = "",
                 enabled: bool = True,
                 params: Optional[Dict[str, Any]] = None,
                 updated_by: Optional[str] = None,
                 updated_at: Optional[datetime] = None,
                 _id: Optional[str] = None):
        self.metric_key = metric_key
        self.name = name
        self.description = description
        self.enabled = enabled
        self.params = params or {}
        self.updated_by = updated_by
        self.updated_at = updated_at or datetime.utcnow()
        self._id = _id or str(ObjectId())

    @classmethod
    def from_mongo(cls, doc):
        if not doc:
            return None
        data = dict(doc)
        data["_id"] = str(data["_id"])
        return cls(**data)

    def to_mongo(self):
        doc = self.__dict__.copy()
        if isinstance(doc.get("_id"), str):
            doc["_id"] = ObjectId(doc["_id"])
        return doc


class IcfReport:
    """正式 ICF 报告文档：结构化 payload + 与 clinical_reports 一致的
    review 状态机（review_history、mutation_version CAS、reviewed_snapshot）。"""
    collection_name = "icf_reports"

    def __init__(self, patient_id: str, assessment_id: str, title: str,
                 generated_by: str, payload: Optional[Dict[str, Any]] = None,
                 review_status: str = "pending", review_note: str = "",
                 reviewer_id: Optional[str] = None,
                 reviewed_at: Optional[datetime] = None,
                 reviewed_snapshot: Optional[Dict[str, Any]] = None,
                 review_history: Optional[List[Dict[str, Any]]] = None,
                 mutation_version: int = 0, content_revision: int = 1,
                 created_at: Optional[datetime] = None,
                 updated_at: Optional[datetime] = None,
                 _id: Optional[str] = None):
        self.patient_id = patient_id
        self.assessment_id = assessment_id
        self.title = title
        self.generated_by = generated_by
        self.payload = payload or {}
        self.review_status = review_status
        self.review_note = review_note
        self.reviewer_id = reviewer_id
        self.reviewed_at = reviewed_at
        self.reviewed_snapshot = reviewed_snapshot
        self.review_history = review_history or []
        self.mutation_version = mutation_version
        self.content_revision = content_revision
        self.created_at = created_at or datetime.utcnow()
        self.updated_at = updated_at or datetime.utcnow()
        self._id = _id or str(ObjectId())

    @classmethod
    def from_mongo(cls, doc):
        if not doc:
            return None
        data = dict(doc)
        data["_id"] = str(data["_id"])
        return cls(**data)

    def to_mongo(self):
        doc = self.__dict__.copy()
        if isinstance(doc.get("_id"), str):
            doc["_id"] = ObjectId(doc["_id"])
        return doc

"""
模型CRUD服务
为各模型提供特定的CRUD操作
"""
from typing import List, Dict, Any, Optional, Type, TypeVar
from motor.motor_asyncio import AsyncIOMotorDatabase
from bson import ObjectId
from fastapi import status
from pymongo import ASCENDING
from pymongo.errors import PyMongoError

from app.db.crud import CRUDBase
from app.core.patient_access import (
    PatientAccessError, assigned_patient_query, patient_domain_mode)
from app.core.patient_identity import identity_candidates
from app.patients.legacy import LegacyPatientRepository
from app.patients.repository import ClinicalPatientRepository, PatientDomainError
from app.models.user import User, Doctor, Patient, HealthManager
from app.models.organization import Organization
from app.models.health_record import HealthRecord, FollowUpRecord
from app.models.rehabilitation import RehabilitationPlan, Exercise
from app.models.device import Device, DeviceData
from app.models.agent import Agent
# 注：原 Message/Conversation 模型类及其 CRUD（结构 A）已随 WS01 统一删除，
# 通信域唯一真实实现见 app/services/communication_service.py（结构 B）。


class CRUDServiceException(Exception):
    """CRUD服务异常基类"""
    pass


# 患者列表分页契约（T59 预适配）：canonical ClinicalPatientRepository.list_assigned
# 强制 1≤limit≤200（超限抛 INVALID_PATIENT_PAGINATION）。显式分页参数在两域执行
# 同一约束与同一错误码，使前端分页消费在域切换前后行为一致；缺省（不传参）
# 路径保持各自域的既有行为（legacy 全量不排序；canonical 为 list_assigned 的
# 仓库级缺省 limit=100、按 patient_id 排序）。
PATIENT_LIST_MAX_LIMIT = 200
PATIENT_LIST_DEFAULT_LIMIT = 100


def _patient_pagination_error(reason: str) -> PatientAccessError:
    """两域统一的分页参数非法错误：INVALID_PATIENT_PAGINATION/503。

    状态码沿用 canonical 仓库对分页越界的既有 503 语义（与患者域其他
    fail-closed 错误一致），错误码独立于 PATIENT_DOMAIN_STATE_UNAVAILABLE，
    前端可按「参数需调整」而非「域状态不可用」展示。
    """
    return PatientAccessError(
        "患者列表分页参数不合法：skip 不得小于 0，limit 取值范围为 1 到 200",
        error_code="INVALID_PATIENT_PAGINATION",
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        details={"reason": reason})


def _patient_domain_state_unavailable(reason: str) -> PatientAccessError:
    """canonical 分支二次状态读取/传输异常的统一包装（与
    patient_access._canonical_patient_read 同语义，避免裸逃逸成 500）。"""
    return PatientAccessError("患者域状态不可用，已拒绝访问",
                              error_code="PATIENT_DOMAIN_STATE_UNAVAILABLE",
                              status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                              details={"reason": reason})


class UserCRUD(CRUDBase[User]):
    """用户CRUD服务"""


class PractitionerCRUD(UserCRUD):
    """医疗从业者基类"""


class DoctorCRUD(PractitionerCRUD):
    """医生CRUD服务"""

    def __init__(self, db: AsyncIOMotorDatabase, model_class: Type[Doctor]):
        super().__init__(db, model_class)
        self.role = "doctor"


class PatientCRUD(CRUDBase[Patient]):
    """患者CRUD服务"""

    # 归属患者查询统一走 find_assigned_patients（与对象授权同源，
    # 经 LegacyPatientRepository 获得标识歧义防护）；早先绕过授权
    # 口径的 find_by_doctors/find_by_health_manager 已确认零调用方，
    # 随患者读取收敛一并删除（T18）。

    async def _get_patient_data(self, patient_doc: dict) -> dict:
        """从患者文档提取前端需要的数据"""
        if not patient_doc:
            return {}
            
        return {
            "id": str(patient_doc["_id"]),
            "name": patient_doc.get("name", "未知患者"),
            "age": patient_doc.get("age", 0),
            "gender": patient_doc.get("gender", "未知"),
            "diagnosis": patient_doc.get("diagnosis", None),
            "status": patient_doc.get("status", "未知")
        }
    
    async def find_by_doctor_id(self, doctor_id: str, *, skip: int = 0,
                                limit: Optional[int] = None) -> List[dict]:
        """根据医生ID查找其管理的所有患者

        数据库/查询异常如实上抛（由路由层转 500），不再吞掉后返回 []，
        避免"空列表"与"查询失败"混淆导致上层误判为空库。
        归属以患者 practitioners 为准，医生 patients 仅为历史兼容字段。
        分页参数语义见 find_assigned_patients（缺省不传=原全量行为）。
        """
        return await self.find_assigned_patients(doctor_id, "doctor",
                                                 skip=skip, limit=limit)

    async def find_assigned_patients(self, operator_id: str, operator_role: str, *,
                                     skip: int = 0,
                                     limit: Optional[int] = None) -> List[dict]:
        """与对象授权同源，返回医护当前管理的患者展示数据。

        T55 canonical 演练修复：按域分派。canonical 分支执行于
        clinical_patients（repo.list_assigned 内建 status=active 收窄与唯一
        主键防重），否则无账号患者（含导入产生的 canonical 临床患者）在
        医护患者列表恒不可见——列表仍把 users 当患者文档。legacy 分支保持
        原语义不变。
        患者读取收敛到 LegacyPatientRepository：先经 assigned_ids 复用授权查询
        并获得标识歧义防护（歧义时上抛 PATIENT_IDENTITY_AMBIGUOUS/503），
        再按适配器同源的双字面（string/ObjectId）标识取回完整文档。
        响应形状（_get_patient_data）与列表顺序（无排序的集合自然序）保持不变。

        T59 分页预适配（加法式，行为保持）：
        - 缺省（skip=0 且不传 limit）路径不变——legacy 全量、无排序、无 limit
          约束；canonical 为 list_assigned 的仓库级缺省语义（limit=100、按
          patient_id 排序）。
        - 显式分页（limit 传入或 skip>0）为可选新路径，两域同一约束：
          skip≥0、1≤limit≤200，违者 INVALID_PATIENT_PAGINATION/503。legacy
          分页按 _id 升序保证翻页稳定（缺省路径仍为集合自然序，不做排序）；
          canonical 按 patient_id 排序。canonical 分支的二次域状态读取与
          传输层异常统一转 503，绝不静默回退 legacy。
        """
        if skip < 0:
            raise _patient_pagination_error("NEGATIVE_SKIP")
        if limit is not None and not 1 <= limit <= PATIENT_LIST_MAX_LIMIT:
            raise _patient_pagination_error("LIMIT_OUT_OF_RANGE")
        paged = skip > 0 or limit is not None
        # domain-dispatch: 迁移完成后可删
        if await patient_domain_mode(self.db) == "canonical":
            repository = ClinicalPatientRepository(self.db)
            effective_limit = PATIENT_LIST_DEFAULT_LIMIT if limit is None else limit
            try:
                documents = await repository.list_assigned(
                    operator_id, operator_role, skip=skip, limit=effective_limit)
            except PatientDomainError as error:
                if error.code == "INVALID_PATIENT_PAGINATION":
                    raise _patient_pagination_error(error.code) from None
                raise _patient_domain_state_unavailable(error.code) from None
            except PyMongoError as error:
                raise _patient_domain_state_unavailable(
                    "PATIENT_DOMAIN_STATE_READ_FAILED") from error
            return [{
                "id": doc["patient_id"],
                "name": doc.get("name") or "未知患者",
                "age": (doc.get("demographic_info") or {}).get("age", 0),
                "gender": (doc.get("demographic_info") or {}).get("gender", "未知"),
                "diagnosis": (doc.get("medical_info") or {}).get("diagnosis", None),
                "status": doc.get("status", "未知"),
            } for doc in documents]
        repository = LegacyPatientRepository(self.db)
        identifiers = await repository.assigned_ids(
            assigned_patient_query(operator_id, operator_role))
        if not identifiers:
            return []
        cursor = self.collection.find({"role": "patient",
                                       "_id": {"$in": identity_candidates(identifiers)}})
        if paged:
            # 分页路径按 _id 升序保证 skip 翻页稳定；缺省路径保持集合自然序不变。
            cursor = cursor.sort("_id", ASCENDING).skip(skip)
            if limit is not None:
                cursor = cursor.limit(limit)
        return [await self._get_patient_data(doc) async for doc in cursor]


class HealthManagerCRUD(PractitionerCRUD):
    """健康管理师CRUD服务"""
    
    def __init__(self, db: AsyncIOMotorDatabase, model_class: Type[HealthManager]):
        super().__init__(db, model_class)
        self.role = "health_manager"


class OrganizationCRUD(CRUDBase[Organization]):
    """组织机构CRUD服务"""


class RecordBaseCRUD(CRUDBase[TypeVar('T')]):
    """记录CRUD服务基类"""


class HealthRecordCRUD(RecordBaseCRUD[HealthRecord]):
    """健康档案CRUD服务"""


class FollowUpRecordCRUD(RecordBaseCRUD[FollowUpRecord]):
    """随访记录CRUD服务"""


class RehabilitationPlanCRUD(RecordBaseCRUD[RehabilitationPlan]):
    """康复计划CRUD服务"""


class ExerciseCRUD(CRUDBase[Exercise]):
    """锻炼CRUD服务"""


class DeviceRelatedCRUD(CRUDBase[TypeVar('T')]):
    """设备相关CRUD服务基类"""


class DeviceCRUD(DeviceRelatedCRUD[Device]):
    """设备CRUD服务"""

    def __init__(self, db: AsyncIOMotorDatabase, model_class: Type[Device]):
        super().__init__(db, model_class)
        self.type_field_name = "device_type"


class DeviceDataCRUD(DeviceRelatedCRUD[DeviceData]):
    """设备数据CRUD服务"""

    def __init__(self, db: AsyncIOMotorDatabase, model_class: Type[DeviceData]):
        super().__init__(db, model_class)
        self.type_field_name = "data_type"


class AgentCRUD(CRUDBase[Agent]):
    """代理CRUD服务"""


# 创建CRUD服务工厂函数
def get_crud_services(db: AsyncIOMotorDatabase):
    """获取所有CRUD服务"""
    return {
        "user": UserCRUD(db, User),
        "doctor": DoctorCRUD(db, Doctor),
        "patient": PatientCRUD(db, Patient),
        "health_manager": HealthManagerCRUD(db, HealthManager),
        "organization": OrganizationCRUD(db, Organization),
        "health_record": HealthRecordCRUD(db, HealthRecord),
        "followup_record": FollowUpRecordCRUD(db, FollowUpRecord),
        "rehabilitation_plan": RehabilitationPlanCRUD(db, RehabilitationPlan),
        "exercise": ExerciseCRUD(db, Exercise),
        "device": DeviceCRUD(db, Device),
        "device_data": DeviceDataCRUD(db, DeviceData),
        "agent": AgentCRUD(db, Agent),
    }

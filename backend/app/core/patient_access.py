"""患者对象授权内核；不依赖认证组装或业务服务。

域模式分派：读取 patients/repository.py 的 patient_domain_state 单例
（clinical-patients-v1）。无状态文档时按现状默认走 legacy（users）路径；
canonical 模式走 ClinicalPatientRepository + patient_account_links。模式
读取失败或观察到未知状态一律 fail-closed（拒绝请求），绝不静默回退 legacy。
"""
from typing import Any, Dict, Optional

from bson import ObjectId
from fastapi import status
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import PyMongoError

from app.core.exceptions import AppBaseException
from app.patients.legacy import LegacyPatientRepository, self_patient_id
from app.patients.repository import (
    ClinicalPatientRepository, PatientDomainError,
    assigned_query as canonical_assigned_query, domain_mode as read_domain_mode)


class PatientAccessError(AppBaseException):
    """患者归属校验失败（对象级授权）。"""

    def __init__(self, message: str, error_code: str = "PATIENT_NOT_ASSIGNED",
                 status_code: int = status.HTTP_403_FORBIDDEN,
                 details: Optional[Dict[str, Any]] = None):
        super().__init__(message=message, status_code=status_code,
                         error_code=error_code, details=details)


def _domain_state_unavailable(reason: str) -> PatientAccessError:
    return PatientAccessError("患者域状态不可用，已拒绝访问",
                              error_code="PATIENT_DOMAIN_STATE_UNAVAILABLE",
                              status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                              details={"reason": reason})


async def patient_domain_mode(db, *, session=None) -> str:
    """读取域开关；仅 `legacy`（无状态文档）与 `canonical` 是合法观察结果。"""
    try:
        return await read_domain_mode(db, session=session)
    except PatientDomainError as error:
        raise _domain_state_unavailable(error.code) from None
    except PyMongoError as error:
        raise _domain_state_unavailable("PATIENT_DOMAIN_STATE_READ_FAILED") from error


def resolve_self_patient_id(actor, patient_id=None) -> str:
    """Resolve only the active legacy domain's explicit same-document identity.

    与域模式无关：任何模式下患者账号都只能显式请求本人 ID，医疗角色不得借
    该入口获得本人患者访问；canonical 的链接核验在其后的异步路径完成。
    """
    identifier = self_patient_id(getattr(actor, "id", None), getattr(actor, "role", None), patient_id)
    if identifier is None:
        raise PatientAccessError("无权访问该患者的数据")
    return identifier


async def ensure_self_patient_access(db, actor, patient_id=None, *, session=None) -> str:
    """Verify the explicit self request against the active domain.

    legacy：同一文档关系即患者实体（保持现状语义）。canonical：必须存在经
    迁移核验的 verified 账号链接（repo.resolve_self），账号 ID 不再被假定即
    患者 ID；链接缺失、停用或临床记录不可用一律拒绝。
    """
    identifier = resolve_self_patient_id(actor, patient_id)
    if await patient_domain_mode(db, session=session) == "canonical":
        patient = await ClinicalPatientRepository(db).resolve_self(identifier, session=session)
        if patient is None:
            raise PatientAccessError("无权访问该患者的数据")
        return str(patient["patient_id"])
    await load_patient_doc(db, identifier, session=session)
    return identifier


def patient_assignment_field(operator_role: str) -> str:
    """使用与患者关联写入路径一致的角色字段，禁止跨角色借用关系。"""
    fields = {"doctor": "practitioners", "health_manager": "health_managers"}
    if operator_role not in fields:
        raise PatientAccessError("当前角色不能通过医护归属访问患者")
    return fields[operator_role]


def assigned_patient_query(operator_id: str, operator_role: str = "doctor") -> Dict[str, Any]:
    """与对象校验同源的患者查询范围，兼容历史 ObjectId 关系值（legacy 域）。

    同步保留：既有业务消费方直接将该查询用于 users 集合，其接入域分派属于
    后续波段。canonical 范围请使用 assigned_scope_query。
    """
    identifiers = [str(operator_id)]
    if ObjectId.is_valid(str(operator_id)):
        identifiers.append(ObjectId(str(operator_id)))
    return {"role": "patient", patient_assignment_field(operator_role): {"$in": identifiers}}


async def assigned_scope_query(db, operator_id: str, operator_role: str = "doctor",
                               *, session=None) -> Dict[str, Any]:
    """按域模式返回患者归属查询范围；canonical 范围已含 status=active。

    角色校验与 legacy 同源（同一 PatientAccessError），避免两条路径的
    医护角色语义漂移。
    """
    patient_assignment_field(operator_role)
    if await patient_domain_mode(db, session=session) == "canonical":
        return canonical_assigned_query(operator_id, operator_role)
    return assigned_patient_query(operator_id, operator_role)


async def load_patient_doc(db: AsyncIOMotorDatabase, patient_id: str, *, session=None) -> Dict[str, Any]:
    """按 ID 加载当前域的患者文档（legacy: users；canonical: clinical_patients）。

    两种主键形态（ObjectId / 非 ObjectId 字符串）在各自域内保持兼容；
    canonical 分支不读 users。
    """
    if await patient_domain_mode(db, session=session) == "canonical":
        doc = await ClinicalPatientRepository(db).get(patient_id, session=session)
    else:
        doc = await LegacyPatientRepository(db).get(patient_id, session=session)
    if not doc:
        raise PatientAccessError("患者不存在", error_code="PATIENT_NOT_FOUND",
                                 status_code=status.HTTP_404_NOT_FOUND)
    return doc


async def ensure_patient_access(db: AsyncIOMotorDatabase, patient_id: str,
                                operator_id: str, operator_role: str, *, session=None) -> Dict[str, Any]:
    """按已认证角色校验患者侧关联；admin 沿用既有豁免。

    归属字段与比较逻辑两域同构（clinical_patients 迁移保留原归属列表与
    ID 字面量）；患者实体的可用状态由所在域文档承载（legacy: is_active，
    canonical: status），由各域消费方自行执行既有策略。
    """
    if operator_role == "admin":
        return {}
    field = patient_assignment_field(operator_role)
    patient = await load_patient_doc(db, patient_id, session=session)
    assignments = {str(item) for item in (patient.get(field) or [])}
    if str(operator_id) not in assignments:
        raise PatientAccessError(
            "当前用户未获分配管理该患者，无权访问该患者数据",
            error_code="PATIENT_NOT_ASSIGNED", status_code=status.HTTP_403_FORBIDDEN)
    return patient

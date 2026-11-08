"""患者对象授权内核；不依赖认证组装或业务服务。"""
from typing import Any, Dict, Optional

from bson import ObjectId
from fastapi import status
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.exceptions import AppBaseException


class PatientAccessError(AppBaseException):
    """患者归属校验失败（对象级授权）。"""

    def __init__(self, message: str, error_code: str = "PATIENT_NOT_ASSIGNED",
                 status_code: int = status.HTTP_403_FORBIDDEN,
                 details: Optional[Dict[str, Any]] = None):
        super().__init__(message=message, status_code=status_code,
                         error_code=error_code, details=details)


async def load_patient_doc(db: AsyncIOMotorDatabase, patient_id: str) -> Dict[str, Any]:
    """按 ID 加载患者 users 文档（兼容 ObjectId 与非 ObjectId 主键）。"""
    query: Dict[str, Any] = {}
    if ObjectId.is_valid(patient_id):
        query["_id"] = ObjectId(patient_id)
    else:
        query["_id"] = patient_id
    doc = await db.users.find_one({**query, "role": "patient"})
    if not doc:
        raise PatientAccessError("患者不存在", error_code="PATIENT_NOT_FOUND",
                                 status_code=status.HTTP_404_NOT_FOUND)
    return doc


async def ensure_patient_access(db: AsyncIOMotorDatabase, patient_id: str,
                                operator_id: str, operator_role: str) -> Dict[str, Any]:
    """操作者须在患者的 practitioners 中；admin 沿用既有豁免。"""
    if operator_role == "admin":
        return {}
    patient = await load_patient_doc(db, patient_id)
    practitioners = {str(item) for item in (patient.get("practitioners") or [])}
    if str(operator_id) not in practitioners:
        raise PatientAccessError(
            "当前用户不是该患者的主治医生，无权访问该患者的康复数据",
            error_code="PATIENT_NOT_ASSIGNED", status_code=status.HTTP_403_FORBIDDEN)
    return patient

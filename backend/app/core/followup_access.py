"""随访入口的患者范围授权；复用共享医患归属规则。"""
from bson import ObjectId
from fastapi import HTTPException

from app.core.patient_access import ensure_patient_access


async def ensure_followup_patient_access(db, patient_id, actor, *, write=False):
    if write and actor.role not in {"doctor", "health_manager"}:
        raise HTTPException(status_code=403, detail="需要医疗人员(医生或健康管理师)权限")
    if actor.role == "patient":
        if str(patient_id) != str(actor.id):
            raise HTTPException(status_code=403, detail="无权访问该患者的随访记录")
        return
    if actor.role not in {"doctor", "health_manager", "admin"}:
        raise HTTPException(status_code=403, detail="无权访问随访记录")
    await ensure_patient_access(db, patient_id, str(actor.id), actor.role)


async def followup_patient_scope(db, actor):
    """返回查询级授权范围；None 仅表示既有 admin 全域豁免。"""
    if actor.role == "admin":
        return None
    if actor.role == "patient":
        return [str(actor.id)]
    if actor.role not in {"doctor", "health_manager"}:
        raise HTTPException(status_code=403, detail="无权访问随访记录")
    identifiers = [str(actor.id)]
    if ObjectId.is_valid(str(actor.id)):
        identifiers.append(ObjectId(str(actor.id)))
    cursor = db.users.find({"role": "patient", "practitioners": {"$in": identifiers}}, {"_id": 1})
    return [str(doc["_id"]) async for doc in cursor]

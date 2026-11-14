"""Patient ownership and clinical management policy for device resources."""
from bson import ObjectId
from fastapi import HTTPException

from app.core.patient_access import (
    assigned_patient_query, ensure_patient_access, load_patient_doc, resolve_self_patient_id,
)
from app.patients.legacy import LegacyPatientRepository
from app.core.patient_identity import identity_key, load_identity_groups


async def resolve_device_patient(db, actor, patient_id=None, *, session=None, fence=False):
    """A patient selects self; medical staff must select an assigned patient."""
    if actor.role == "patient":
        target = resolve_self_patient_id(actor, patient_id)
        patient = await load_patient_doc(db, target, session=session)
    elif actor.role in {"doctor", "health_manager", "admin"}:
        if not isinstance(patient_id, (str, ObjectId)) or not str(patient_id):
            raise HTTPException(422, detail="请明确选择设备所属患者")
        target = str(patient_id)
        patient = (await load_patient_doc(db, target, session=session) if actor.role == "admin" else
                   await ensure_patient_access(db, target, str(actor.id), actor.role, session=session))
    else:
        raise HTTPException(403, detail="无权管理患者设备")
    if patient.get("is_active", True) is not True:
        raise HTTPException(404, detail="患者不存在或不可用")
    if fence:
        groups = await load_identity_groups(db, [actor.id], session=session)
        accounts = groups.get(identity_key(actor.id), [])
        account = accounts[0] if len(accounts) == 1 else None
        if (not account or account.get("role") != actor.role
                or account.get("is_active", True) is not True):
            raise HTTPException(403, detail="当前账号不可用")
        for document in {document["_id"]: document for document in (account, patient)}.values():
            value = document.get("_device_access_fence", 0)
            if type(value) is not int or value < 0:
                raise HTTPException(503, detail="设备授权并发状态无效")
            result = await db.users.update_one({"_id": document["_id"]},
                {"$inc": {"_device_access_fence": 1}}, session=session)
            if result.matched_count != 1:
                raise HTTPException(403, detail="设备授权已变化")
    return str(patient["_id"])


async def ensure_device_access(db, device, actor, roles, *, write=False, session=None, fence=False):
    """Historical non-patient bindings remain visible only to administrators."""
    if write and device.get("status") == "deleted":
        raise HTTPException(409, detail="设备已解绑，不能继续修改")
    if actor.role == "admin" and not write:
        return
    if actor.role != "patient" and actor.role not in roles:
        raise HTTPException(403, detail="无权访问此设备")
    patient_id = device.get("patient_id")
    if not isinstance(patient_id, (str, ObjectId)) or not str(patient_id):
        raise HTTPException(404, detail="设备所属患者不可用")
    await resolve_device_patient(db, actor, patient_id, session=session, fence=fence)


async def device_patient_scope(db, actor, patient_id=None):
    """Return patient IDs; None is the administrator's read-only inventory."""
    if patient_id is not None or actor.role == "patient":
        return [await resolve_device_patient(db, actor, patient_id)]
    if actor.role == "admin":
        return None
    if actor.role not in {"doctor", "health_manager"}:
        raise HTTPException(403, detail="无权查看患者设备")
    return await LegacyPatientRepository(db).assigned_ids(
        {**assigned_patient_query(str(actor.id), actor.role), "$or": [
            {"is_active": True}, {"is_active": {"$exists": False}}]})

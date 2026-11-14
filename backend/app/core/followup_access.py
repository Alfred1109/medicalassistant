"""随访入口的患者范围授权；复用共享医患归属规则。"""
from fastapi import HTTPException

from app.core.patient_access import (
    PatientAccessError, assigned_scope_ids, ensure_patient_access, ensure_self_patient_access,
)


async def ensure_followup_patient_access(db, patient_id, actor, *, write=False):
    if write and actor.role not in {"doctor", "health_manager"}:
        raise HTTPException(status_code=403, detail="需要医疗人员(医生或健康管理师)权限")
    if actor.role == "patient":
        try:
            await ensure_self_patient_access(db, actor, patient_id)
        except PatientAccessError:
            raise HTTPException(status_code=403, detail="无权访问该患者的随访记录") from None
        return
    if actor.role not in {"doctor", "health_manager", "admin"}:
        raise HTTPException(status_code=403, detail="无权访问随访记录")
    await ensure_patient_access(db, patient_id, str(actor.id), actor.role)


async def followup_patient_scope(db, actor):
    """返回查询级授权范围；None 仅表示既有 admin 全域豁免。

    范围解析走内核「构造+执行」一体的 assigned_scope_ids：legacy 执行于
    users（歧义防护不变），canonical 执行于 clinical_patients——不再把
    canonical 查询形状交给 users 集合执行（那会让医护范围静默为空）。
    """
    if actor.role == "admin":
        return None
    if actor.role == "patient":
        return [await ensure_self_patient_access(db, actor)]
    if actor.role not in {"doctor", "health_manager"}:
        raise HTTPException(status_code=403, detail="无权访问随访记录")
    return await assigned_scope_ids(db, str(actor.id), actor.role)

"""健康档案入口的患者范围授权。"""
from fastapi import HTTPException

from app.core.patient_access import ensure_patient_access


async def ensure_health_record_patient_access(db, patient_id, actor):
    """患者仅访问本人；医护采用共享归属规则；admin 保持既有豁免。"""
    if actor.role == "patient":
        if str(patient_id) != str(actor.id):
            raise HTTPException(status_code=403, detail="无权访问该患者的健康档案")
        return
    if actor.role not in {"doctor", "health_manager", "admin"}:
        raise HTTPException(status_code=403, detail="无权访问健康档案")
    await ensure_patient_access(db, patient_id, str(actor.id), actor.role)

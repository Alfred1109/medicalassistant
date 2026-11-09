"""Reminder runtime health and authorized delivery history; never a send API."""
from typing import Optional
from datetime import datetime, timezone
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, Response

from app.core.dependencies import get_current_user
from app.core.followup_access import followup_patient_scope, ensure_followup_patient_access
from app.db.mongodb import get_database
from app.services.followup_reminder_service import DELIVERIES, reminder_runtime
from app.services.followup_service import FollowupService

router = APIRouter(prefix="/health-records/followup-reminders", tags=["随访提醒"])


def utc_fields(row):
    return {key: value.replace(tzinfo=timezone.utc).isoformat() if isinstance(value, datetime)
            and value.tzinfo is None else value for key, value in row.items()}


def medical_actor(actor):
    if actor.role not in {"doctor", "health_manager", "admin"}:
        raise HTTPException(403, detail="需要医护或管理员权限")


@router.get("/status")
async def reminder_status(response: Response, actor=Depends(get_current_user)):
    medical_actor(actor)
    response.headers["Cache-Control"] = "no-store"
    return utc_fields(reminder_runtime.status)


@router.get("")
async def reminder_history(response: Response, followup_id: Optional[str] = Query(None),
                           skip: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100),
                           actor=Depends(get_current_user), db=Depends(get_database)):
    medical_actor(actor)
    response.headers["Cache-Control"] = "no-store"
    scope = await followup_patient_scope(db, actor)
    query = {} if scope is None else {"patient_id": {"$in": scope}}
    if followup_id:
        if not ObjectId.is_valid(followup_id):
            raise HTTPException(422, detail="随访ID无效")
        record = await FollowupService(db).get_reminder_source(followup_id)
        if not record or record.get("deleted"):
            raise HTTPException(404, detail="随访不存在")
        await ensure_followup_patient_access(db, str(record["patient_id"]), actor)
        query["followup_id"] = str(ObjectId(followup_id))
    rows = await db[DELIVERIES].find(query, {"_id": 0, "policy": 1, "followup_id": 1,
        "patient_id": 1, "slot": 1, "planned_at": 1, "checked_at": 1,
        "status": 1, "reason": 1, "notification_id": 1}).sort(
            [("checked_at", -1), ("followup_id", 1), ("slot", 1)]).skip(skip).limit(limit).to_list(length=limit)
    return {"items": [utc_fields(row) for row in rows], "total": await db[DELIVERIES].count_documents(query), "skip": skip, "limit": limit}

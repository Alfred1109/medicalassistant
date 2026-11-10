from fastapi import APIRouter, Body, Depends, HTTPException, status, Query
from typing import List, Optional
from bson import ObjectId
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient

from ...core.auth import get_current_user
from ...db.mongodb import get_database
from ...models.communication import Notification
from app.schemas.user import UserResponse
from ...services.notification_service import NotificationService

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("/settings")
async def notification_settings(db: AsyncIOMotorClient = Depends(get_database),
                                current_user: UserResponse = Depends(get_current_user)):
    from app.directory.records import read_preferences
    saved = await read_preferences(db, current_user.id)
    return saved["notifications"]


@router.put("/settings")
async def update_notification_settings(payload: dict = Body(...), db: AsyncIOMotorClient = Depends(get_database),
                                       current_user: UserResponse = Depends(get_current_user)):
    from app.directory.records import save_preferences
    if not isinstance(payload, dict) or any(not isinstance(value, bool) for value in payload.values()):
        raise HTTPException(status_code=422, detail={"code": "INVALID_NOTIFICATION_SETTINGS"})
    saved = await save_preferences(db, current_user.id, notifications=payload)
    return saved["notifications"]

@router.get("/", response_model=List[Notification])
async def get_notifications(
    limit: int = Query(20, ge=1, le=100),
    skip: int = Query(0, ge=0),
    type: Optional[str] = None,
    read: Optional[bool] = None,
    db: AsyncIOMotorClient = Depends(get_database),
    current_user: UserResponse = Depends(get_current_user)
):
    """获取当前用户的通知"""
    user_id = current_user.id
    return await NotificationService.get_notifications(db, user_id, limit, skip, type, read)

@router.get("/unread/count", response_model=int)
async def get_unread_count(
    db: AsyncIOMotorClient = Depends(get_database),
    current_user: UserResponse = Depends(get_current_user)
):
    """获取未读通知数量"""
    user_id = current_user.id
    return await NotificationService.get_unread_count(db, user_id)

@router.put("/{notification_id}/read")
async def mark_as_read(
    notification_id: str,
    db: AsyncIOMotorClient = Depends(get_database),
    current_user: UserResponse = Depends(get_current_user)
):
    """将特定通知标记为已读"""
    user_id = current_user.id
    success = await NotificationService.mark_as_read(db, notification_id, user_id)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="未找到通知或您无权访问此通知"
        )
    
    return {"message": "通知已标记为已读"}

@router.put("/read-all")
async def mark_all_as_read(
    db: AsyncIOMotorClient = Depends(get_database),
    current_user: UserResponse = Depends(get_current_user)
):
    """将所有通知标记为已读"""
    user_id = current_user.id
    modified_count = await NotificationService.mark_all_as_read(db, user_id)
    
    return {"message": f"共{modified_count}条通知已标记为已读"}

@router.delete("/clear-all")
async def clear_all_notifications(
    db: AsyncIOMotorClient = Depends(get_database),
    current_user: UserResponse = Depends(get_current_user)
):
    """清空当前用户的通知；固定路径必须先于单条通知的动态路径。"""
    deleted_count = await NotificationService.clear_all_notifications(db, current_user.id)
    return {"message": f"共{deleted_count}条通知已清空"}


@router.delete("/{notification_id}")
async def delete_notification(
    notification_id: str,
    db: AsyncIOMotorClient = Depends(get_database),
    current_user: UserResponse = Depends(get_current_user)
):
    """删除特定通知"""
    user_id = current_user.id
    success = await NotificationService.delete_notification(db, notification_id, user_id)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="未找到通知或您无权访问此通知"
        )
    
    return {"message": "通知已删除"}

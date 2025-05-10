from fastapi import APIRouter, Depends, HTTPException, Query, Path, Body, WebSocket, WebSocketDisconnect
from typing import List, Dict, Any, Optional
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime
from pydantic import BaseModel, Field

from app.db.mongodb import get_database
from app.core.auth import get_current_user, get_current_active_user
from app.models.user import User
from app.services.communication_service import CommunicationService

router = APIRouter(prefix="/communications", tags=["communications"])

# 请求和响应模型
class MessageCreate(BaseModel):
    content: str = Field(..., description="消息内容")
    type: str = Field("text", description="消息类型，默认为文本")
    attachments: Optional[List[Dict[str, Any]]] = Field(None, description="附件列表")
    metadata: Optional[Dict[str, Any]] = Field(None, description="元数据")

class ConversationCreate(BaseModel):
    participant_id: str = Field(..., description="对话参与者ID")
    type: str = Field("chat", description="对话类型")

class OfflineSync(BaseModel):
    last_sync_time: datetime = Field(..., description="上次同步时间")

# 获取当前用户的对话列表
@router.get("/conversations")
async def get_conversations(
    limit: int = Query(20, ge=1, le=100),
    skip: int = Query(0, ge=0),
    status: Optional[str] = Query(None, description="对话状态筛选"),
    db: AsyncIOMotorClient = Depends(get_database),
    current_user: User = Depends(get_current_active_user)
):
    """获取当前用户的对话列表"""
    user_id = str(current_user["_id"])
    
    conversations = await CommunicationService.get_conversations(
        db, user_id, limit, skip, status
    )
    
    return conversations

# 获取特定对话详情
@router.get("/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: str = Path(..., description="对话ID"),
    db: AsyncIOMotorClient = Depends(get_database),
    current_user: User = Depends(get_current_active_user)
):
    """获取特定对话详情"""
    user_id = str(current_user["_id"])
    
    conversation = await CommunicationService.get_conversation(
        db, conversation_id, user_id
    )
    
    if not conversation:
        raise HTTPException(status_code=404, detail="对话不存在或无权访问")
    
    return conversation

# 创建新对话
@router.post("/conversations", status_code=201)
async def create_conversation(
    conversation: ConversationCreate,
    db: AsyncIOMotorClient = Depends(get_database),
    current_user: User = Depends(get_current_active_user)
):
    """创建新对话"""
    user_id = str(current_user["_id"])
    
    # 检查参与者是否存在
    participant = await db.users.find_one({"_id": conversation.participant_id})
    if not participant:
        raise HTTPException(status_code=404, detail="指定的参与者不存在")
    
    conversation_id = await CommunicationService.create_conversation(
        db, user_id, conversation.participant_id, conversation.type
    )
    
    return {"id": conversation_id}

# 获取对话中的消息
@router.get("/conversations/{conversation_id}/messages")
async def get_messages(
    conversation_id: str = Path(..., description="对话ID"),
    limit: int = Query(50, ge=1, le=100),
    before_id: Optional[str] = Query(None, description="指定消息ID，获取此消息之前的消息"),
    db: AsyncIOMotorClient = Depends(get_database),
    current_user: User = Depends(get_current_active_user)
):
    """获取对话中的消息"""
    user_id = str(current_user["_id"])
    
    messages = await CommunicationService.get_messages(
        db, conversation_id, user_id, limit, before_id
    )
    
    return messages

# 发送新消息
@router.post("/conversations/{conversation_id}/messages", status_code=201)
async def send_message(
    conversation_id: str = Path(..., description="对话ID"),
    message: MessageCreate = Body(...),
    db: AsyncIOMotorClient = Depends(get_database),
    current_user: User = Depends(get_current_active_user)
):
    """发送新消息"""
    user_id = str(current_user["_id"])
    
    try:
        message_response = await CommunicationService.send_message(
            db, conversation_id, user_id, message.content, message.type,
            message.attachments, message.metadata
        )
        return message_response
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))

# 标记消息已读
@router.put("/messages/{message_id}/read")
async def mark_message_as_read(
    message_id: str = Path(..., description="消息ID"),
    db: AsyncIOMotorClient = Depends(get_database),
    current_user: User = Depends(get_current_active_user)
):
    """将特定消息标记为已读"""
    user_id = str(current_user["_id"])
    
    success = await CommunicationService.mark_message_as_read(
        db, message_id, user_id
    )
    
    if not success:
        raise HTTPException(status_code=404, detail="消息不存在或无权操作")
    
    return {"status": "success"}

# 标记对话所有消息已读
@router.put("/conversations/{conversation_id}/read")
async def mark_conversation_as_read(
    conversation_id: str = Path(..., description="对话ID"),
    db: AsyncIOMotorClient = Depends(get_database),
    current_user: User = Depends(get_current_active_user)
):
    """将对话中所有消息标记为已读"""
    user_id = str(current_user["_id"])
    
    marked_count = await CommunicationService.mark_conversation_as_read(
        db, conversation_id, user_id
    )
    
    return {"marked_count": marked_count}

# 删除消息
@router.delete("/messages/{message_id}")
async def delete_message(
    message_id: str = Path(..., description="消息ID"),
    db: AsyncIOMotorClient = Depends(get_database),
    current_user: User = Depends(get_current_active_user)
):
    """删除消息（软删除）"""
    user_id = str(current_user["_id"])
    
    success = await CommunicationService.delete_message(
        db, message_id, user_id
    )
    
    if not success:
        raise HTTPException(status_code=404, detail="消息不存在或无权删除")
    
    return {"status": "success"}

# 获取未读消息数量
@router.get("/unread-count")
async def get_unread_count(
    db: AsyncIOMotorClient = Depends(get_database),
    current_user: User = Depends(get_current_active_user)
):
    """获取用户所有对话的未读消息总数"""
    user_id = str(current_user["_id"])
    
    count = await CommunicationService.get_total_unread_messages_count(
        db, user_id
    )
    
    return {"count": count}

# 同步离线消息
@router.post("/sync")
async def sync_offline_messages(
    sync_data: OfflineSync,
    db: AsyncIOMotorClient = Depends(get_database),
    current_user: User = Depends(get_current_active_user)
):
    """同步用户离线期间的新消息"""
    user_id = str(current_user["_id"])
    
    messages = await CommunicationService.sync_offline_messages(
        db, user_id, sync_data.last_sync_time
    )
    
    return messages 
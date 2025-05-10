from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException
from typing import Dict, List, Any, Optional, Set
import json
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime
import logging

from app.core.auth import get_current_user_ws
from app.db.mongodb import get_database
from app.models.user import User
from app.services.notification_service import NotificationService

# 配置日志
logger = logging.getLogger(__name__)

# 维护活跃连接的管理器
class ConnectionManager:
    def __init__(self):
        # 所有活跃连接：user_id -> {connection_id -> websocket}
        self.active_connections: Dict[str, Dict[str, WebSocket]] = {}
        # 聊天室连接：conversation_id -> {user_id -> {connection_id -> websocket}}
        self.chat_rooms: Dict[str, Dict[str, Dict[str, WebSocket]]] = {}
        # 通知连接：user_id -> {connection_id -> websocket}
        self.notification_connections: Dict[str, Dict[str, WebSocket]] = {}
    
    async def connect(self, websocket: WebSocket, user_id: str, connection_id: str):
        """建立新的WebSocket连接"""
        await websocket.accept()
        
        if user_id not in self.active_connections:
            self.active_connections[user_id] = {}
        
        self.active_connections[user_id][connection_id] = websocket
        logger.info(f"User {user_id} connected with connection {connection_id}")
    
    async def connect_to_chat(self, websocket: WebSocket, user_id: str, conversation_id: str, connection_id: str):
        """将用户连接到特定聊天室"""
        await self.connect(websocket, user_id, connection_id)
        
        if conversation_id not in self.chat_rooms:
            self.chat_rooms[conversation_id] = {}
        
        if user_id not in self.chat_rooms[conversation_id]:
            self.chat_rooms[conversation_id][user_id] = {}
        
        self.chat_rooms[conversation_id][user_id][connection_id] = websocket
        logger.info(f"User {user_id} joined chat room {conversation_id}")
    
    async def connect_to_notifications(self, websocket: WebSocket, user_id: str, connection_id: str):
        """建立通知WebSocket连接"""
        await self.connect(websocket, user_id, connection_id)
        
        if user_id not in self.notification_connections:
            self.notification_connections[user_id] = {}
        
        self.notification_connections[user_id][connection_id] = websocket
        logger.info(f"User {user_id} connected to notifications with connection {connection_id}")
    
    def disconnect(self, user_id: str, connection_id: str):
        """断开WebSocket连接"""
        if user_id in self.active_connections and connection_id in self.active_connections[user_id]:
            del self.active_connections[user_id][connection_id]
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]
            logger.info(f"User {user_id} disconnected connection {connection_id}")
        
        # 同时从通知连接中移除
        if user_id in self.notification_connections and connection_id in self.notification_connections[user_id]:
            del self.notification_connections[user_id][connection_id]
            if not self.notification_connections[user_id]:
                del self.notification_connections[user_id]
        
        # 从所有聊天室中移除
        for conversation_id in list(self.chat_rooms.keys()):
            if user_id in self.chat_rooms[conversation_id] and connection_id in self.chat_rooms[conversation_id][user_id]:
                del self.chat_rooms[conversation_id][user_id][connection_id]
                if not self.chat_rooms[conversation_id][user_id]:
                    del self.chat_rooms[conversation_id][user_id]
                if not self.chat_rooms[conversation_id]:
                    del self.chat_rooms[conversation_id]
    
    async def send_personal_message(self, message: Dict[str, Any], user_id: str):
        """向特定用户发送消息"""
        if user_id in self.active_connections:
            for connection_id, websocket in self.active_connections[user_id].items():
                try:
                    await websocket.send_json(message)
                except Exception as e:
                    logger.error(f"Error sending message to user {user_id}: {str(e)}")
    
    async def send_chat_message(self, message: Dict[str, Any], conversation_id: str):
        """向聊天室中的所有用户发送消息"""
        if conversation_id in self.chat_rooms:
            for user_id, connections in self.chat_rooms[conversation_id].items():
                for connection_id, websocket in connections.items():
                    try:
                        await websocket.send_json(message)
                    except Exception as e:
                        logger.error(f"Error sending chat message to user {user_id} in conversation {conversation_id}: {str(e)}")
    
    async def send_notification(self, notification: Dict[str, Any], user_id: str):
        """向用户发送通知"""
        if user_id in self.notification_connections:
            for connection_id, websocket in self.notification_connections[user_id].items():
                try:
                    await websocket.send_json({
                        "type": "notification",
                        "data": notification
                    })
                except Exception as e:
                    logger.error(f"Error sending notification to user {user_id}: {str(e)}")
    
    async def broadcast(self, message: Dict[str, Any], exclude_user_id: Optional[str] = None):
        """向所有连接的用户广播消息，可选择排除特定用户"""
        for user_id, connections in self.active_connections.items():
            if user_id != exclude_user_id:
                for connection_id, websocket in connections.items():
                    try:
                        await websocket.send_json(message)
                    except Exception as e:
                        logger.error(f"Error broadcasting message to user {user_id}: {str(e)}")
    
    def get_active_users_in_chat(self, conversation_id: str) -> Set[str]:
        """获取聊天室中的活跃用户ID集合"""
        if conversation_id in self.chat_rooms:
            return set(self.chat_rooms[conversation_id].keys())
        return set()

# 创建连接管理器实例
manager = ConnectionManager()

# 在应用中注册WebSocket路由
def setup_websockets(app: FastAPI):
    @app.websocket("/ws/chat/{conversation_id}")
    async def websocket_chat_endpoint(
        websocket: WebSocket, 
        conversation_id: str,
        db: AsyncIOMotorClient = Depends(get_database)
    ):
        """聊天WebSocket端点"""
        user = None
        connection_id = f"conn_{datetime.now().timestamp()}"
        
        try:
            # 验证用户身份
            user = await get_current_user_ws(websocket, db)
            if not user:
                await websocket.close(code=1008)  # Policy violation
                return
            
            user_id = str(user["_id"])
            
            # 建立连接
            await manager.connect_to_chat(websocket, user_id, conversation_id, connection_id)
            
            # 通知聊天室中的其他用户有新用户加入
            active_users = manager.get_active_users_in_chat(conversation_id)
            await manager.send_chat_message(
                {
                    "type": "user_joined",
                    "user_id": user_id,
                    "user_name": user.get("name", "Unknown"),
                    "active_users": list(active_users),
                    "timestamp": datetime.now().isoformat()
                },
                conversation_id
            )
            
            # 处理消息
            try:
                while True:
                    # 接收消息
                    data = await websocket.receive_text()
                    message_data = json.loads(data)
                    
                    # 根据消息类型处理
                    if message_data.get("type") == "message":
                        # 保存消息到数据库
                        message_content = message_data.get("content", "")
                        
                        # 广播消息到聊天室
                        await manager.send_chat_message(
                            {
                                "type": "message",
                                "message": {
                                    "id": str(datetime.now().timestamp()),
                                    "sender_id": user_id,
                                    "sender_name": user.get("name", "Unknown"),
                                    "content": message_content,
                                    "timestamp": datetime.now().isoformat()
                                }
                            },
                            conversation_id
                        )
                    elif message_data.get("type") == "typing":
                        # 广播用户正在输入状态
                        await manager.send_chat_message(
                            {
                                "type": "typing",
                                "user_id": user_id,
                                "user_name": user.get("name", "Unknown"),
                                "is_typing": message_data.get("is_typing", False)
                            },
                            conversation_id
                        )
                    elif message_data.get("type") == "read_receipt":
                        # 处理消息已读回执
                        message_ids = message_data.get("message_ids", [])
                        if message_ids:
                            # 更新消息状态为已读
                            # 这里可以添加数据库更新代码
                            
                            # 广播消息已读状态
                            await manager.send_chat_message(
                                {
                                    "type": "read_receipt",
                                    "user_id": user_id,
                                    "message_ids": message_ids
                                },
                                conversation_id
                            )
            except WebSocketDisconnect:
                # 用户断开连接
                manager.disconnect(user_id, connection_id)
                # 通知其他用户
                active_users = manager.get_active_users_in_chat(conversation_id)
                await manager.send_chat_message(
                    {
                        "type": "user_left",
                        "user_id": user_id,
                        "user_name": user.get("name", "Unknown"),
                        "active_users": list(active_users),
                        "timestamp": datetime.now().isoformat()
                    },
                    conversation_id
                )
            except Exception as e:
                logger.error(f"Error in chat websocket: {str(e)}")
                manager.disconnect(user_id, connection_id)
        except Exception as e:
            logger.error(f"Error establishing chat websocket connection: {str(e)}")
            try:
                await websocket.close(code=1011)  # Internal error
            except:
                pass
    
    @app.websocket("/ws/notifications")
    async def websocket_notification_endpoint(
        websocket: WebSocket,
        db: AsyncIOMotorClient = Depends(get_database)
    ):
        """通知WebSocket端点"""
        user = None
        connection_id = f"notif_{datetime.now().timestamp()}"
        
        try:
            # 验证用户身份
            user = await get_current_user_ws(websocket, db)
            if not user:
                await websocket.close(code=1008)  # Policy violation
                return
            
            user_id = str(user["_id"])
            
            # 建立连接
            await manager.connect_to_notifications(websocket, user_id, connection_id)
            
            # 发送初始未读通知数量
            unread_count = await NotificationService.get_unread_count(db, user_id)
            await websocket.send_json({
                "type": "notification_count",
                "count": unread_count
            })
            
            # 处理消息
            try:
                while True:
                    # 保持连接活跃，接收可能的客户端消息
                    data = await websocket.receive_text()
                    # 这里可以处理客户端发送的配置消息，如通知设置等
            except WebSocketDisconnect:
                # 用户断开连接
                manager.disconnect(user_id, connection_id)
            except Exception as e:
                logger.error(f"Error in notification websocket: {str(e)}")
                manager.disconnect(user_id, connection_id)
        except Exception as e:
            logger.error(f"Error establishing notification websocket connection: {str(e)}")
            try:
                await websocket.close(code=1011)  # Internal error
            except:
                pass

    # 添加其他WebSocket端点...

# 暴露管理器实例，供其他模块使用
def get_connection_manager():
    return manager 
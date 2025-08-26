"""
通知服务
处理系统通知的创建、获取和管理
"""
from typing import Dict, List, Any, Optional
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
import asyncio
import logging

# 配置日志
logger = logging.getLogger(__name__)

class NotificationService:
    """通知服务类"""
    
    @staticmethod
    async def get_notifications(
        db: AsyncIOMotorClient, 
        user_id: str,
        limit: int = 20,
        skip: int = 0,
        notification_type: Optional[str] = None,
        read: Optional[bool] = None
    ) -> List[Dict[str, Any]]:
        """获取用户的通知列表"""
        query = {"recipient_id": user_id}
        
        # 添加可选筛选条件
        if notification_type:
            query["notification_type"] = notification_type
        if read is not None:
            query["read"] = read
        
        # 查询数据库
        cursor = db.notifications.find(query)
        
        # 排序和分页
        cursor = cursor.sort("time", -1).skip(skip).limit(limit)
        
        # 转换为列表
        notifications = await cursor.to_list(length=limit)
        for notification in notifications:
            notification["id"] = str(notification["_id"])
            del notification["_id"]
        
        return notifications
    
    @staticmethod
    async def get_unread_count(db: AsyncIOMotorClient, user_id: str) -> int:
        """获取用户未读通知数量"""
        count = await db.notifications.count_documents({
            "recipient_id": user_id,
            "read": False
        })
        return count
    
    @staticmethod
    async def mark_as_read(db: AsyncIOMotorClient, notification_id: str, user_id: str) -> bool:
        """将特定通知标记为已读"""
        # 确保通知存在且属于当前用户
        notification = await db.notifications.find_one({
            "_id": ObjectId(notification_id),
            "recipient_id": user_id
        })
        
        if not notification:
            return False
        
        # 更新为已读
        result = await db.notifications.update_one(
            {"_id": ObjectId(notification_id)},
            {"$set": {"read": True}}
        )
        
        return result.modified_count > 0
    
    @staticmethod
    async def mark_all_as_read(db: AsyncIOMotorClient, user_id: str) -> int:
        """将用户所有通知标记为已读"""
        result = await db.notifications.update_many(
            {"recipient_id": user_id, "read": False},
            {"$set": {"read": True}}
        )
        
        return result.modified_count
    
    @staticmethod
    async def delete_notification(db: AsyncIOMotorClient, notification_id: str, user_id: str) -> bool:
        """删除特定通知"""
        # 确保通知存在且属于当前用户
        notification = await db.notifications.find_one({
            "_id": ObjectId(notification_id),
            "recipient_id": user_id
        })
        
        if not notification:
            return False
        
        # 删除通知
        result = await db.notifications.delete_one({"_id": ObjectId(notification_id)})
        
        return result.deleted_count > 0
    
    @staticmethod
    async def clear_all_notifications(db: AsyncIOMotorClient, user_id: str) -> int:
        """清空用户所有通知"""
        result = await db.notifications.delete_many({"recipient_id": user_id})
        
        return result.deleted_count
    
    @staticmethod
    async def create_notification(
        db: AsyncIOMotorClient,
        title: str,
        content: str,
        sender_id: str,
        sender_name: str,
        sender_role: str,
        recipient_id: str,
        notification_type: str = "general",
        priority: str = "normal",
        related_entity_id: Optional[str] = None,
        related_entity_type: Optional[str] = None
    ) -> str:
        """创建新通知"""
        notification = {
            "_id": ObjectId(),
            "title": title,
            "content": content,
            "sender_id": sender_id,
            "sender_name": sender_name,
            "sender_role": sender_role,
            "recipient_id": recipient_id,
            "time": datetime.now(),
            "read": False,
            "notification_type": notification_type,
            "priority": priority,
            "related_entity_id": related_entity_id,
            "related_entity_type": related_entity_type
        }
        
        result = await db.notifications.insert_one(notification)
        
        # 异步推送通知（如果启用了WebSocket连接管理器）
        try:
            from app.api.websockets import get_connection_manager
            connection_manager = get_connection_manager()
            
            # 转换通知为可JSON序列化格式
            notification_json = {
                "id": str(notification["_id"]),
                "title": notification["title"],
                "content": notification["content"],
                "sender_id": notification["sender_id"],
                "sender_name": notification["sender_name"],
                "sender_role": notification["sender_role"],
                "time": notification["time"].isoformat(),
                "notification_type": notification["notification_type"],
                "priority": notification["priority"],
                "related_entity_id": notification["related_entity_id"],
                "related_entity_type": notification["related_entity_type"]
            }
            
            # 创建异步任务发送通知
            asyncio.create_task(connection_manager.send_notification(notification_json, recipient_id))
            
            # 更新未读通知计数
            unread_count = await NotificationService.get_unread_count(db, recipient_id)
            asyncio.create_task(connection_manager.send_personal_message(
                {
                    "type": "notification_count",
                    "count": unread_count
                },
                recipient_id
            ))
        except Exception as e:
            logger.warning(f"通知实时推送失败: {str(e)}")
        
        return str(result.inserted_id)
    
    @staticmethod
    async def create_batch_notifications(
        db: AsyncIOMotorClient,
        title: str,
        content: str,
        sender_id: str,
        sender_name: str,
        sender_role: str,
        recipient_ids: List[str],
        notification_type: str = "general",
        priority: str = "normal",
        related_entity_id: Optional[str] = None,
        related_entity_type: Optional[str] = None
    ) -> List[str]:
        """批量创建通知给多个用户"""
        if not recipient_ids:
            return []
        
        notifications = []
        notification_ids = []
        
        for recipient_id in recipient_ids:
            notification_id = ObjectId()
            notification = {
                "_id": notification_id,
                "title": title,
                "content": content,
                "sender_id": sender_id,
                "sender_name": sender_name,
                "sender_role": sender_role,
                "recipient_id": recipient_id,
                "time": datetime.now(),
                "read": False,
                "notification_type": notification_type,
                "priority": priority,
                "related_entity_id": related_entity_id,
                "related_entity_type": related_entity_type
            }
            notifications.append(notification)
            notification_ids.append(str(notification_id))
        
        if notifications:
            await db.notifications.insert_many(notifications)
            
            # 异步推送通知
            try:
                from app.api.websockets import get_connection_manager
                connection_manager = get_connection_manager()
                
                for notification in notifications:
                    recipient_id = notification["recipient_id"]
                    
                    # 转换通知为可JSON序列化格式
                    notification_json = {
                        "id": str(notification["_id"]),
                        "title": notification["title"],
                        "content": notification["content"],
                        "sender_id": notification["sender_id"],
                        "sender_name": notification["sender_name"],
                        "sender_role": notification["sender_role"],
                        "time": notification["time"].isoformat(),
                        "notification_type": notification["notification_type"],
                        "priority": notification["priority"],
                        "related_entity_id": notification["related_entity_id"],
                        "related_entity_type": notification["related_entity_type"]
                    }
                    
                    # 发送通知
                    asyncio.create_task(connection_manager.send_notification(notification_json, recipient_id))
                    
                    # 更新未读通知计数
                    unread_count = await NotificationService.get_unread_count(db, recipient_id)
                    asyncio.create_task(connection_manager.send_personal_message(
                        {
                            "type": "notification_count",
                            "count": unread_count
                        },
                        recipient_id
                    ))
            except Exception as e:
                logger.warning(f"批量通知实时推送失败: {str(e)}")
        
        return notification_ids 
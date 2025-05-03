import asyncio
import json
from datetime import datetime, timedelta
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient

from app.core.config import settings

async def init_notification_data():
    """初始化通知数据，用于测试"""
    print("开始初始化通知数据...")
    
    # 连接数据库
    client = AsyncIOMotorClient(settings.MONGODB_URL)
    db = client[settings.MONGODB_DB_NAME]
    
    # 获取用户列表
    users = await db.users.find().to_list(length=100)
    
    if not users:
        print("错误: 未找到任何用户，请先初始化用户数据")
        return
    
    # 找到医生和患者
    doctors = [user for user in users if user.get('role') == 'doctor']
    patients = [user for user in users if user.get('role') == 'patient']
    
    if not doctors:
        print("错误: 未找到任何医生用户")
        return
    
    if not patients:
        print("错误: 未找到任何患者用户")
        return
    
    print(f"找到 {len(doctors)} 名医生和 {len(patients)} 名患者")
    
    # 创建医生通知
    notifications = []
    now = datetime.now()
    
    for patient in patients:
        patient_id = str(patient["_id"])
        
        # 为每个患者从每个医生创建几条通知
        for i, doctor in enumerate(doctors[:2]):  # 限制为前两个医生
            doctor_id = str(doctor["_id"])
            doctor_name = doctor.get("name", f"医生{i+1}")
            
            notifications.extend([
                {
                    "_id": ObjectId(),
                    "title": "康复计划已更新",
                    "content": f"您的康复计划已由{doctor_name}更新，请查看最新内容。",
                    "sender_id": doctor_id,
                    "sender_name": doctor_name,
                    "sender_role": "doctor",
                    "recipient_id": patient_id,
                    "time": now - timedelta(hours=i, days=1),
                    "read": False,
                    "notification_type": "medical",
                    "priority": "high",
                    "related_entity_id": str(ObjectId()),
                    "related_entity_type": "rehabilitation_plan"
                },
                {
                    "_id": ObjectId(),
                    "title": "下周随访预约提醒",
                    "content": f"{doctor_name}已为您安排下周随访，请准时参加。",
                    "sender_id": doctor_id,
                    "sender_name": doctor_name,
                    "sender_role": "doctor",
                    "recipient_id": patient_id,
                    "time": now - timedelta(days=2, hours=i*2),
                    "read": i == 0,  # 第一个医生的通知已读
                    "notification_type": "appointment",
                    "priority": "normal",
                    "related_entity_id": str(ObjectId()),
                    "related_entity_type": "appointment"
                },
                {
                    "_id": ObjectId(),
                    "title": "新的健康建议",
                    "content": f"{doctor_name}为您提供了新的健康建议，请查看。",
                    "sender_id": doctor_id,
                    "sender_name": doctor_name,
                    "sender_role": "doctor",
                    "recipient_id": patient_id,
                    "time": now - timedelta(days=4, hours=i),
                    "read": True,
                    "notification_type": "general",
                    "priority": "low",
                    "related_entity_id": None,
                    "related_entity_type": None
                }
            ])
    
    # 清空现有通知集合
    await db.notifications.delete_many({})
    
    # 插入新通知
    if notifications:
        result = await db.notifications.insert_many(notifications)
        print(f"成功插入 {len(result.inserted_ids)} 条通知数据")
    else:
        print("没有通知数据被插入")
    
    client.close()
    print("通知数据初始化完成")

if __name__ == "__main__":
    asyncio.run(init_notification_data()) 
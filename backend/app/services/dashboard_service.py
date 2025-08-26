"""
仪表盘数据服务
处理患者仪表盘相关的数据获取与处理逻辑
"""
from typing import Dict, List, Any, Optional
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId

class DashboardService:
    """仪表盘数据服务类"""
    
    @staticmethod
    async def get_all_dashboard_data(db: AsyncIOMotorClient, user_id: str) -> Dict[str, Any]:
        """获取用户的所有仪表盘数据"""
        result = {}
        
        # 获取健康指标数据
        health_metrics = await DashboardService.get_health_metrics(db, user_id)
        result["health_metrics"] = health_metrics

        # 获取待办事项
        todo_items = await DashboardService.get_todo_items(db, user_id)
        result["todo_items"] = todo_items
        
        # 获取康复进度
        rehab_progress = await DashboardService.get_rehab_progress(db, user_id)
        result["rehab_progress"] = rehab_progress
        
        return result
    
    @staticmethod
    async def get_health_metrics(db: AsyncIOMotorClient, user_id: str) -> List[Dict[str, Any]]:
        """获取用户的健康指标数据"""
        health_metrics_cursor = db.health_metrics.find({"user_id": user_id})
        health_metrics = await health_metrics_cursor.to_list(length=10)
        
        # 转换ObjectId为字符串
        for metric in health_metrics:
            metric["id"] = str(metric["_id"])
            del metric["_id"]
            
        return health_metrics
    
    @staticmethod
    async def get_todo_items(db: AsyncIOMotorClient, user_id: str) -> List[Dict[str, Any]]:
        """获取用户的待办事项"""
        todo_items_cursor = db.todo_items.find({"user_id": user_id})
        todo_items = await todo_items_cursor.to_list(length=10)
        
        # 转换ObjectId为字符串
        for item in todo_items:
            item["id"] = str(item["_id"])
            del item["_id"]
            
        return todo_items
    
    @staticmethod
    async def get_rehab_progress(db: AsyncIOMotorClient, user_id: str) -> Optional[Dict[str, Any]]:
        """获取用户的康复进度"""
        rehab_progress = await db.rehab_progress.find_one({"user_id": user_id})
        
        if not rehab_progress:
            return None
        
        # 转换ObjectId为字符串
        rehab_progress["id"] = str(rehab_progress["_id"])
        del rehab_progress["_id"]
        
        return rehab_progress 
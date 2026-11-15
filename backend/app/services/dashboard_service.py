"""
仪表盘数据服务
处理患者仪表盘相关的数据获取与处理逻辑
"""
import json
from typing import Dict, List, Any
from motor.motor_asyncio import AsyncIOMotorClient
from types import SimpleNamespace

from app.core.patient_access import resolve_self_patient_entity
from app.services.rehab_publication_service import RehabPublicationService

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
        
        # 患者康复内容只来自当前本人可见的已发布版本；历史 raw progress 不参与首页。
        result["published_rehab_plans"] = await RehabPublicationService(db).patient_list(
            SimpleNamespace(id=user_id, role="patient"), skip=0, limit=5)
        
        return result
    
    @staticmethod
    async def get_health_metrics(db: AsyncIOMotorClient, user_id: str) -> List[Dict[str, Any]]:
        """Project the patient's recorded vital signs without inventing a status or trend."""
        patient_id = await resolve_self_patient_entity(
            db, SimpleNamespace(id=user_id, role="patient"))
        cursor = db.health_data.find({"patient_id": patient_id, "data_type": "vital_sign", "deleted": {"$ne": True}})
        rows = await cursor.sort("recorded_at", -1).limit(10).to_list(length=10)
        result = []
        for row in rows:
            data = row.get("data") or {}
            value = data.get("value")
            flags = (row.get("metadata") or {}).get("quality_flags") or []
            if not isinstance(flags, list) or not all(isinstance(flag, str) for flag in flags):
                flags = ["invalid_quality_flags"]
            if isinstance(value, dict):
                # Preserve compound values without attempting clinical interpretation.
                value = json.dumps(value, ensure_ascii=False)
            result.append({"id": str(row["_id"]), "type": data.get("type"),
                           "name": data.get("type"), "value": value,
                           "unit": data.get("unit"), "timestamp": row.get("recorded_at"),
                           "quality_flags": flags})
        return result
    
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

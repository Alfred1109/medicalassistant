"""
仪表盘数据服务
处理患者仪表盘相关的数据获取与处理逻辑
"""
import json
from datetime import datetime, timezone
from typing import Dict, List, Any
from motor.motor_asyncio import AsyncIOMotorClient
from types import SimpleNamespace

from app.core.patient_access import resolve_self_patient_entity
from app.services.rehab_publication_service import RehabPublicationService
from app.integrations.forms import patient_self
from app.directory.records import list_pending_consent_summaries

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
        result["todo_items"] = await DashboardService.get_todo_items(db, user_id)
        
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
        """Read the stored items used by existing dashboard clients."""
        rows = await db.todo_items.find({"user_id": user_id}).to_list(length=10)
        for row in rows:
            row["id"] = str(row.pop("_id"))
        return rows

    @staticmethod
    async def get_todo_center(db: AsyncIOMotorClient, actor, *, include_questionnaires: bool = True) -> Dict[str, Any]:
        """Aggregate stored patient actions without creating local TODO copies.

        Each source is isolated so a failed integration does not hide other
        actionable items. Submitted/closed questionnaire tasks are deliberately
        excluded; only assigned or active patient tasks can be acted on.
        """
        items: List[Dict[str, Any]] = []
        source_errors: List[str] = []

        try:
            skip = 0
            while include_questionnaires:
                page = await patient_self.list_tasks(db, actor, skip=skip, limit=100, actionable_only=True)
                rows = page.get("items", [])
                for task in rows:
                    if task.get("status") not in {"assigned", "active"}:
                        continue
                    task_id = task.get("id")
                    if not task_id:
                        continue
                    items.append({
                        "id": f"questionnaire:{task_id}",
                        "type": "questionnaire",
                        "title": task.get("questionnaireTitle") or task.get("visitName") or "患者问卷",
                        "description": "请完成待填写的患者问卷。",
                        "status": "pending",
                        "created_at": task.get("createdAt"),
                        "href": f"/app/patient/questionnaires/{task_id}",
                    })
                skip += len(rows)
                if skip >= page.get("total", 0) or not rows:
                    break
                if skip > 10000:
                    source_errors.append("questionnaires_incomplete")
                    break
        except Exception:
            source_errors.append("questionnaires_unavailable")

        try:
            documents = await list_pending_consent_summaries(db, actor)
            for document in documents:
                if not document.get("id"):
                    continue
                document_id = str(document["id"])
                created_at = document.get("created_at")
                if isinstance(created_at, datetime):
                    utc = created_at.replace(tzinfo=timezone.utc) if created_at.tzinfo is None else created_at.astimezone(timezone.utc)
                    created_at = utc.isoformat().replace("+00:00", "Z")
                items.append({
                    "id": f"consent:{document_id}",
                    "type": "consent",
                    "title": document.get("title") or "知情同意文档",
                    "description": "请查看并处理待签署的知情同意文档。",
                    "status": "pending",
                    "created_at": created_at,
                    "href": f"/app/patient/documents/{document_id}",
                })
        except Exception:
            source_errors.append("consents_unavailable")

        items.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
        return {"items": items, "source_errors": source_errors}

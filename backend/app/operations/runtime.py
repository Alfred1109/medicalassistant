"""Admin settings and a bounded export that retains patient information."""
import logging
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from fastapi.responses import Response
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError
from .data_export import EXPORT_COLLECTIONS as BACKUP_COLLECTIONS, data_export_bytes

LOG_LEVELS = {"debug": logging.DEBUG, "info": logging.INFO, "warning": logging.WARNING, "error": logging.ERROR}


def _now():
    return datetime.now(timezone.utc)


def public_settings(row):
    row = row or {}
    return {
        "allow_registration": row.get("allow_registration", True),
        "maintenance_mode": bool(row.get("maintenance_mode")),
        "session_timeout_minutes": int(row.get("session_timeout_minutes") or 480),
        "data_retention_days": int(row.get("data_retention_days") or 365),
        "backup_frequency": row.get("backup_frequency") or "daily",
        "log_level": row.get("log_level") or "info",
        "login_notifications": row.get("login_notifications", True),
        "last_backup_at": row.get("last_backup_at"),
        "last_data_export_at": row.get("last_data_export_at"),
        "last_scheduled_export_at": row.get("last_scheduled_export_at"),
    }


async def read_operations(db):
    return public_settings(await db.system_settings.find_one({"_id": "system"}))


async def save_operations(db, payload):
    if payload.log_level not in LOG_LEVELS or payload.backup_frequency not in {"hourly", "daily", "weekly", "monthly"}:
        raise HTTPException(422, detail={"code": "INVALID_OPERATIONS"})
    changes = payload.model_dump()
    changes["updated_at"] = _now()
    await db.system_settings.update_one({"_id": "system"}, {"$set": changes}, upsert=True)
    logging.getLogger().setLevel(LOG_LEVELS[payload.log_level])
    cutoff = _now() - timedelta(days=payload.data_retention_days)
    await db.audit_logs.delete_many({"created_at": {"$lt": cutoff}})
    await db.notifications.delete_many({"time": {"$lt": cutoff.replace(tzinfo=None)}})
    return await read_operations(db)


async def session_timeout_minutes(db, default: int) -> int:
    row = await db.system_settings.find_one({"_id": "system"})
    minutes = int((row or {}).get("session_timeout_minutes") or default)
    return min(max(minutes, 15), 480)


async def backup_bytes(db) -> bytes:
    """Compatibility name for the limited business export."""
    return await data_export_bytes(db)


async def build_backup(db):
    body = await backup_bytes(db)
    await db.system_settings.update_one(
        {"_id": "system"}, {"$set": {"last_data_export_at": _now()}}, upsert=True)
    return Response(content=body, media_type="application/json", headers={
        "Content-Disposition": "attachment; filename=rehab-backup.json",
        "Cache-Control": "no-store",
        "X-Artifact-Type": "limited-credentials-filtered-business-export",
        "X-Database-Restorable": "false",
    })


class BackupSchedule:
    def __init__(self):
        self._task = None

    async def start(self, db):
        import os
        if os.getenv("PYTEST_CURRENT_TEST"):
            return
        import asyncio
        self._task = asyncio.create_task(self._loop(db))

    async def stop(self):
        if self._task:
            self._task.cancel()
            self._task = None

    async def _loop(self, db):
        import asyncio
        while True:
            try:
                await self.run_if_due(db)
            except Exception:
                logging.warning("定时业务导出没有写成文件")
            await asyncio.sleep(3600)

    async def run_if_due(self, db):
        from pathlib import Path
        row = await db.system_settings.find_one({"_id": "system"}) or {}
        hours = {"hourly": 1, "daily": 24, "weekly": 24 * 7, "monthly": 24 * 30}.get(row.get("backup_frequency") or "daily", 24)
        last = row.get("last_scheduled_export_at", row.get("last_backup_at"))
        if isinstance(last, datetime) and last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        if isinstance(last, datetime) and _now() - last < timedelta(hours=hours):
            return
        # T37（D1 修复）：到点后不再 check-then-act（读时间戳→导出→无条件回写），
        # 而是用 find_one_and_update 原子领取：到点条件放进 filter，由 MongoDB
        # 单文档原子性判定，只有领取成功（返回文档）的进程才执行导出，其余进程
        # 直接跳过。多 worker 同时到点不再各自执行全量业务导出（含患者数据的
        # 敏感文件，文件名秒级时间戳，同秒互相覆盖、跨秒留两份）。
        # 崩溃窗口取舍：领取先于导出——进程在导出中崩溃只会留下已推进的领取
        # 时间戳，下一轮将跳过一次导出（宁可漏一次，也不能重复落敏感文件）；
        # 旧实现的崩溃窗口（导出已做、标记未写、下轮重复导出）随之消除。
        # 领取条件与上面的 Python 端到点判断保持同一语义：
        # - 主条件：调度时间戳已过窗口（$lte，类型限定下不匹配 null/缺失）；
        # - legacy 回退：无调度时间戳时按旧的 last_backup_at 判定（row.get 回退）；
        # - 两个时间戳都缺失（从未导出）或调度时间戳为 null：视为到点
        #   （与 row.get 命中 None 后跳过 isinstance 判断的行为一致）。
        cutoff = _now() - timedelta(hours=hours)
        due = {"$or": [
            {"last_scheduled_export_at": {"$lte": cutoff}},
            {"last_scheduled_export_at": None, "last_backup_at": {"$lte": cutoff}},
            {"last_scheduled_export_at": None, "last_backup_at": None},
            {"last_scheduled_export_at": {"$eq": None, "$exists": True}},
        ]}
        try:
            claimed = await db.system_settings.find_one_and_update(
                {"_id": "system", **due},
                {"$set": {"last_scheduled_export_at": _now()}},
                upsert=True, return_document=ReturnDocument.AFTER)
        except DuplicateKeyError:
            # 行已存在但被并发方抢先领取/创建（upsert 撞唯一 _id）：领取失败即跳过
            return
        if claimed is None:
            return
        folder = Path(__file__).resolve().parents[2] / "data" / "backups"
        folder.mkdir(parents=True, exist_ok=True)
        stamp = _now().strftime("%Y%m%dT%H%M%SZ")
        (folder / f"rehab-backup-{stamp}.json").write_bytes(await backup_bytes(db))


backup_schedule = BackupSchedule()


async def record_login_notice(db, user_id: str) -> None:
    row = await db.system_settings.find_one({"_id": "system"})
    if row and row.get("login_notifications") is False:
        return
    from app.services.notification_service import NotificationService
    await NotificationService.create_notification(
        db, "登录提醒", "这个账号刚刚完成了一次登录。", str(user_id), "系统", "admin",
        str(user_id), notification_type="login")

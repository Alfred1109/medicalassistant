"""Admin settings that change a real local behavior, plus a secret-stripped backup."""
import json
import logging
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from fastapi.responses import Response

LOG_LEVELS = {"debug": logging.DEBUG, "info": logging.INFO, "warning": logging.WARNING, "error": logging.ERROR}
BACKUP_COLLECTIONS = (
    "users", "organizations", "tags", "system_settings", "user_preferences",
    "consent_templates", "consent_documents", "followup_records", "rehab_plans",
    "exercises", "notifications", "audit_logs",
)
SECRET_KEYS = {"password", "password_hash", "hashed_password", "refresh_tokens", "avatar_bytes",
               "access_token", "secret", "api_key"}


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


def _clean(value):
    if isinstance(value, dict):
        return {key: _clean(item) for key, item in value.items() if key not in SECRET_KEYS}
    if isinstance(value, list):
        return [_clean(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if type(value).__name__ == "ObjectId":
        return str(value)
    return value


async def backup_bytes(db) -> bytes:
    exported = {"generated_at": _now().isoformat(), "collections": {}}
    for name in BACKUP_COLLECTIONS:
        rows = []
        cursor = db[name].find({})
        async for row in cursor:
            rows.append(_clean(row))
            if len(rows) >= 2000:
                break
        exported["collections"][name] = {"count": len(rows), "capped": len(rows) >= 2000, "rows": rows}
    return json.dumps(exported, ensure_ascii=False).encode()


async def build_backup(db):
    body = await backup_bytes(db)
    await db.system_settings.update_one(
        {"_id": "system"}, {"$set": {"last_backup_at": _now()}}, upsert=True)
    return Response(content=body, media_type="application/json", headers={
        "Content-Disposition": "attachment; filename=rehab-backup.json",
        "Cache-Control": "no-store",
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
                logging.warning("定时备份没有写成文件")
            await asyncio.sleep(3600)

    async def run_if_due(self, db):
        from pathlib import Path
        row = await db.system_settings.find_one({"_id": "system"}) or {}
        hours = {"hourly": 1, "daily": 24, "weekly": 24 * 7, "monthly": 24 * 30}.get(row.get("backup_frequency") or "daily", 24)
        last = row.get("last_backup_at")
        if isinstance(last, datetime) and last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        if isinstance(last, datetime) and _now() - last < timedelta(hours=hours):
            return
        folder = Path(__file__).resolve().parents[2] / "data" / "backups"
        folder.mkdir(parents=True, exist_ok=True)
        stamp = _now().strftime("%Y%m%dT%H%M%SZ")
        (folder / f"rehab-backup-{stamp}.json").write_bytes(await backup_bytes(db))
        await db.system_settings.update_one(
            {"_id": "system"}, {"$set": {"last_backup_at": _now()}}, upsert=True)


backup_schedule = BackupSchedule()


async def record_login_notice(db, user_id: str) -> None:
    row = await db.system_settings.find_one({"_id": "system"})
    if row and row.get("login_notifications") is False:
        return
    from app.services.notification_service import NotificationService
    await NotificationService.create_notification(
        db, "登录提醒", "这个账号刚刚完成了一次登录。", str(user_id), "系统", "admin",
        str(user_id), notification_type="login")

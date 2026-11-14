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
        # - 主条件：调度时间戳为 date 且已过窗口（$lte，类型限定下不匹配 null/缺失）；
        # - B1 修复：调度时间戳存在但为非 date 标量（string/int/long/double，
        #   legacy 外部脚本/运维工具写入的形态）也视为到点。Mongo 的比较算子
        #   带 BSON 类型栅栏：$lte 接 date 永不匹配字符串/数字时间戳，若只保留
        #   $lte 分支，此类行的领取必然落空 → upsert 撞唯一 _id → 领取永久
        #   停摆且无日志。Python 预判对非 datetime 一律视同到点，两端语义在此
        #   对齐；领取成功后 $set 写回 datetime（_now()），时间戳形态随之归一。
        # - legacy 回退：无调度时间戳时按旧的 last_backup_at 判定（row.get 回退），
        #   同样带 date/非 date 标量两个分支；
        # - 两个时间戳都缺失（从未导出）或调度时间戳为 null：视为到点
        #   （与 row.get 命中 None 后跳过 isinstance 判断的行为一致）。
        cutoff = _now() - timedelta(hours=hours)
        _legacy_scalar_types = ["string", "int", "long", "double"]
        due = {"$or": [
            {"last_scheduled_export_at": {"$type": "date", "$lte": cutoff}},
            {"last_scheduled_export_at": {"$type": _legacy_scalar_types}},
            {"last_scheduled_export_at": None, "last_backup_at": {"$type": "date", "$lte": cutoff}},
            {"last_scheduled_export_at": None, "last_backup_at": {"$type": _legacy_scalar_types}},
            {"last_scheduled_export_at": None, "last_backup_at": None},
            {"last_scheduled_export_at": {"$eq": None, "$exists": True}},
        ]}
        try:
            claimed = await db.system_settings.find_one_and_update(
                {"_id": "system", **due},
                {"$set": {"last_scheduled_export_at": _now()}},
                upsert=True, return_document=ReturnDocument.AFTER)
        except DuplicateKeyError:
            # 行已存在但领取 filter 未命中：要么并发方抢先领取（date 时间戳已被
            # 推进过窗口），要么行上时间戳的 BSON 类型仍未落入任何 $or 分支
            # （B1 的类型落空形态）。读回区分两者并留日志——此前该分支静默
            # return，类型落空会让定时备份永久停摆而无任何痕迹。
            current = await db.system_settings.find_one({"_id": "system"}) or {}
            last = current.get("last_scheduled_export_at", current.get("last_backup_at"))
            if isinstance(last, datetime) and _now() - last < timedelta(hours=hours):
                logging.info("定时业务导出被并发进程抢先领取，本轮跳过")
            else:
                logging.warning(
                    "定时业务导出领取条件未命中但行已存在（时间戳类型异常或窗口判定落空），"
                    "本轮跳过：last_scheduled_export_at=%r last_backup_at=%r",
                    current.get("last_scheduled_export_at"), current.get("last_backup_at"))
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

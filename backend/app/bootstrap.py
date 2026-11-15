"""应用启动与关闭时的后台服务编排。

路由、中间件和异常处理留在 main。这里只排数据库连上之后要拉起的进程内
服务，以及关闭时的对称停止。连接本身的建立与断开仍由 main 负责，这样
启动失败的传播路径不变。
"""
from app.api.websockets import setup_websockets
from app.core.config import settings
from app.core.logging import app_logger as logger
from app.db.indexes import ensure_communication_indexes, ensure_patient_scope_indexes, ensure_timeline_indexes
from app.db.mongodb import db as mongodb_state
from app.integrations.identity.config import oidc_settings
from app.integrations.identity.service import ensure_identity_indexes
from app.operations.runtime import backup_schedule
from app.services.followup_reminder_service import disposition_runtime, reminder_runtime


async def start_background_services(app) -> None:
    """数据库已连接后拉起 WebSocket、索引声明和后台循环。"""
    setup_websockets(app)
    logger.info("WebSocket服务已初始化")
    await ensure_communication_indexes(mongodb_state.db)
    await ensure_patient_scope_indexes(mongodb_state.db)
    await ensure_timeline_indexes(mongodb_state.db)
    if oidc_settings.enabled:
        await ensure_identity_indexes(mongodb_state.db)
    await reminder_runtime.start(
        mongodb_state.db,
        enabled=settings.FOLLOWUP_REMINDERS_ENABLED,
        interval=settings.FOLLOWUP_REMINDERS_POLL_SECONDS)
    await disposition_runtime.start(
        mongodb_state.db, interval=settings.FOLLOWUP_REMINDERS_POLL_SECONDS)
    await backup_schedule.start(mongodb_state.db)


async def stop_background_services() -> None:
    """按启动的逆序停掉后台循环。数据库连接由调用方关闭。"""
    await reminder_runtime.stop()
    await disposition_runtime.stop()
    await backup_schedule.stop()

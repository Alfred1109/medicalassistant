"""审计落库端口（core 层）。

core 是底座，不得反向依赖 services：审计写入的具体实现由上层注入
（组合根调用 configure_audit_sink），未注入时使用本模块内置的集合写入实现
——落库形状（AuditLogCreate + created_at + ip_address）与
services.audit_log_service.AuditLogService 逐字一致。

调用方只需要一个「能写审计」的最小接口（AuditSink），不必知道实现落在
services、db 还是别的层。
"""
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional, Protocol, runtime_checkable

from app.schemas.audit_log import AuditLogCreate


@runtime_checkable
class AuditSink(Protocol):
    """审计落库最小接口（core 定义，上层实现）。"""

    async def create_log(self, log_data: AuditLogCreate,
                         ip_address: Optional[str] = None) -> Any:
        """写入一条审计记录。"""

    async def log_permission_check(self, user_id: str, permission: str,
                                   resource_id: Optional[str] = None,
                                   is_granted: bool = True,
                                   ip_address: Optional[str] = None,
                                   details: Optional[Dict[str, Any]] = None) -> Any:
        """写入一条权限检查审计记录。"""


async def write_audit_log(db, log_data: AuditLogCreate,
                          ip_address: Optional[str] = None,
                          session=None) -> Dict[str, Any]:
    """audit_logs 集合写入（落库形状的唯一事实来源）。

    与 AuditLogService.create_log 同形：model_dump → 补 ip_address/created_at
    → insert_one；调用方拿到的返回值含落库后的 id。
    """
    log_dict = log_data.model_dump()
    if ip_address:
        log_dict["ip_address"] = ip_address
    log_dict["created_at"] = datetime.now(timezone.utc)
    if session is None:
        result = await db.audit_logs.insert_one(log_dict)
    else:
        result = await db.audit_logs.insert_one(log_dict, session=session)
    log_dict.pop("_id", None)
    return {**log_dict, "id": str(result.inserted_id)}


class MongoAuditSink:
    """内置审计实现：直接写 audit_logs 集合（未注入上层实现时的兜底）。"""

    def __init__(self, db):
        self.db = db

    async def create_log(self, log_data: AuditLogCreate,
                         ip_address: Optional[str] = None) -> Any:
        return await write_audit_log(self.db, log_data, ip_address)

    async def log_permission_check(self, user_id: str, permission: str,
                                   resource_id: Optional[str] = None,
                                   is_granted: bool = True,
                                   ip_address: Optional[str] = None,
                                   details: Optional[Dict[str, Any]] = None) -> Any:
        log_data = AuditLogCreate(
            user_id=user_id,
            action="access",
            resource_type="permission",
            resource_id=resource_id,
            status="success" if is_granted else "failure",
            details={**(details or {}), "permission": permission},
        )
        return await self.create_log(log_data, ip_address)


_audit_sink_factory: Optional[Callable[[Any], AuditSink]] = None


def configure_audit_sink(factory: Callable[[Any], AuditSink]) -> None:
    """注入审计落库实现（组合根调用；传入按 db 构造 sink 的工厂）。"""
    global _audit_sink_factory
    _audit_sink_factory = factory


def resolve_audit_sink(db) -> AuditSink:
    """按 db 解析审计落库实现：优先上层注入的实现，否则用内置实现。"""
    if _audit_sink_factory is not None:
        return _audit_sink_factory(db)
    return MongoAuditSink(db)

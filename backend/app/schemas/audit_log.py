from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, Literal
from pydantic import BaseModel, Field, field_validator, model_validator


AuditSortField = Literal["created_at", "user_id", "action", "resource_type", "resource_id", "status"]
AUDIT_SORT_FIELDS = frozenset({"created_at", "user_id", "action", "resource_type", "resource_id", "status"})


def utc_datetime(value: datetime) -> datetime:
    """Legacy naive audit dates were written with utcnow(), so they represent UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class AuditLogBase(BaseModel):
    """审计日志基础Schema"""
    action: str = Field(..., description="操作类型，如login, logout, access, modify, grant, revoke等")
    resource_type: str = Field(..., description="资源类型，如permission, role, user等")
    resource_id: Optional[str] = Field(None, description="资源ID")
    details: Optional[Dict[str, Any]] = Field(default_factory=dict, description="详细信息")
    ip_address: Optional[str] = Field(None, description="IP地址")
    status: str = Field("success", description="操作状态，success或failure")


class AuditLogCreate(AuditLogBase):
    """创建审计日志的Schema"""
    user_id: str = Field(..., description="执行操作的用户ID")


class AuditLogResponse(AuditLogBase):
    """审计日志响应Schema"""
    id: str = Field(..., description="审计日志ID")
    user_id: str = Field(..., description="执行操作的用户ID")
    created_at: datetime = Field(..., description="创建时间")

    @field_validator("created_at")
    @classmethod
    def timestamp_is_utc(cls, value: datetime) -> datetime:
        return utc_datetime(value)
    
    class Config:
        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class AuditLogFilter(BaseModel):
    """审计日志过滤条件"""
    user_id: Optional[str] = Field(None, description="用户ID")
    action: Optional[str] = Field(None, description="操作类型")
    resource_type: Optional[str] = Field(None, description="资源类型")
    resource_id: Optional[str] = Field(None, description="资源ID")
    status: Optional[Literal["success", "failure"]] = Field(None, description="操作状态")
    start_date: Optional[datetime] = Field(None, description="开始日期")
    end_date: Optional[datetime] = Field(None, description="结束日期")

    @field_validator("start_date", "end_date")
    @classmethod
    def filter_timestamp_is_utc(cls, value: Optional[datetime]) -> Optional[datetime]:
        return utc_datetime(value) if value is not None else None

    @model_validator(mode="after")
    def range_is_ordered(self):
        if self.start_date is not None and self.end_date is not None and self.start_date > self.end_date:
            raise ValueError("结束时间不能早于开始时间")
        return self
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class AuditLogList(BaseModel):
    """审计日志列表响应"""
    total: int = Field(..., description="总数")
    items: List[AuditLogResponse] = Field(..., description="日志列表")
    
    class Config:
        from_attributes = True

"""
通用模型模块
提供通用响应模型和分页模型
"""
from typing import Generic, List, Optional, TypeVar, Dict, Any, Union
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime

from app.core.config import settings

T = TypeVar('T')

class ResponseModel(BaseModel, Generic[T]):
    """通用API响应模型"""
    success: bool = True
    data: Optional[T] = None
    message: Optional[str] = None
    error: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    request_id: Optional[str] = None
    process_time: Optional[float] = None
    version: Optional[str] = Field(default=settings.API_VERSION)
    
    model_config = ConfigDict(
        json_encoders={
            datetime: lambda dt: dt.isoformat()
        }
    )
    
    @classmethod
    def success_response(
        cls, 
        data: Optional[T] = None, 
        message: Optional[str] = None,
        request_id: Optional[str] = None,
        process_time: Optional[float] = None
    ) -> "ResponseModel[T]":
        """创建成功响应"""
        return cls(
            success=True,
            data=data,
            message=message,
            request_id=request_id if settings.API_RESPONSE_INCLUDE_REQUEST_ID else None,
            process_time=process_time if settings.API_RESPONSE_INCLUDE_PROCESS_TIME else None,
            version=settings.API_VERSION if settings.API_RESPONSE_INCLUDE_VERSION else None
        )
    
    @classmethod
    def error_response(
        cls,
        error: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        request_id: Optional[str] = None,
        process_time: Optional[float] = None
    ) -> "ResponseModel[None]":
        """创建错误响应"""
        return cls(
            success=False,
            data=None,
            message=message,
            error=error,
            details=details,
            request_id=request_id if settings.API_RESPONSE_INCLUDE_REQUEST_ID else None,
            process_time=process_time if settings.API_RESPONSE_INCLUDE_PROCESS_TIME else None,
            version=settings.API_VERSION if settings.API_RESPONSE_INCLUDE_VERSION else None
        )


class PaginationParams(BaseModel):
    """分页参数"""
    page: int = Field(default=1, ge=1, description="页码，从1开始")
    page_size: int = Field(
        default=settings.DEFAULT_PAGE_SIZE,
        ge=1,
        le=settings.MAX_PAGE_SIZE,
        description=f"每页条数，最大{settings.MAX_PAGE_SIZE}"
    )
    
    def get_skip(self) -> int:
        """获取跳过的记录数"""
        return (self.page - 1) * self.page_size
    
    def get_limit(self) -> int:
        """获取限制的记录数"""
        return self.page_size


class PaginatedResponse(BaseModel, Generic[T]):
    """分页响应模型"""
    items: List[T]
    total: int
    page: int
    page_size: int
    pages: int
    
    @classmethod
    def create(
        cls,
        items: List[T],
        total: int,
        params: PaginationParams
    ) -> "PaginatedResponse[T]":
        """创建分页响应"""
        pages = (total + params.page_size - 1) // params.page_size if total > 0 else 1
        return cls(
            items=items,
            total=total,
            page=params.page,
            page_size=params.page_size,
            pages=pages
        )


class HealthCheck(BaseModel):
    """健康检查响应"""
    status: str
    version: str = settings.API_VERSION
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    environment: str = settings.ENVIRONMENT
    components: Dict[str, Dict[str, Any]] = {}
    
    model_config = ConfigDict(
        json_encoders={
            datetime: lambda dt: dt.isoformat()
        }
    )


class ErrorDetail(BaseModel):
    """错误详情"""
    loc: List[Union[str, int]] = []
    msg: str
    type: str 
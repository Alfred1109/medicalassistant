"""
通用模式定义
定义在多个模块中使用的通用数据结构和响应模型
"""
from typing import Any, Dict, Generic, List, Optional, TypeVar, Union
from pydantic import BaseModel, Field

# 泛型类型变量
T = TypeVar('T')

class ResponseModel(BaseModel):
    """
    标准API响应模型
    
    用于包装所有API响应，提供一致的响应格式
    """
    success: bool = True
    message: str = "操作成功"
    data: Optional[Any] = None
    errors: Optional[List[str]] = None
    
    @classmethod
    def success_response(cls, data: Any = None, message: str = "操作成功") -> "ResponseModel":
        """创建成功响应"""
        return cls(
            success=True,
            message=message,
            data=data
        )
    
    @classmethod
    def error_response(cls, message: str = "操作失败", errors: List[str] = None) -> "ResponseModel":
        """创建错误响应"""
        return cls(
            success=False,
            message=message,
            errors=errors or []
        )

class PaginatedResponse(Generic[T], BaseModel):
    """
    分页响应模型
    
    用于返回分页数据的标准格式
    """
    items: List[T]
    total: int
    page: int
    page_size: int
    pages: int
    
    @classmethod
    def create(cls, items: List[T], total: int, page: int, page_size: int) -> "PaginatedResponse[T]":
        """创建分页响应"""
        pages = (total + page_size - 1) // page_size if page_size > 0 else 0
        return cls(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            pages=pages
        )

class StatusMessage(BaseModel):
    """简单的状态消息响应"""
    status: str
    message: str 
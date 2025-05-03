"""
API工具模块
提供API路由和控制器相关的工具函数和装饰器
"""
from functools import wraps
from typing import Callable, Dict, Any, List, Optional, Type, TypeVar, Union
import inspect
import time
from fastapi import HTTPException, status, Depends
from pydantic import BaseModel, ValidationError

from app.core.logging import app_logger as logger
from app.core.exceptions import (
    AppBaseException, ResourceNotFoundException, 
    AuthorizationException, ValidationException
)
from app.schemas.common import ResponseModel


T = TypeVar('T')

def api_route(
    *,
    roles: Optional[List[str]] = None,
    permissions: Optional[List[str]] = None,
    response_model: Optional[Type[BaseModel]] = None,
    error_responses: Optional[Dict[int, Dict[str, Any]]] = None,
    description: Optional[str] = None,
    summary: Optional[str] = None
):
    """
    API路由装饰器，统一处理权限检查和异常
    
    参数:
        roles: 允许访问的角色列表
        permissions: 需要的权限列表
        response_model: 响应模型类
        error_responses: 错误响应字典 {状态码: 响应信息}
        description: 路由描述
        summary: 路由摘要
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            
            # 检查当前用户和权限
            if roles or permissions:
                # 从kwargs中提取当前用户
                current_user = None
                for arg_name, arg_value in kwargs.items():
                    if arg_name == "current_user":
                        current_user = arg_value
                        break
                
                # 检查角色权限
                if current_user:
                    # 角色检查
                    if roles and current_user.role not in roles:
                        logger.warning(
                            f"权限不足: 用户 {current_user.id} 角色 {current_user.role} 尝试访问需要角色 {roles} 的路由"
                        )
                        raise AuthorizationException(message="权限不足，您的角色无法访问此资源")
                    
                    # 权限检查（如果项目有详细的权限系统）
                    if permissions and not all(perm in (current_user.permissions or []) for perm in permissions):
                        logger.warning(
                            f"权限不足: 用户 {current_user.id} 权限不足，需要权限 {permissions}"
                        )
                        raise AuthorizationException(message="权限不足，您没有执行此操作的权限")
            
            try:
                # 执行原始路由处理函数
                result = await func(*args, **kwargs)
                
                # 计算处理时间
                process_time = time.time() - start_time
                
                # 如果结果已经是ResponseModel，直接返回
                if isinstance(result, ResponseModel):
                    if not result.process_time:
                        result.process_time = process_time
                    return result
                
                # 如果结果不是ResponseModel，则包装为成功响应
                if response_model and not isinstance(result, ResponseModel):
                    # 将结果转换为response_model
                    if isinstance(result, dict) and inspect.isclass(response_model):
                        try:
                            # 尝试将字典转换为响应模型
                            result = response_model(**result)
                        except ValidationError as e:
                            logger.error(f"响应模型验证错误: {str(e)}")
                            raise ValidationException(
                                message="服务器响应格式错误",
                                errors=[{"msg": err["msg"], "loc": err["loc"]} for err in e.errors()]
                            )
                
                # 封装结果为统一响应格式
                return ResponseModel.success_response(
                    data=result,
                    process_time=process_time
                )
                
            except AppBaseException as e:
                # 记录异常并转换为HTTP异常
                logger.warning(
                    f"业务异常: {e.error_code} - {e.message}",
                    extra={"details": e.details}
                )
                raise e.to_http_exception()
                
            except HTTPException:
                # 直接传递HTTP异常
                raise
                
            except ValidationError as e:
                # 处理验证错误
                logger.warning(f"验证错误: {str(e)}")
                raise ValidationException(
                    message="请求数据验证失败",
                    errors=[{"msg": err["msg"], "loc": err["loc"]} for err in e.errors()]
                ).to_http_exception()
                
            except Exception as e:
                # 处理未预期的异常
                logger.error(
                    f"路由处理异常: {func.__name__} - {type(e).__name__}: {str(e)}",
                    exc_info=True
                )
                # 对于未处理的异常，返回500错误
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail={
                        "error": "INTERNAL_SERVER_ERROR",
                        "message": "服务器内部错误，请稍后再试"
                    }
                )
                
        # 返回装饰后的函数
        return wrapper
    
    return decorator


def entity_resolver(
    entity_type: str, 
    entity_service: Any,
    id_param: str = "id",
    required: bool = True
):
    """
    实体解析器，根据ID查找实体
    
    参数:
        entity_type: 实体类型名称(用于错误消息)
        entity_service: 实体服务对象或方法
        id_param: ID参数名
        required: 实体是否必须存在
        
    返回:
        依赖函数，返回解析后的实体
    """
    async def resolver(**kwargs):
        entity_id = kwargs.get(id_param)
        if not entity_id:
            if required:
                raise ValidationException(message=f"{entity_type} ID不能为空")
            return None
            
        # 根据服务类型处理
        if callable(entity_service):
            # 如果传入的是函数，直接调用
            entity = await entity_service(entity_id)
        else:
            # 如果传入的是服务对象，假设有get_by_id方法
            entity = await entity_service.get_by_id(entity_id)
            
        if not entity and required:
            raise ResourceNotFoundException(
                resource_type=entity_type,
                resource_id=entity_id
            )
            
        return entity
    
    return Depends(resolver)


def pagination_params(
    default_page: int = 1,
    default_page_size: int = 50,
    max_page_size: int = 100
):
    """
    分页参数依赖
    
    参数:
        default_page: 默认页码
        default_page_size: 默认每页条数
        max_page_size: 最大每页条数
        
    返回:
        依赖函数，返回分页参数字典
    """
    def get_pagination(
        page: int = default_page,
        page_size: int = default_page_size
    ):
        if page < 1:
            page = 1
            
        if page_size < 1:
            page_size = default_page_size
            
        if page_size > max_page_size:
            page_size = max_page_size
            
        skip = (page - 1) * page_size
        
        return {
            "page": page,
            "page_size": page_size,
            "skip": skip,
            "limit": page_size
        }
    
    return Depends(get_pagination)


def format_response(data: Any) -> Dict[str, Any]:
    """
    格式化响应数据
    
    参数:
        data: 要格式化的数据
        
    返回:
        格式化后的数据字典
    """
    from app.core.utils import format_document
    
    if isinstance(data, dict):
        return format_document(data)
    elif isinstance(data, list):
        return [format_document(item) if isinstance(item, dict) else item for item in data]
    else:
        return data 
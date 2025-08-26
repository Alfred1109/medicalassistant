"""
异常处理模块
提供统一的应用程序异常类和处理机制
"""
from typing import Optional, Any, Dict, List
from fastapi import HTTPException, status

# 基础异常类
class AppBaseException(Exception):
    """应用基础异常类"""
    def __init__(
        self, 
        message: str = "应用程序发生错误", 
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        error_code: str = "INTERNAL_ERROR",
        details: Optional[Dict[str, Any]] = None
    ):
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        self.details = details or {}
        super().__init__(self.message)

    def to_dict(self) -> Dict[str, Any]:
        """将异常转换为字典表示"""
        result = {
            "error": self.error_code,
            "message": self.message,
        }
        if self.details:
            result["details"] = self.details
        return result
    
    def to_http_exception(self) -> HTTPException:
        """将应用异常转换为FastAPI的HTTPException"""
        return HTTPException(
            status_code=self.status_code,
            detail=self.to_dict()
        )


# 身份验证和授权异常
class AuthenticationException(AppBaseException):
    """认证失败异常"""
    def __init__(
        self, 
        message: str = "认证失败", 
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            message=message,
            status_code=status.HTTP_401_UNAUTHORIZED,
            error_code="AUTHENTICATION_ERROR",
            details=details
        )


class AuthorizationException(AppBaseException):
    """授权失败异常"""
    def __init__(
        self, 
        message: str = "权限不足", 
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            message=message,
            status_code=status.HTTP_403_FORBIDDEN,
            error_code="AUTHORIZATION_ERROR",
            details=details
        )


# 资源相关异常
class ResourceNotFoundException(AppBaseException):
    """资源不存在异常"""
    def __init__(
        self, 
        resource_type: str,
        resource_id: Optional[str] = None,
        message: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        if not message:
            message = f"{resource_type} 不存在"
            if resource_id:
                message = f"{resource_type}(ID: {resource_id}) 不存在"
        
        super().__init__(
            message=message,
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="RESOURCE_NOT_FOUND",
            details=details or {"resource_type": resource_type, "resource_id": resource_id}
        )


class ResourceConflictException(AppBaseException):
    """资源冲突异常"""
    def __init__(
        self, 
        resource_type: str,
        message: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        if not message:
            message = f"{resource_type} 发生冲突"
        
        super().__init__(
            message=message,
            status_code=status.HTTP_409_CONFLICT,
            error_code="RESOURCE_CONFLICT",
            details=details or {"resource_type": resource_type}
        )


# 数据库相关异常
class DatabaseException(AppBaseException):
    """数据库操作异常"""
    def __init__(
        self, 
        message: str = "数据库操作失败", 
        original_error: Optional[Exception] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        error_details = details or {}
        if original_error:
            error_details["original_error"] = str(original_error)
            
        super().__init__(
            message=message,
            error_code="DATABASE_ERROR",
            details=error_details
        )


# 验证相关异常
class ValidationException(AppBaseException):
    """数据验证异常"""
    def __init__(
        self, 
        message: str = "数据验证失败", 
        errors: Optional[List[Dict[str, Any]]] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        error_details = details or {}
        if errors:
            error_details["errors"] = errors
            
        super().__init__(
            message=message,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            error_code="VALIDATION_ERROR",
            details=error_details
        )


# 业务逻辑异常
class BusinessLogicException(AppBaseException):
    """业务逻辑异常"""
    def __init__(
        self, 
        message: str, 
        error_code: str = "BUSINESS_ERROR",
        status_code: int = status.HTTP_400_BAD_REQUEST,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            message=message,
            status_code=status_code,
            error_code=error_code,
            details=details
        )


# 第三方服务异常
class ExternalServiceException(AppBaseException):
    """外部服务调用异常"""
    def __init__(
        self, 
        message: str = "外部服务调用失败", 
        service_name: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        error_details = details or {}
        if service_name:
            error_details["service_name"] = service_name
            
        super().__init__(
            message=message,
            error_code="EXTERNAL_SERVICE_ERROR",
            details=error_details
        ) 
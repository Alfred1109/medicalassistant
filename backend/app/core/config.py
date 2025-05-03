from pydantic_settings import BaseSettings
from pydantic import AnyHttpUrl, field_validator
from typing import List, Optional, Union, Dict, Any
import os
from dotenv import load_dotenv
import secrets

load_dotenv()

class Settings(BaseSettings):
    # API Settings
    API_V1_STR: str = "/api"
    PROJECT_NAME: str = "Medical Rehabilitation Assistant"
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    DEBUG: bool = os.getenv("DEBUG", "False").lower() in ("true", "1", "t")
    API_VERSION: str = "0.1.0"
    
    # CORS Settings
    BACKEND_CORS_ORIGINS: List[str] = ["*"]
    
    @field_validator("BACKEND_CORS_ORIGINS", mode='before')
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> Union[List[str], str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",")]
        elif isinstance(v, (list, str)):
            return v
        raise ValueError(v)
        
    # MongoDB Settings
    MONGODB_URL: str = "mongodb://localhost:27017"
    MONGODB_DB_NAME: str = os.getenv("DATABASE_NAME", "rehab_assistant")
    # MongoDB连接池设置
    MONGODB_MAX_CONNECTIONS: int = int(os.getenv("MONGODB_MAX_CONNECTIONS", "10"))
    MONGODB_MIN_CONNECTIONS: int = int(os.getenv("MONGODB_MIN_CONNECTIONS", "1"))
    MONGODB_MAX_IDLE_TIME_MS: int = int(os.getenv("MONGODB_MAX_IDLE_TIME_MS", "60000"))
    MONGODB_WAIT_QUEUE_TIMEOUT_MS: int = int(os.getenv("MONGODB_WAIT_QUEUE_TIMEOUT_MS", "2000"))
    MONGODB_CONNECT_TIMEOUT_MS: int = int(os.getenv("MONGODB_CONNECT_TIMEOUT_MS", "5000"))
    MONGODB_SERVER_SELECTION_TIMEOUT_MS: int = int(os.getenv("MONGODB_SERVER_SELECTION_TIMEOUT_MS", "30000"))
    
    # Authentication Settings
    SECRET_KEY: str = secrets.token_urlsafe(32)
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days
    
    # LLM/Agent Settings
    DEFAULT_LLM_MODEL: str = os.getenv("DEFAULT_LLM_MODEL", "gpt-4-turbo")
    OPENAI_API_KEY: Optional[str] = os.getenv("OPENAI_API_KEY")
    ANTHROPIC_API_KEY: Optional[str] = os.getenv("ANTHROPIC_API_KEY")
    
    # 用户认证相关
    FIRST_SUPERUSER: str = "admin@example.com"
    FIRST_SUPERUSER_PASSWORD: str = "admin123"
    
    # 测试用户
    TEST_USER: str = "test@example.com"
    TEST_USER_PASSWORD: str = "password123"
    
    # LLM API配置
    LLM_API_KEY: str = "bc16c0aa-81fe-49a0-a094-98a1c0b23c76"
    LLM_API_BASE_URL: str = "https://ark.cn-beijing.volces.com/api/v3"
    LLM_API_MODEL: str = "deepseek-v3-241226"
    
    # 系统日志级别
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_PATH: str = os.getenv("LOG_PATH", "logs")
    
    # API响应格式
    API_RESPONSE_INCLUDE_REQUEST_ID: bool = True
    API_RESPONSE_INCLUDE_PROCESS_TIME: bool = True
    API_RESPONSE_INCLUDE_VERSION: bool = True
    
    # 操作限制
    MAX_PAGE_SIZE: int = 100
    DEFAULT_PAGE_SIZE: int = 20
    API_RATE_LIMIT: int = int(os.getenv("API_RATE_LIMIT", "100"))  # 每分钟请求数
    FILE_UPLOAD_MAX_SIZE: int = 10 * 1024 * 1024  # 10MB
    
    # 数据转换
    AUTO_CAMEL_CASE: bool = True  # 自动将响应数据转为驼峰命名
    
    # 缓存设置
    CACHE_ENABLED: bool = os.getenv("CACHE_ENABLED", "False").lower() in ("true", "1", "t")
    CACHE_TTL_SECONDS: int = int(os.getenv("CACHE_TTL_SECONDS", "300"))  # 5分钟
    
    # 健康检查
    HEALTH_CHECK_INCLUDE_DB: bool = True
    
    model_config = {
        "case_sensitive": True
    }
    
    def get_api_url(self) -> str:
        """获取API URL"""
        return f"{self.API_V1_STR}"
    
    def is_development(self) -> bool:
        """检查是否为开发环境"""
        return self.ENVIRONMENT.lower() == "development"
    
    def is_production(self) -> bool:
        """检查是否为生产环境"""
        return self.ENVIRONMENT.lower() == "production"
    
    def is_testing(self) -> bool:
        """检查是否为测试环境"""
        return self.ENVIRONMENT.lower() == "testing"
    
    def get_response_envelope(self, data: Any = None, message: str = None) -> Dict[str, Any]:
        """生成标准响应封装"""
        result = {
            "success": True,
            "data": data
        }
        
        if message:
            result["message"] = message
            
        if self.API_RESPONSE_INCLUDE_VERSION:
            result["version"] = self.API_VERSION
            
        return result


settings = Settings() 
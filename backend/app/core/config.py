from pydantic_settings import BaseSettings
from pydantic import AnyHttpUrl, field_validator
from typing import List, Optional, Union
import os
from dotenv import load_dotenv
import secrets

load_dotenv()

class Settings(BaseSettings):
    # API Settings
    API_V1_STR: str = "/api"
    PROJECT_NAME: str = "Medical Rehabilitation Assistant"
    
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
    
    model_config = {
        "case_sensitive": True
    }


settings = Settings() 
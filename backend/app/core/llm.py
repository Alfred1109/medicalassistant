"""Shared configuration boundary for the external LLM provider."""
from app.core.config import settings
from app.core.exceptions import AppBaseException


class LLMConfigurationError(AppBaseException):
    def __init__(self):
        super().__init__(
            message="AI服务尚未配置，请联系管理员。",
            status_code=503,
            error_code="LLM_NOT_CONFIGURED",
        )


def require_llm_api_key() -> str:
    secret = settings.LLM_API_KEY
    value = secret.get_secret_value().strip() if secret is not None else ""
    if not value:
        raise LLMConfigurationError()
    return value

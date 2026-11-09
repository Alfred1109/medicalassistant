"""服务凭证配置：轮换双活窗口、哈希参数与限流预留位。

参数对齐 113.44 侧 e44a10f 惯例：PBKDF2-SHA256 加盐慢哈希、
双活轮换窗口默认 24h。全部参数可经环境变量（前缀 SERVICE_CREDENTIALS_）覆盖。
"""
from typing import Optional

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# PBKDF2 迭代次数允许范围：下限防止误配成弱参数，上限防止集合内被写入
# 超大迭代值导致验证请求被拖垮（CPU DoS）。
MIN_PBKDF2_ITERATIONS = 100_000
MAX_PBKDF2_ITERATIONS = 2_000_000

# 双活窗口允许范围：0（轮换即失效）到 7 天。
MAX_ROTATION_OVERLAP_SECONDS = 7 * 24 * 3600


class ServiceCredentialSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SERVICE_CREDENTIALS_", extra="ignore")

    # 轮换双活窗口（秒）：轮换后旧凭证在该窗口内仍可验证，默认 24h。
    # 0 表示轮换即失效；不能配置为负数或超过 7 天。
    rotation_overlap_seconds: int = 24 * 3600

    # PBKDF2-SHA256 迭代次数，默认对齐 113.44 e44a10f 的 600000。
    pbkdf2_iterations: int = 600_000

    # 限流预留位：仅作为新凭证默认配额（次/分钟）的来源；None=暂不限。
    # 注意：限流执行逻辑尚未实现，本字段当前只随凭证文档持久化，
    # 不构成已生效的限流能力，不能按"已有限流"对外宣称。
    rate_limit_per_minute: Optional[int] = None

    @model_validator(mode="after")
    def validate_ranges(self):
        if not 0 <= self.rotation_overlap_seconds <= MAX_ROTATION_OVERLAP_SECONDS:
            raise ValueError("rotation_overlap_seconds must be within 0–7 days")
        if not MIN_PBKDF2_ITERATIONS <= self.pbkdf2_iterations <= MAX_PBKDF2_ITERATIONS:
            raise ValueError("pbkdf2_iterations out of allowed range")
        if self.rate_limit_per_minute is not None and self.rate_limit_per_minute <= 0:
            raise ValueError("rate_limit_per_minute must be positive when set")
        return self


service_credential_settings = ServiceCredentialSettings()

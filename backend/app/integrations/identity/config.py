from urllib.parse import urlsplit
from typing import Literal

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from cryptography.fernet import Fernet


class OidcSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="OIDC_", extra="ignore")

    enabled: bool = False
    authentication_mode: Literal["legacy", "oidc"] = "legacy"
    issuer: str = ""
    client_id: str = ""
    client_secret: SecretStr = SecretStr("")
    public_base_url: str = ""
    session_seconds: int = 3600
    session_encryption_key: SecretStr = SecretStr("")

    @model_validator(mode="after")
    def validate_enabled(self):
        if self.authentication_mode == "oidc" and not self.enabled:
            raise ValueError("OIDC authentication mode requires the OIDC integration")
        if not self.enabled:
            return self
        for value in (self.issuer, self.public_base_url):
            parsed = urlsplit(value)
            if (parsed.scheme != "https" or not parsed.hostname or parsed.username
                    or parsed.password or parsed.query or parsed.fragment or value.endswith("/")):
                raise ValueError("OIDC requires exact HTTPS URLs without credentials, query, fragment or trailing slash")
        if not self.client_id or not self.client_secret.get_secret_value():
            raise ValueError("OIDC client credentials are required")
        try:
            Fernet(self.session_encryption_key.get_secret_value().encode("ascii"))
        except (ValueError, UnicodeError):
            raise ValueError("Independent OIDC session encryption key is required") from None
        if not 60 <= self.session_seconds <= 3600:
            raise ValueError("Application sessions must expire within 60–3600 seconds")
        return self

    @property
    def callback_uri(self):
        return self.public_base_url + "/api/auth/oidc/callback"

    @property
    def session_uri(self):
        return self.public_base_url + "/api/auth/session"


oidc_settings = OidcSettings()

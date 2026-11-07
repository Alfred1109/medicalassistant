"""113.44 表单平台 HTTP 客户端封装。

- 服务端对服务端凭证认证：Authorization: Bearer <client_id>.<secret>；
- 错误类型化：FormPlatformUnavailable（网络/超时）、AuthorizationRejected（远端 401/403）、
  FormPlatformError（其余远端错误），不吞错误、不把失败伪装成成功；
- 凭证只用于构造请求头，不写入日志与异常消息。
"""

from typing import Any, Dict, Optional

import httpx

from app.core.config import settings


class FormPlatformError(Exception):
    """远端表单平台返回的错误（含状态码与远端错误码）。"""

    def __init__(self, message: str, status_code: Optional[int] = None,
                 remote_code: Optional[str] = None):
        super().__init__(message)
        self.status_code = status_code
        self.remote_code = remote_code


class FormPlatformUnavailable(FormPlatformError):
    """无法连接远端（网络错误、超时、DNS 等）。"""


class AuthorizationRejected(FormPlatformError):
    """远端拒绝集成凭证或授权范围（401/403）。"""


class FormPlatformClient:
    """对 113.44 集成 API 的最小封装；仅覆盖填报会话所需端点。"""

    def __init__(self, base_url: str, client_id: str, client_secret: str,
                 timeout_seconds: float, transport: Optional[httpx.AsyncBaseTransport] = None):
        self._base_url = base_url.rstrip("/")
        self._client_id = client_id
        self._client_secret = client_secret
        self._timeout = httpx.Timeout(timeout_seconds)
        # transport 仅测试注入（httpx.MockTransport）；生产为 None
        self._transport = transport

    @classmethod
    def from_settings(cls) -> "FormPlatformClient":
        secret = settings.FORM_PLATFORM_CLIENT_SECRET
        if (not settings.FORM_PLATFORM_BASE_URL or not settings.FORM_PLATFORM_CLIENT_ID
                or secret is None):
            raise FormPlatformError(
                "表单平台集成未配置（FORM_PLATFORM_BASE_URL / CLIENT_ID / CLIENT_SECRET）")
        return cls(
            base_url=settings.FORM_PLATFORM_BASE_URL,
            client_id=settings.FORM_PLATFORM_CLIENT_ID,
            client_secret=secret.get_secret_value(),
            timeout_seconds=settings.FORM_PLATFORM_TIMEOUT_SECONDS,
        )

    def _auth_headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self._client_id}.{self._client_secret}"}

    async def _request(self, method: str, path: str,
                       json_body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=self._timeout,
                                         transport=self._transport) as client:
                response = await client.request(
                    method, f"{self._base_url}{path}",
                    json=json_body, headers=self._auth_headers(),
                )
        except httpx.HTTPError as exc:
            # httpx.HTTPError 覆盖 TransportError 与无效请求构造；均属"无法完成调用"
            raise FormPlatformUnavailable(f"表单平台不可达：{type(exc).__name__}") from exc

        if response.status_code in (401, 403):
            code = self._remote_code(response)
            raise AuthorizationRejected(
                "表单平台拒绝了集成凭证或授权范围", status_code=response.status_code,
                remote_code=code)
        if response.status_code >= 400:
            code = self._remote_code(response)
            message = self._remote_message(response) or "表单平台请求被拒绝"
            raise FormPlatformError(message, status_code=response.status_code, remote_code=code)

        try:
            return response.json()
        except ValueError as exc:
            raise FormPlatformError("表单平台返回了无法解析的响应",
                                    status_code=response.status_code) from exc

    @staticmethod
    def _remote_code(response: httpx.Response) -> Optional[str]:
        try:
            body = response.json()
        except ValueError:
            return None
        if isinstance(body, dict):
            code = body.get("code")
            if isinstance(code, str):
                return code
        return None

    @staticmethod
    def _remote_message(response: httpx.Response) -> Optional[str]:
        try:
            body = response.json()
        except ValueError:
            return None
        if isinstance(body, dict) and isinstance(body.get("message"), str):
            return body["message"]
        return None

    async def create_fill_session(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return await self._request("POST", "/integration/v1/fill-sessions", payload)

    async def get_fill_session(self, session_uuid: str) -> Dict[str, Any]:
        return await self._request("GET", f"/integration/v1/fill-sessions/{session_uuid}")

    async def cancel_fill_session(self, session_uuid: str) -> Dict[str, Any]:
        return await self._request("POST", f"/integration/v1/fill-sessions/{session_uuid}/cancel")

    async def get_response(self, response_id: int) -> Dict[str, Any]:
        return await self._request("GET", f"/integration/v1/responses/{response_id}")

"""113.44 表单平台 HTTP 客户端封装。

- 服务端对服务端凭证认证：Authorization: Bearer <client_id>.<secret>；
- 错误类型化：FormPlatformUnavailable（网络/超时）、AuthorizationRejected（远端 401/403）、
  FormPlatformError（其余远端错误），不吞错误、不把失败伪装成成功；
- 凭证只用于构造请求头，不写入日志与异常消息。
"""

from typing import Any, Dict, Optional
import re
from urllib.parse import quote, urlsplit

import httpx

from app.core.config import settings


class FormPlatformError(Exception):
    """远端表单平台返回的错误（含状态码与远端错误码）。"""

    def __init__(self, message: str, status_code: Optional[int] = None,
                 remote_code: Optional[str] = None,
                 details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.status_code = status_code
        self.remote_code = remote_code
        # 远端错误响应的 details（如 task_ref_conflict 的既有会话指针），不写入日志
        self.details = details if isinstance(details, dict) else None


class FormPlatformUnavailable(FormPlatformError):
    """无法连接远端（网络错误、超时、DNS 等）。"""


class AuthorizationRejected(FormPlatformError):
    """远端拒绝集成凭证或授权范围（401/403）。"""


class FormPlatformClient:
    """对 113.44 集成 API 的最小封装；仅覆盖填报会话所需端点。"""

    def __init__(self, base_url: str, client_id: str, client_secret: str,
                 timeout_seconds: float, transport: Optional[httpx.AsyncBaseTransport] = None,
                 verify_tls: bool = True):
        self._base_url = base_url.rstrip("/")
        self._client_id = client_id
        self._client_secret = client_secret
        self._timeout = httpx.Timeout(timeout_seconds)
        # transport 仅测试注入（httpx.MockTransport）；生产为 None
        self._transport = transport
        # verify_tls=False 仅限隔离联调的自签名证书场景
        self._verify_tls = verify_tls

    @property
    def source_origin(self) -> str:
        """Controlled source namespace for reference bindings, never caller input."""
        parsed = urlsplit(self._base_url)
        try:
            parsed.port
        except ValueError:
            raise FormPlatformError("表单平台来源地址配置无效") from None
        if (parsed.scheme not in {"http", "https"} or not parsed.hostname
                or parsed.username or parsed.password or parsed.query or parsed.fragment
                or "?" in self._base_url or "#" in self._base_url
                or parsed.path not in {"", "/"} or any(ord(c) <= 32 for c in self._base_url)
                or (settings.ENVIRONMENT.lower() == "production" and parsed.scheme != "https")):
            raise FormPlatformError("表单平台来源地址配置无效")
        return f"{parsed.scheme}://{parsed.netloc.lower()}"

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
            verify_tls=settings.FORM_PLATFORM_VERIFY_TLS,
        )

    def _auth_headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self._client_id}.{self._client_secret}"}

    async def _request(self, method: str, path: str,
                       json_body: Optional[Dict[str, Any]] = None,
                       params: Optional[Dict[str, Any]] = None,
                       extra_headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=self._timeout,
                                         transport=self._transport,
                                         verify=self._verify_tls) as client:
                response = await client.request(
                    method, f"{self._base_url}{path}",
                    json=json_body, params=params, headers={**self._auth_headers(), **(extra_headers or {})},
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
            body = None
            try:
                parsed = response.json()
            except ValueError:
                parsed = None
            if isinstance(parsed, dict):
                body = parsed
            code = body.get("code") if body and isinstance(body.get("code"), str) else None
            details = body.get("details") if body and isinstance(body.get("details"), dict) else None
            message = (body.get("message")
                       if body and isinstance(body.get("message"), str) else None) \
                or "表单平台请求被拒绝"
            raise FormPlatformError(message, status_code=response.status_code,
                                    remote_code=code, details=details)

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

    async def create_fill_session(self, payload: Dict[str, Any], *, source_access_token: str,
                                  idempotency_key: Optional[str] = None) -> Dict[str, Any]:
        """创建填报会话；idempotency_key 对齐源端 T36（1-128 字符，可选但统一携带）。

        同键同体重试（超时/断连后）返回同一会话并以 Idempotency-Replayed: true
        标记；键与请求体指纹绑定，重试不得改动 payload。
        """
        headers = {"X-Source-Access-Token": source_access_token}
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        return await self._request("POST", "/integration/v1/fill-sessions", payload,
                                   extra_headers=headers)

    async def get_fill_session_by_task_ref(self, ma_task_ref: str) -> Dict[str, Any]:
        """T36 对账端点：按 (client, ma_task_ref) 找回本客户端的填报会话。

        404 session_not_found 表示该引用下尚无会话（如创建请求在远端处理前
        即超时），由调用方决定后续处理。
        """
        return await self._request(
            "GET", f"/integration/v1/fill-sessions/by-task-ref/{quote(ma_task_ref, safe='')}")

    async def launch_fill_session(self, session_uuid: str, *, source_access_token: str) -> Dict[str, Any]:
        return await self._request(
            "POST", f"/integration/v1/fill-sessions/{session_uuid}/launch",
            extra_headers={"X-Source-Access-Token": source_access_token},
        )

    async def get_fill_session(self, session_uuid: str) -> Dict[str, Any]:
        return await self._request("GET", f"/integration/v1/fill-sessions/{session_uuid}")

    async def cancel_fill_session(self, session_uuid: str) -> Dict[str, Any]:
        return await self._request("POST", f"/integration/v1/fill-sessions/{session_uuid}/cancel")

    async def create_patient_self_fill_session(self, payload: Dict[str, Any], *,
                                               idempotency_key: str) -> Dict[str, Any]:
        """Create/recover a source-side patient-owned session; no clinician token is sent."""
        return await self._request("POST", "/integration/v1/patient-self-fill-sessions", payload,
                                   extra_headers={"Idempotency-Key": idempotency_key})

    async def get_patient_self_fill_session(self, session_id: str) -> Dict[str, Any]:
        if not isinstance(session_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", session_id):
            raise FormPlatformError("患者本人填报会话标识无效", status_code=422)
        return await self._request("GET", f"/integration/v1/patient-self-fill-sessions/{session_id}")

    async def get_patient_self_fill_response(self, session_id: str) -> Dict[str, Any]:
        """Read the submitted answer snapshot through its patient-owned session."""
        if not isinstance(session_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", session_id):
            raise FormPlatformError("患者本人填报会话标识无效", status_code=422)
        return await self._request(
            "GET", f"/integration/v1/patient-self-fill-sessions/{session_id}/response")

    async def resume_patient_self_fill_session(self, session_id: str, payload: Dict[str, Any], *,
                                               idempotency_key: str) -> Dict[str, Any]:
        """Rotate the one-use launch proof for an existing still-active patient draft."""
        if not isinstance(session_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", session_id):
            raise FormPlatformError("患者本人填报会话标识无效", status_code=422)
        if not isinstance(idempotency_key, str) or not 1 <= len(idempotency_key) <= 128:
            raise FormPlatformError("患者本人恢复请求缺少幂等键", status_code=422)
        return await self._request("POST", f"/integration/v1/patient-self-fill-sessions/{session_id}/resume", payload,
                                   extra_headers={"Idempotency-Key": idempotency_key})

    async def revoke_patient_self_fill_session(self, session_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(session_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", session_id):
            raise FormPlatformError("患者本人填报会话标识无效", status_code=422)
        return await self._request("POST", f"/integration/v1/patient-self-fill-sessions/{session_id}/revoke", payload)

    async def get_response(self, response_id: int) -> Dict[str, Any]:
        return await self._request("GET", f"/integration/v1/responses/{response_id}")

    async def list_projects(self, *, limit: int = 50, cursor: Optional[str] = None) -> Dict[str, Any]:
        return await self._request("GET", "/integration/v1/projects",
                                   params=self._catalog_params(limit, cursor))

    async def list_centers(self, project_id: int, *, limit: int = 50,
                           cursor: Optional[str] = None) -> Dict[str, Any]:
        return await self._request("GET", f"/integration/v1/projects/{project_id}/centers",
                                   params=self._catalog_params(limit, cursor))

    async def list_subjects(self, project_id: int, *, center_id: Optional[int] = None,
                            status: str = "all", limit: int = 50,
                            cursor: Optional[str] = None) -> Dict[str, Any]:
        params = dict(self._catalog_params(limit, cursor), status=status)
        if center_id is not None:
            params["center_id"] = center_id
        return await self._request("GET", f"/integration/v1/projects/{project_id}/subjects", params=params)

    async def list_people(self, project_id: int, *, limit: int = 50,
                          cursor: Optional[str] = None) -> Dict[str, Any]:
        return await self._request("GET", f"/integration/v1/projects/{project_id}/people",
                                   params=self._catalog_params(limit, cursor))

    async def list_forms(self, project_id: int, *, status: str = "active", limit: int = 50,
                         cursor: Optional[str] = None) -> Dict[str, Any]:
        return await self._request("GET", f"/integration/v1/projects/{project_id}/forms",
                                   params=dict(self._catalog_params(limit, cursor), status=status))

    async def get_patient_reference(self, project_id: int, center_id: int,
                                    subject_id: int) -> Dict[str, Any]:
        return await self._request("GET", f"/integration/v1/projects/{project_id}/centers/{center_id}"
                                   f"/subjects/{subject_id}/patient-reference")

    async def get_form_definition(self, form_id: int, *, version: Optional[int] = None) -> Dict[str, Any]:
        return await self._request("GET", f"/integration/v1/forms/{form_id}/definition",
                                   params={"version": version} if version is not None else None)

    async def create_share_request(self, body: Dict[str, Any]) -> Dict[str, Any]:
        return await self._request("POST", "/integration/v1/share-requests", json_body=body)

    async def get_share_request(self, share_id: int) -> Dict[str, Any]:
        return await self._request("GET", f"/integration/v1/share-requests/{share_id}")

    async def withdraw_share_request(self, share_id: int) -> Dict[str, Any]:
        return await self._request("POST", f"/integration/v1/share-requests/{share_id}/withdraw")

    @staticmethod
    def _catalog_params(limit: int, cursor: Optional[str]) -> Dict[str, Any]:
        return {"limit": limit, **({"cursor": cursor} if cursor is not None else {})}

"""服务凭证核心实现：哈希存储、生命周期、scope 默认拒绝与审计。

存储约定（MongoDB 集合 `service_credentials`，以 client_id 为 _id）：
- `secret_hash` / `previous_secret_hash`：PBKDF2-SHA256 加盐哈希，算法前缀随
  哈希串（`pbkdf2_sha256$<iterations>$<salt_hex>$<hash_hex>`），明文永不落库。
- 轮换双活：轮换保留上一凭证哈希与 `secret_rotated_at`，旧凭证在配置窗口
  （默认 24h）内仍可验证，窗口过后仅新凭证有效。
- 授权（scope）为显式清单：`projects` / `centers` / `actions`，判定默认拒绝。

边界（如实标注）：
- 吊销只作用于本地集合；跨平台撤权属 AUTH04，未实现，本模块不通知外部系统。
- 凭证验证结果只描述客户端，不携带用户身份：服务凭证不能代替真实操作人。
- 限流仅持久化预留字段，执行逻辑未实现。
"""
import hashlib
import hmac
import logging
import re
import secrets
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, Optional, Tuple

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.permission_audit import redact_sensitive_details
from app.schemas.audit_log import AuditLogCreate
from app.services.audit_log_service import AuditLogService

from .config import (
    MAX_PBKDF2_ITERATIONS,
    MIN_PBKDF2_ITERATIONS,
    service_credential_settings,
)

logger = logging.getLogger(__name__)

# 哈希串算法前缀：随哈希串存储，便于未来升级算法（新前缀新逻辑）。
HASH_PREFIX = "pbkdf2_sha256"

# client_id 是稳定的机器身份标识：小写字母/数字开头，允许中划线与下划线。
CLIENT_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{2,63}$")

STATUS_ACTIVE = "active"
STATUS_REVOKED = "revoked"

# scope 的三个维度；scope 以外的键会被拒绝写入，防止调用方夹带自定义语义。
SCOPE_DIMENSIONS = ("projects", "centers", "actions")


class CredentialError(Exception):
    """服务凭证操作的受控失败；对外不携带敏感细节。"""


class CredentialAlreadyExists(CredentialError):
    pass


def hash_secret(secret: str, *, iterations: Optional[int] = None) -> str:
    """PBKDF2-SHA256 加盐哈希；算法与参数随哈希串保存（对齐 113.44 e44a10f）。"""
    rounds = iterations or service_credential_settings.pbkdf2_iterations
    salt = secrets.token_bytes(16)
    derived = hashlib.pbkdf2_hmac("sha256", secret.encode("utf-8"), salt, rounds)
    return f"{HASH_PREFIX}${rounds}${salt.hex()}${derived.hex()}"


def verify_secret(secret: str, stored: str) -> bool:
    """按哈希串携带的算法与参数校验；无法识别的格式一律拒绝，不做弱回退。"""
    if not isinstance(secret, str) or not isinstance(stored, str):
        return False
    try:
        prefix, rounds_text, salt_hex, hash_hex = stored.split("$")
    except ValueError:
        return False
    if prefix != HASH_PREFIX or not rounds_text.isdigit():
        return False
    rounds = int(rounds_text)
    # 集合内容被视为不可信：迭代次数必须在允许范围内，否则拒绝。
    if not MIN_PBKDF2_ITERATIONS <= rounds <= MAX_PBKDF2_ITERATIONS:
        return False
    try:
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
    except ValueError:
        return False
    derived = hashlib.pbkdf2_hmac("sha256", secret.encode("utf-8"), salt, rounds)
    return hmac.compare_digest(derived.hex(), hash_hex)


def generate_secret() -> str:
    """生成凭证明文；仅在创建/轮换响应中出现一次。"""
    return secrets.token_urlsafe(32)


def normalize_scopes(scopes: Optional[Dict[str, Iterable[str]]]) -> Dict[str, list]:
    """规整 scope：去重、排序，只接受已知维度；未知键直接拒绝（默认拒绝原则）。"""
    normalized: Dict[str, list] = {}
    if scopes:
        for key, values in scopes.items():
            if key not in SCOPE_DIMENSIONS:
                raise CredentialError(f"unknown scope dimension: {key}")
            cleaned = sorted({str(value) for value in values or () if str(value).strip()})
            normalized[key] = cleaned
    return {dimension: normalized.get(dimension, []) for dimension in SCOPE_DIMENSIONS}


def is_scope_allowed(
    scopes: Dict[str, Iterable[str]],
    *,
    project_id: Optional[str],
    center_id: Optional[str],
    action: Optional[str],
) -> bool:
    """最小授权判定：默认拒绝。

    任一维度（项目 / 中心 / 动作）缺失、对应清单为空、或值不在显式授权清单内，
    一律拒绝。与统一身份契约 §6 的默认拒绝语义一致：不允许"空清单=不限"，
    也不允许只凭 client_id 通过任何跨项目/跨中心的校验。
    """
    normalized = normalize_scopes(scopes)
    if not project_id or not center_id or not action:
        return False
    for dimension, value in (
        ("projects", str(project_id)),
        ("centers", str(center_id)),
        ("actions", str(action)),
    ):
        allowed = normalized[dimension]
        if not allowed or value not in allowed:
            return False
    return True


def client_view(record: Dict[str, Any]) -> Dict[str, Any]:
    """凭证验证成功后对外可见的最小视图。

    刻意不包含任何用户/操作人字段：服务凭证只能代表受限客户端，
    不能代替真实操作人；调用方不得据此构造 user_id。
    """
    return {
        "client_id": record["_id"],
        "scopes": normalize_scopes(record.get("scopes") or {}),
        "status": record.get("status"),
        "expires_at": record.get("expires_at"),
        # 显式标记主体类型，防止调用方把机器身份当成自然人。
        "principal_type": "client",
        "represents_operator": False,
        # 限流预留位：仅回显持久化配置，当前没有执行逻辑。
        "rate_limit_per_minute": record.get("rate_limit_per_minute"),
    }


class ServiceCredentialService:
    """服务凭证生命周期与授权判定；审计写入失败不影响判定结果。"""

    COLLECTION = "service_credentials"

    def __init__(
        self,
        db: AsyncIOMotorDatabase,
        *,
        audit_service: Optional[AuditLogService] = None,
        settings=service_credential_settings,
    ):
        self.db = db
        self.collection = db[self.COLLECTION]
        self.audit_service = audit_service
        self.settings = settings

    async def ensure_indexes(self):
        # client_id 即 _id（天然唯一）；过期时间建索引供后续清理任务使用。
        await self.collection.create_index("expires_at", name="expires_at_lookup")

    # ------------------------------------------------------------------ 审计

    async def _audit(
        self,
        event: str,
        *,
        client_id: str,
        outcome: str,
        actor_id: Optional[str],
        extra: Optional[Dict[str, Any]] = None,
        status: str = "success",
    ):
        """写入操作审计。

        details 只由固定键构造并经 redact_sensitive_details 二次脱敏：
        绝不写入凭证明文、哈希、盐或完整敏感答卷内容。
        actor_id 是发起生命周期操作的真实操作人；验证类事件没有自然人主体，
        以 `client:<client_id>` 记入 details，不伪造 user_id。
        """
        if self.audit_service is None:
            return
        details = {"event": event, "outcome": outcome, "client_id": client_id}
        if actor_id:
            details["actor_id"] = actor_id
        else:
            details["subject"] = f"client:{client_id}"
        if extra:
            details.update(extra)
        try:
            await self.audit_service.create_log(
                log_data=AuditLogCreate(
                    user_id=actor_id or "anonymous",
                    action=event,
                    resource_type="service_credential",
                    resource_id=client_id,
                    status=status,
                    details=redact_sensitive_details(details),
                ),
            )
        except Exception:  # noqa: BLE001 - 审计失败不阻断业务结果，与既有写点一致
            logger.error("service credential audit write failed for %s/%s", event, client_id)

    # -------------------------------------------------------------- 生命周期

    async def create_credential(
        self,
        *,
        client_id: str,
        scopes: Dict[str, Iterable[str]],
        expires_at: Optional[datetime] = None,
        actor_id: Optional[str] = None,
        rate_limit_per_minute: Optional[int] = None,
    ) -> Tuple[Dict[str, Any], str]:
        """创建凭证：返回 (存储文档视图, 明文 secret)。明文只在本次响应出现。"""
        if not CLIENT_ID_PATTERN.match(client_id or ""):
            raise CredentialError("invalid client_id")
        normalized_scopes = normalize_scopes(scopes)
        if expires_at is not None and expires_at <= datetime.utcnow():
            raise CredentialError("expires_at must be in the future")
        if rate_limit_per_minute is not None and rate_limit_per_minute <= 0:
            raise CredentialError("rate_limit_per_minute must be positive")
        secret = generate_secret()
        document = {
            "_id": client_id,
            "secret_hash": hash_secret(secret, iterations=self.settings.pbkdf2_iterations),
            "previous_secret_hash": None,
            "secret_rotated_at": None,
            "scopes": normalized_scopes,
            "status": STATUS_ACTIVE,
            "expires_at": expires_at,
            # 限流预留位：只持久化，不执行。
            "rate_limit_per_minute": (
                rate_limit_per_minute
                if rate_limit_per_minute is not None
                else self.settings.rate_limit_per_minute
            ),
            "created_by": actor_id or "anonymous",
            "created_at": datetime.utcnow(),
            "revoked_at": None,
            "revoked_by": None,
            "last_used_at": None,
        }
        try:
            await self.collection.insert_one(document.copy())
        except Exception as exc:  # pymongo DuplicateKeyError 等
            raise CredentialAlreadyExists(client_id) from exc
        await self._audit("create", client_id=client_id, outcome="created", actor_id=actor_id,
                          extra={"expires_at": expires_at.isoformat() + "Z" if expires_at else None})
        return client_view(document), secret

    async def verify(self, client_id: str, secret: str) -> Optional[Dict[str, Any]]:
        """验证客户端凭证；成功返回最小客户端视图，失败返回 None 并记审计。

        判定顺序：存在 → 未吊销 → 未过期 → 哈希匹配（当前哈希优先，
        其次双活窗口内的上一凭证哈希）。任一步失败即拒绝，默认拒绝。
        """
        record = await self.collection.find_one({"_id": client_id})
        if record is None:
            await self._audit("verify", client_id=client_id, outcome="unknown_client",
                              actor_id=None, status="failure")
            return None
        if record.get("status") != STATUS_ACTIVE:
            await self._audit("verify", client_id=client_id, outcome="revoked",
                              actor_id=None, status="failure")
            return None
        expires_at = record.get("expires_at")
        if expires_at is not None and expires_at <= datetime.utcnow():
            await self._audit("verify", client_id=client_id, outcome="expired",
                              actor_id=None, status="failure")
            return None
        if not isinstance(secret, str) or not secret:
            await self._audit("verify", client_id=client_id, outcome="missing_secret",
                              actor_id=None, status="failure")
            return None
        if verify_secret(secret, record.get("secret_hash") or ""):
            await self.collection.update_one(
                {"_id": client_id}, {"$set": {"last_used_at": datetime.utcnow()}})
            return client_view(record)
        # 轮换双活：旧凭证在窗口内仍可验证；窗口外旧凭证立即失效。
        previous_hash = record.get("previous_secret_hash")
        rotated_at = record.get("secret_rotated_at")
        overlap = self.settings.rotation_overlap_seconds
        if (previous_hash and rotated_at is not None and overlap >= 0
                and datetime.utcnow() < rotated_at + timedelta(seconds=overlap)
                and verify_secret(secret, previous_hash)):
            return client_view(record)
        await self._audit("verify", client_id=client_id, outcome="invalid_secret",
                          actor_id=None, status="failure")
        return None

    async def rotate(self, client_id: str, *, actor_id: Optional[str] = None) -> Tuple[Dict[str, Any], str]:
        """轮换凭证：新 secret 生效，旧 secret 在双活窗口内仍可验证。

        双活窗口默认 24h（对齐 113.44 试点参数），由配置覆盖。
        只对本地记录生效；不产生任何跨平台通知（AUTH04 未实现）。
        """
        record = await self.collection.find_one({"_id": client_id, "status": STATUS_ACTIVE})
        if record is None:
            raise CredentialError("credential not found or not active")
        old_hash = record.get("secret_hash")
        secret = generate_secret()
        # 单次原子更新完成轮换：旧哈希晋升为 previous_secret_hash（双活窗口内
        # 仍可验证），并以旧哈希作并发条件，避免两个并发轮换互相覆盖。
        rotated_at = datetime.utcnow()
        new_hash = hash_secret(secret, iterations=self.settings.pbkdf2_iterations)
        result = await self.collection.update_one(
            {"_id": client_id, "secret_hash": old_hash},
            {"$set": {
                "secret_hash": new_hash,
                "previous_secret_hash": old_hash,
                "secret_rotated_at": rotated_at,
            }})
        if result.matched_count != 1:
            raise CredentialError("credential changed concurrently; retry rotation")
        await self._audit("rotate", client_id=client_id, outcome="rotated", actor_id=actor_id)
        return client_view({**record, "secret_hash": None, "secret_rotated_at": rotated_at}), secret

    async def revoke(self, client_id: str, *, actor_id: Optional[str] = None, reason: Optional[str] = None) -> bool:
        """吊销凭证（幂等）。

        边界：只覆盖本地；跨平台撤权（AUTH04）未实现，本方法不向 113.44
        或其他平台传播失效，不能据此宣称跨平台撤权能力。
        """
        result = await self.collection.find_one_and_update(
            {"_id": client_id, "status": STATUS_ACTIVE},
            {"$set": {
                "status": STATUS_REVOKED,
                "revoked_at": datetime.utcnow(),
                "revoked_by": actor_id or "anonymous",
                # 吊销即终止双活：清空上一凭证哈希，旧凭证立即失效。
                "previous_secret_hash": None,
                "secret_rotated_at": None,
            }},
        )
        if result is None:
            # 已吊销或不存在：幂等返回 False，不泄露具体原因差异。
            await self._audit("revoke", client_id=client_id, outcome="not_active",
                              actor_id=actor_id, status="failure")
            return False
        await self._audit("revoke", client_id=client_id, outcome="revoked",
                          actor_id=actor_id, extra={"reason": reason})
        return True

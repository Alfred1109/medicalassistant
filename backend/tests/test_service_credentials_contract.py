"""AUTH02 服务凭证契约测试：哈希存储、生命周期、scope 默认拒绝与审计脱敏。

真实数据库测试需要显式的隔离副本集 URI（见 deploy/mongodb/README.md）：

    cd backend
    DEBUG=false REHAB_TEST_CREDENTIALS_MONGO_URI='mongodb://127.0.0.1:37021/?replicaSet=rehab_rs&directConnection=true' \
        .venv/bin/python -m pytest tests/test_service_credentials_contract.py -q

每个数据库用例新建并删除 rehab_creds_test_ 前缀的独立库，不指向业务实例。
"""
import os
import unittest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient

from app.core.permission_audit import redact_sensitive_details
from app.core.permission_audit import ResourcePermissionTracker
from app.integrations.credentials.config import ServiceCredentialSettings
from app.integrations.credentials.service import (
    CredentialAlreadyExists,
    CredentialError,
    ServiceCredentialService,
    generate_secret,
    hash_secret,
    is_scope_allowed,
    normalize_scopes,
    verify_secret,
)
from app.services.audit_log_service import AuditLogService


URI = os.environ.get("REHAB_TEST_CREDENTIALS_MONGO_URI")

SECRET_PLAINTEXT = "plaintext-never-store"
FULL_ANSWER = "答卷全文：" + "患者主诉与量表作答" * 64


class SecretHashingTests(unittest.TestCase):
    """凭证只存哈希：PBKDF2 加盐、算法前缀随哈希串、无法识别格式拒绝。"""

    def test_hash_carries_algorithm_prefix_and_salted_params(self):
        stored = hash_secret(SECRET_PLAINTEXT, iterations=600_000)
        prefix, rounds, salt_hex, hash_hex = stored.split("$")
        self.assertEqual(prefix, "pbkdf2_sha256")
        self.assertEqual(rounds, "600000")
        self.assertEqual(len(salt_hex), 32)  # 16 字节盐
        self.assertEqual(len(hash_hex), 64)  # sha256 摘要

    def test_same_secret_produces_distinct_hashes(self):
        first = hash_secret(SECRET_PLAINTEXT, iterations=600_000)
        second = hash_secret(SECRET_PLAINTEXT, iterations=600_000)
        self.assertNotEqual(first, second)
        self.assertTrue(verify_secret(SECRET_PLAINTEXT, first))
        self.assertTrue(verify_secret(SECRET_PLAINTEXT, second))

    def test_wrong_secret_and_tampered_hash_fail(self):
        stored = hash_secret(SECRET_PLAINTEXT, iterations=600_000)
        self.assertFalse(verify_secret("wrong-secret", stored))
        prefix, rounds, salt_hex, hash_hex = stored.split("$")
        tampered = "$".join([prefix, rounds, salt_hex, "0" * 64])
        self.assertFalse(verify_secret(SECRET_PLAINTEXT, tampered))

    def test_unrecognized_or_out_of_range_formats_are_rejected(self):
        self.assertFalse(verify_secret(SECRET_PLAINTEXT, ""))
        self.assertFalse(verify_secret(SECRET_PLAINTEXT, "sha256$deadbeef"))
        self.assertFalse(verify_secret(
            SECRET_PLAINTEXT,
            # 已知前缀但迭代次数超出允许范围：视为不可信集合内容。
            hash_secret(SECRET_PLAINTEXT, iterations=600_000).replace("$600000$", "$10$")))

    def test_plaintext_and_generated_secret_are_not_recoverable_from_hash(self):
        secret = generate_secret()
        stored = hash_secret(secret, iterations=600_000)
        self.assertNotIn(secret, stored)
        self.assertNotIn(secret.encode().hex(), stored)


class ServiceCredentialSettingsTests(unittest.TestCase):
    """轮换窗口与哈希参数：默认对齐 113.44 e44a10f 惯例，异常配置拒绝。"""

    def test_defaults_align_with_pilot_convention(self):
        config = ServiceCredentialSettings(_env_file=None)
        self.assertEqual(config.rotation_overlap_seconds, 24 * 3600)
        self.assertEqual(config.pbkdf2_iterations, 600_000)
        self.assertIsNone(config.rate_limit_per_minute)  # 限流仅预留位

    def test_out_of_range_values_are_rejected(self):
        for field, value in (
            ("rotation_overlap_seconds", -1),
            ("rotation_overlap_seconds", 8 * 24 * 3600),
            ("pbkdf2_iterations", 1000),
            ("rate_limit_per_minute", 0),
        ):
            with self.assertRaises(ValueError):
                ServiceCredentialSettings(_env_file=None, **{field: value})


class ScopeDefaultDenyTests(unittest.TestCase):
    """最小授权：scope 默认拒绝；任一维度缺失或不在清单内即拒绝。"""

    def test_empty_or_missing_scopes_deny_everything(self):
        for scopes in (None, {}, {"projects": ["p1"], "centers": [], "actions": ["a1"]}):
            with self.subTest(scopes=scopes):
                self.assertFalse(is_scope_allowed(
                    scopes, project_id="p1", center_id="c1", action="a1"))

    def test_unlisted_project_center_or_action_is_denied(self):
        scopes = {"projects": ["p1"], "centers": ["c1"], "actions": ["forms.read"]}
        self.assertFalse(is_scope_allowed(scopes, project_id="p2", center_id="c1", action="forms.read"))
        self.assertFalse(is_scope_allowed(scopes, project_id="p1", center_id="c2", action="forms.read"))
        self.assertFalse(is_scope_allowed(scopes, project_id="p1", center_id="c1", action="forms.export"))

    def test_missing_dimension_argument_is_denied(self):
        scopes = {"projects": ["p1"], "centers": ["c1"], "actions": ["forms.read"]}
        self.assertFalse(is_scope_allowed(scopes, project_id=None, center_id="c1", action="forms.read"))
        self.assertFalse(is_scope_allowed(scopes, project_id="p1", center_id=None, action="forms.read"))
        self.assertFalse(is_scope_allowed(scopes, project_id="p1", center_id="c1", action=None))

    def test_exact_match_within_all_dimensions_is_allowed(self):
        scopes = {"projects": ["p1", "p3"], "centers": ["c1"], "actions": ["forms.read"]}
        self.assertTrue(is_scope_allowed(scopes, project_id="p1", center_id="c1", action="forms.read"))

    def test_unknown_scope_dimension_is_rejected(self):
        with self.assertRaises(CredentialError):
            normalize_scopes({"projects": ["p1"], "everything": ["*"]})


class AuditRedactionTests(unittest.TestCase):
    """审计脱敏：凭证明文/哈希与完整敏感答卷内容不得进入审计记录。"""

    def test_credential_like_keys_are_removed_entirely(self):
        details = {
            "client_secret": SECRET_PLAINTEXT,
            "secret_hash": "$pbkdf2_sha256$600000$aa$bb",
            "access_token": "bearer-value",
            "x_api_key": "key-value",
            "authorization": "Basic abc",
            "credentials_file": "/tmp/creds",
            "client_id": "form-backend",  # 非敏感标识应保留
            "outcome": "revoked",
        }
        redacted = redact_sensitive_details(details)
        for key in ("client_secret", "secret_hash", "access_token", "x_api_key",
                    "authorization", "credentials_file"):
            self.assertNotIn(key, redacted)
        self.assertEqual(redacted["client_id"], "form-backend")
        self.assertEqual(redacted["outcome"], "revoked")

    def test_full_sensitive_answer_content_keys_are_removed(self):
        details = {
            "answer": FULL_ANSWER,
            "response": FULL_ANSWER,
            "questionnaire_data": {"q1": FULL_ANSWER},
            "raw_text": FULL_ANSWER,
            "results_count": 1,  # 统计类字段不受影响
        }
        redacted = redact_sensitive_details(details)
        self.assertEqual(redacted, {"results_count": 1})

    def test_partial_masking_is_never_applied(self):
        # 整键移除而非掩码：掩码会泄露长度等元信息。
        redacted = redact_sensitive_details({"client_secret": SECRET_PLAINTEXT})
        self.assertEqual(redacted, {})
        self.assertNotIn("***", str(redacted))

    def test_none_and_empty_details_are_safe(self):
        self.assertEqual(redact_sensitive_details(None), {})
        self.assertEqual(redact_sensitive_details({}), {})


class TrackerRedactionTests(unittest.IsolatedAsyncioTestCase):
    """ResourcePermissionTracker 的 details 来自调用方，写入前必须脱敏。"""

    async def test_track_resource_access_redacts_details(self):
        captured = []

        async def capture_insert_one(document):
            captured.append(document)
            return MagicMock(inserted_id=ObjectId())

        mock_db = MagicMock()
        mock_db.audit_logs.insert_one = AsyncMock(side_effect=capture_insert_one)
        tracker = ResourcePermissionTracker(mock_db)
        await tracker.track_resource_access(
            user_id="operator", resource_type="service_credential",
            resource_id="form-backend", action="create",
            details={"client_secret": SECRET_PLAINTEXT, "answer": FULL_ANSWER,
                     "event": "create"})
        self.assertEqual(len(captured), 1)
        details = captured[0]["details"]
        self.assertNotIn("client_secret", details)
        self.assertNotIn("answer", details)
        self.assertNotIn(SECRET_PLAINTEXT, str(details))
        self.assertNotIn("患者主诉与量表作答", str(details))
        self.assertEqual(details["event"], "create")


@unittest.skipUnless(URI, "set isolated local REHAB_TEST_CREDENTIALS_MONGO_URI")
class ServiceCredentialLifecycleTests(unittest.IsolatedAsyncioTestCase):
    """真实副本集上的生命周期：创建/验证/过期/吊销/轮换窗口与审计落库。"""

    async def asyncSetUp(self):
        self.assertTrue(URI.startswith(("mongodb://127.0.0.1:", "mongodb://localhost:")))
        self.mongo = AsyncIOMotorClient(URI, serverSelectionTimeoutMS=3000)
        self.db = self.mongo["rehab_creds_test_" + uuid4().hex]
        self.audit_captured = []

        async def capture_insert_one(document):
            self.audit_captured.append(document)
            return MagicMock(inserted_id=ObjectId())

        audit_db = MagicMock()
        audit_db.audit_logs.insert_one = AsyncMock(side_effect=capture_insert_one)
        self.service = ServiceCredentialService(self.db, audit_service=AuditLogService(audit_db))
        await self.service.ensure_indexes()

    async def asyncTearDown(self):
        await self.mongo.drop_database(self.db.name)
        self.mongo.close()

    async def create(self, client_id="form-backend", **kwargs):
        scopes = kwargs.pop("scopes", {"projects": ["p1"], "centers": ["c1"],
                                       "actions": ["forms.read"]})
        return await self.service.create_credential(
            client_id=client_id, scopes=scopes, actor_id="admin-1", **kwargs)

    async def test_create_returns_secret_once_and_stores_only_hash(self):
        view, secret = await self.create()
        stored = await self.db.service_credentials.find_one({"_id": "form-backend"})
        self.assertTrue(verify_secret(secret, stored["secret_hash"]))
        # 明文与哈希不落库：文档任何位置都不出现明文 secret。
        self.assertNotIn(secret, str(stored))
        self.assertTrue(stored["secret_hash"].startswith("pbkdf2_sha256$"))
        self.assertEqual(stored["status"], "active")
        self.assertEqual(stored["created_by"], "admin-1")
        # 客户端视图只描述机器身份，不含任何用户身份字段。
        self.assertEqual(view["principal_type"], "client")
        self.assertFalse(view["represents_operator"])
        for forbidden in ("user_id", "actor_id", "operator", "secret", "secret_hash"):
            self.assertNotIn(forbidden, view)
        # 创建事件落审计，且审计内容不含明文。
        create_logs = [log for log in self.audit_captured if log["action"] == "create"]
        self.assertEqual(len(create_logs), 1)
        self.assertNotIn(secret, str(create_logs[0]))
        self.assertEqual(create_logs[0]["resource_type"], "service_credential")

    async def test_duplicate_client_id_is_rejected(self):
        await self.create()
        with self.assertRaises(CredentialAlreadyExists):
            await self.create()

    async def test_create_rejects_past_expiry(self):
        with self.assertRaises(CredentialError):
            await self.create(expires_at=datetime.utcnow() - timedelta(seconds=1))

    async def test_verify_success_failure_and_last_used(self):
        _, secret = await self.create()
        view = await self.service.verify("form-backend", secret)
        self.assertEqual(view["client_id"], "form-backend")
        self.assertIsNone(await self.service.verify("form-backend", "wrong"))
        self.assertIsNone(await self.service.verify("unknown-client", secret))
        stored = await self.db.service_credentials.find_one({"_id": "form-backend"})
        self.assertIsNotNone(stored["last_used_at"])

    async def test_expired_credential_is_denied(self):
        await self.create()
        # 创建接口拒绝过去的到期时间；过期语义通过把已建凭证到期时间回拨验证。
        await self.db.service_credentials.update_one(
            {"_id": "form-backend"},
            {"$set": {"expires_at": datetime.utcnow() - timedelta(seconds=1)}})
        _, secret = await self.create(client_id="fresh-client")
        self.assertIsNone(await self.service.verify("form-backend", secret))
        expired_logs = [log for log in self.audit_captured if log["details"].get("outcome") == "expired"]
        self.assertTrue(expired_logs)

    async def test_revoked_credential_is_denied_and_old_secret_cannot_survive(self):
        _, secret = await self.create()
        self.assertTrue(await self.service.revoke("form-backend", actor_id="admin-2", reason="offboarded"))
        self.assertIsNone(await self.service.verify("form-backend", secret))
        stored = await self.db.service_credentials.find_one({"_id": "form-backend"})
        self.assertEqual(stored["status"], "revoked")
        self.assertEqual(stored["revoked_by"], "admin-2")
        # 幂等：重复吊销返回 False 且状态不变。
        self.assertFalse(await self.service.revoke("form-backend", actor_id="admin-2"))
        revoked_logs = [log for log in self.audit_captured
                        if log["action"] == "revoke" and log["details"].get("outcome") == "revoked"]
        self.assertEqual(len(revoked_logs), 1)

    async def test_rotation_dual_alive_window(self):
        _, old_secret = await self.create()
        _, new_secret = await self.service.rotate("form-backend", actor_id="admin-1")
        # 双活窗口内（默认 24h）：新旧凭证都可验证。
        self.assertIsNotNone(await self.service.verify("form-backend", old_secret))
        self.assertIsNotNone(await self.service.verify("form-backend", new_secret))
        stored = await self.db.service_credentials.find_one({"_id": "form-backend"})
        self.assertTrue(verify_secret(old_secret, stored["previous_secret_hash"]))
        self.assertTrue(verify_secret(new_secret, stored["secret_hash"]))
        # 轮换窗口过期后（把 rotated_at 回拨超过窗口）：旧凭证失效。
        overlap = self.service.settings.rotation_overlap_seconds
        await self.db.service_credentials.update_one(
            {"_id": "form-backend"},
            {"$set": {"secret_rotated_at": datetime.utcnow() - timedelta(seconds=overlap + 1)}})
        self.assertIsNone(await self.service.verify("form-backend", old_secret))
        self.assertIsNotNone(await self.service.verify("form-backend", new_secret))

    async def test_rotation_with_zero_overlap_retires_old_secret_immediately(self):
        self.service.settings = ServiceCredentialSettings(_env_file=None, rotation_overlap_seconds=0)
        _, old_secret = await self.create()
        _, new_secret = await self.service.rotate("form-backend")
        self.assertIsNone(await self.service.verify("form-backend", old_secret))
        self.assertIsNotNone(await self.service.verify("form-backend", new_secret))

    async def test_scope_is_enforced_on_the_stored_credential(self):
        view, _ = await self.create(
            scopes={"projects": ["p1"], "centers": ["c1"], "actions": ["forms.read"]})
        self.assertTrue(is_scope_allowed(
            view["scopes"], project_id="p1", center_id="c1", action="forms.read"))
        # 跨项目 / 跨中心 / 未授权动作一律拒绝（默认拒绝内核与契约 §6 一致）。
        self.assertFalse(is_scope_allowed(
            view["scopes"], project_id="p2", center_id="c1", action="forms.read"))
        self.assertFalse(is_scope_allowed(
            view["scopes"], project_id="p1", center_id="c9", action="forms.read"))
        self.assertFalse(is_scope_allowed(
            view["scopes"], project_id="p1", center_id="c1", action="care.export"))

    async def test_lifecycle_audits_never_contain_secret_or_hash(self):
        _, secret = await self.create()
        await self.service.verify("form-backend", "wrong-secret")
        await self.service.rotate("form-backend", actor_id="admin-1")
        await self.service.revoke("form-backend", actor_id="admin-1")
        self.assertTrue(self.audit_captured)
        for log in self.audit_captured:
            self.assertNotIn(secret, str(log))
            self.assertNotIn("pbkdf2_sha256$", str(log))
            self.assertNotIn("wrong-secret", str(log))
            # 每条记录都可归因：要么真实操作人，要么显式的客户端主体标记。
            self.assertTrue(log["user_id"] != "anonymous" or "client:" in str(log["details"]))


if __name__ == "__main__":
    unittest.main()

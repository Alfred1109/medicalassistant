"""T64：显式账号绑定管理端点 HTTP 契约测试（内存打桩，不触碰数据库）。

覆盖 app/api/routers/patient_account_binding_router.py 的行为契约：

- 权限：仅 admin（doctor/patient 一律 403，与 system_admin_router 账号管理
  权限形态一致）；
- 创建绑定 201 真实响应形状（patient_id/account_id/status/source/审计）；
- 停用绑定 200（disable 语义走仓储状态机）；
- PatientDomainError → HTTP 映射：409 冲突 / 404 不存在 / 422 校验与凭证 /
  503 域状态不可用，不降级 500、不吞错误；
- schema 校验 422（extra=forbid、account_id 长度、必填 reviewer/evidence）。

仓储行为（互斥/状态机/反向核验）由 test_patient_account_binding.py 的
副本集门控测试覆盖，本文件只验证 HTTP 层契约（patch 仓储方法）。
"""
import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from bson import ObjectId
from fastapi import FastAPI

from app.api.routers.patient_account_binding_router import router as binding_router
from app.core.auth import get_current_active_user
from app.db.mongodb import get_database
from app.patients.repository import ClinicalPatientRepository, PatientDomainError

PATIENT_ID = str(ObjectId())
ACCOUNT_ID = str(ObjectId())
ADMIN_ID = str(ObjectId())
NOW = datetime.now(timezone.utc)

LINK = {"_id": f"explicit:{PATIENT_ID}", "account_id": ACCOUNT_ID,
        "account_document_id": ACCOUNT_ID, "patient_id": PATIENT_ID,
        "source": "explicit_binding", "schema_version": 1, "status": "verified",
        "bound_at": NOW,
        "audit": {"reviewer": "管理员甲", "evidence_reference": "核实凭证-1",
                  "operation": "explicit_binding", "at": NOW}}


def make_user(role="admin", user_id=ADMIN_ID):
    from app.schemas.user import UserResponse
    now = datetime.utcnow()
    return UserResponse(id=user_id, email="actor@example.com", name="合成用户",
                        role=role, is_active=True, createdAt=now, updatedAt=now)


class BindingRouterContractTests(unittest.IsolatedAsyncioTestCase):
    def _setup(self, role="admin"):
        user = make_user(role=role)

        async def fake_current_user():
            return user

        self.app = FastAPI()
        self.app.include_router(binding_router, prefix="/api")
        # 仓储方法已 patch；db 用 MagicMock 仅为让构造器 db[PATIENTS] 可用。
        self.app.dependency_overrides[get_database] = lambda: MagicMock()
        self.app.dependency_overrides[get_current_active_user] = fake_current_user
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app, raise_app_exceptions=False),
            base_url="http://binding-test")
        self.addAsyncCleanup(self.client.aclose)

    def _patch_bind(self, side_effect=None, return_value=LINK):
        return patch.object(ClinicalPatientRepository, "bind_account",
                            new=AsyncMock(return_value=return_value,
                                          side_effect=side_effect))

    def _patch_disable(self, side_effect=None, return_value=LINK):
        return patch.object(ClinicalPatientRepository, "disable_account_link",
                            new=AsyncMock(return_value=return_value,
                                          side_effect=side_effect))

    async def test_create_binding_201_real_shape(self):
        self._setup()
        with self._patch_bind() as mock:
            response = await self.client.post("/api/patients/account-bindings", json={
                "patient_id": PATIENT_ID, "account_id": ACCOUNT_ID,
                "reviewer": "管理员甲", "evidence_reference": "核实凭证-1"})
        self.assertEqual(response.status_code, 201, response.text)
        body = response.json()
        self.assertEqual(body["patient_id"], PATIENT_ID)
        self.assertEqual(body["account_id"], ACCOUNT_ID)
        self.assertEqual(body["status"], "verified")
        self.assertEqual(body["source"], "explicit_binding")
        self.assertEqual(body["reviewer"], "管理员甲")
        self.assertEqual(body["evidence_reference"], "核实凭证-1")
        self.assertIsNotNone(body["bound_at"])
        mock.assert_awaited_once_with(PATIENT_ID, account_id=ACCOUNT_ID,
                                      reviewer="管理员甲",
                                      evidence_reference="核实凭证-1")

    async def test_create_binding_requires_admin(self):
        for role in ("doctor", "health_manager", "patient"):
            with self.subTest(role=role):
                self._setup(role=role)
                with self._patch_bind() as mock:
                    response = await self.client.post("/api/patients/account-bindings",
                                                      json={"patient_id": PATIENT_ID,
                                                            "account_id": ACCOUNT_ID,
                                                            "reviewer": "管理员甲",
                                                            "evidence_reference": "凭证"})
                self.assertEqual(response.status_code, 403, response.text)
                mock.assert_not_awaited()

    async def test_create_binding_error_mapping(self):
        cases = [
            ("PATIENT_ACCOUNT_LINK_CONFLICT", 409),
            ("PATIENT_NOT_FOUND", 404),
            ("PATIENT_ACCOUNT_LINK_NOT_FOUND", 404),
            ("PATIENT_REVIEW_REQUIRED", 422),
            ("INVALID_PATIENT_ACCOUNT", 422),
            ("INVALID_PATIENT_REVIEW_REFERENCE", 422),
            ("PATIENT_DOMAIN_NOT_MIGRATED", 503),
            ("PATIENT_DOMAIN_STATE_UNAVAILABLE", 503),
        ]
        for code, expected in cases:
            with self.subTest(code=code):
                self._setup()
                with self._patch_bind(side_effect=PatientDomainError(code)):
                    response = await self.client.post("/api/patients/account-bindings",
                                                      json={"patient_id": PATIENT_ID,
                                                            "account_id": ACCOUNT_ID,
                                                            "reviewer": "管理员甲",
                                                            "evidence_reference": "凭证"})
                self.assertEqual(response.status_code, expected, response.text)
                self.assertEqual(response.json()["detail"]["error"], code)

    async def test_create_binding_schema_validation_422(self):
        self._setup()
        invalid_bodies = [
            {},  # 缺全部必填
            {"patient_id": PATIENT_ID, "account_id": ACCOUNT_ID,
             "reviewer": "管理员甲"},  # 缺 evidence
            {"patient_id": PATIENT_ID, "account_id": "short-id",
             "reviewer": "管理员甲", "evidence_reference": "凭证"},  # account_id 长度
            {"patient_id": PATIENT_ID, "account_id": ACCOUNT_ID,
             "reviewer": "管理员甲", "evidence_reference": "凭证", "extra": 1},  # extra=forbid
            {"patient_id": "", "account_id": ACCOUNT_ID,
             "reviewer": "管理员甲", "evidence_reference": "凭证"},  # 空 patient_id
        ]
        for body in invalid_bodies:
            with self.subTest(body=body):
                with self._patch_bind() as mock:
                    response = await self.client.post("/api/patients/account-bindings",
                                                      json=body)
                self.assertEqual(response.status_code, 422, response.text)
                mock.assert_not_awaited()

    async def test_disable_binding_200_and_error_mapping(self):
        self._setup()
        disabled = dict(LINK, status="disabled",
                        audit=[LINK["audit"],
                               {"operation": "explicit_binding_disable",
                                "reviewer": "管理员乙",
                                "evidence_reference": "解绑-1", "at": NOW}],
                        disabled_at=NOW)
        with self._patch_disable(return_value=disabled) as mock:
            response = await self.client.post(
                f"/api/patients/account-bindings/{PATIENT_ID}/disable",
                json={"reviewer": "管理员乙", "evidence_reference": "解绑-1"})
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["status"], "disabled")
        self.assertIsNotNone(body["disabled_at"])
        mock.assert_awaited_once_with(PATIENT_ID, reviewer="管理员乙",
                                      evidence_reference="解绑-1")
        # 停用同样要求 admin
        self._setup(role="doctor")
        with self._patch_disable() as mock:
            response = await self.client.post(
                f"/api/patients/account-bindings/{PATIENT_ID}/disable",
                json={"reviewer": "管理员乙", "evidence_reference": "解绑-1"})
        self.assertEqual(response.status_code, 403, response.text)
        mock.assert_not_awaited()
        # 未绑定患者 404
        self._setup()
        with self._patch_disable(side_effect=PatientDomainError("PATIENT_ACCOUNT_LINK_NOT_FOUND")):
            response = await self.client.post(
                f"/api/patients/account-bindings/{PATIENT_ID}/disable",
                json={"reviewer": "管理员乙", "evidence_reference": "解绑-1"})
        self.assertEqual(response.status_code, 404, response.text)

    async def test_disable_binding_schema_validation_422(self):
        self._setup()
        with self._patch_disable() as mock:
            response = await self.client.post(
                f"/api/patients/account-bindings/{PATIENT_ID}/disable", json={
                    "reviewer": "管理员乙", "evidence_reference": "解绑-1", "extra": True})
        self.assertEqual(response.status_code, 422, response.text)
        mock.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()

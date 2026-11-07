"""健康档案路由契约测试（WP0 路由层修复，2026-11-07）。

覆盖三类路由层缺陷修复后的契约：
1. GET /followups、GET /followups/upcoming、GET /health-data 不再被
   GET /{record_id} / GET /followups/{followup_id} 的路径参数遮蔽；
2. GET /{record_id} 对真实形状（24 位十六进制）ID 仍正常；
3. 未认证一律 401；患者越权访问 403，本人/医疗人员正常访问。

服务层（HealthRecordService）全部内存打桩，不触碰真实数据库；
服务层自身的一代/二代字段错位（FU01 范围）不在本测试修复或掩盖。
"""

import unittest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from bson import ObjectId
from jose import jwt

from app.core.config import settings
from app.core.dependencies import get_health_record_service
from app.db.mongodb import get_database
from app.main import app
from app.schemas.followup import (
    FollowUpRecordResponse,
    FollowUpStatus,
)
from app.schemas.health_record import (
    HealthDataResponse,
    HealthRecordResponse,
)
from app.schemas.user import UserResponse
from app.services.user_service import UserService

PATIENT_ID = str(ObjectId())
OTHER_PATIENT_ID = str(ObjectId())
RECORD_ID = str(ObjectId())
FOLLOWUP_ID = str(ObjectId())
DATA_ID = str(ObjectId())
CREATOR_ID = str(ObjectId())


def make_user(role, user_id):
    now = datetime.utcnow()
    return UserResponse(id=user_id, email="actor@example.com", name="合成操作者",
                        role=role, is_active=True, createdAt=now, updatedAt=now)


def make_record(patient_id=PATIENT_ID):
    return HealthRecordResponse(
        id=RECORD_ID, patient_id=patient_id, record_type="medical_record",
        title="合成档案", content="合成内容", created_by=CREATOR_ID, current_version=1)


def make_followup(patient_id=PATIENT_ID):
    return FollowUpRecordResponse(
        id=FOLLOWUP_ID, patient_id=patient_id, follow_up_type="phone",
        scheduled_date=datetime.utcnow() + timedelta(days=1),
        provider_id=CREATOR_ID, description="合成随访",
        created_by=CREATOR_ID, status=FollowUpStatus.SCHEDULED)


def make_health_data(patient_id=PATIENT_ID):
    return HealthDataResponse(
        id=DATA_ID, patient_id=patient_id, data_type="vital_sign",
        data_content={"heart_rate": 72}, recorded_by=CREATOR_ID, source="manual")


class HealthRecordRouterContractTests(unittest.IsolatedAsyncioTestCase):
    """打桩 HealthRecordService + 合成 JWT；按角色分别断言路由与权限契约。"""

    async def asyncSetUp(self):
        self.service = AsyncMock()
        self.service.get_health_record = AsyncMock(return_value=make_record())
        self.service.list_followup_records = AsyncMock(return_value=[make_followup()])
        self.service.get_upcoming_followups = AsyncMock(return_value=[make_followup()])
        self.service.get_followup_record = AsyncMock(return_value=make_followup())
        self.service.list_health_data = AsyncMock(return_value=[make_health_data()])
        self.service.get_health_data = AsyncMock(return_value=make_health_data())
        self.service.delete_health_record = AsyncMock(return_value=True)
        self.service.get_health_record_version = AsyncMock(return_value={"version": 1})
        self.service.get_medical_timeline = AsyncMock(return_value=[])
        self.service.get_health_record_stats = AsyncMock(return_value={
            "total_records": 0, "record_type_counts": {}, "upcoming_followups": 0,
            "recent_activity": [], "completion_percentage": 0.0, "total_attachments": 0,
        })

        app.dependency_overrides[get_health_record_service] = lambda: self.service
        # get_current_user 的 get_database 依赖也会做真实 Mongo ping；
        # 全部内存打桩，避免触碰（或等待）真实数据库
        async def fake_database():
            yield MagicMock()

        app.dependency_overrides[get_database] = fake_database
        # get_current_user 内部经 UserService 查库；按既有契约测试模式打桩
        self.get_user_mock = AsyncMock(return_value=make_user("doctor", CREATOR_ID))
        self.lookup = patch.object(UserService, "get_user_by_id", new=self.get_user_mock)
        self.lookup.start()
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://health-record-test")

    async def asyncTearDown(self):
        await self.client.aclose()
        self.lookup.stop()
        app.dependency_overrides.clear()

    def login_as(self, role, user_id=None):
        user = make_user(role, user_id or (PATIENT_ID if role == "patient" else CREATOR_ID))
        self.get_user_mock.return_value = user
        token = jwt.encode({"sub": user.id, "token_type": "access",
                            "exp": datetime.utcnow() + timedelta(minutes=5)},
                           settings.SECRET_KEY, algorithm=settings.ALGORITHM)
        return {"Authorization": f"Bearer {token}"}

    # -------- 路由遮蔽修复 --------

    async def test_get_followups_list_is_not_shadowed_by_record_id(self):
        response = await self.client.get(
            "/api/health-records/followups",
            params={"patient_id": PATIENT_ID}, headers=self.login_as("doctor"))
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertIsInstance(body, list)
        self.assertEqual(body[0]["id"], FOLLOWUP_ID)
        self.service.list_followup_records.assert_awaited_once()
        self.assertEqual(self.service.list_followup_records.await_args.kwargs["patient_id"],
                         PATIENT_ID)
        # "followups" 不应再被当作 record_id 查询
        self.service.get_health_record.assert_not_awaited()

    async def test_get_upcoming_followups_is_reachable(self):
        response = await self.client.get(
            "/api/health-records/followups/upcoming", headers=self.login_as("doctor"))
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()[0]["id"], FOLLOWUP_ID)
        self.service.get_upcoming_followups.assert_awaited_once()
        # "upcoming" 不应再被当作 followup_id 查询
        self.service.get_followup_record.assert_not_awaited()

    async def test_get_health_data_list_is_not_shadowed_by_record_id(self):
        response = await self.client.get(
            "/api/health-records/health-data",
            params={"patient_id": PATIENT_ID}, headers=self.login_as("doctor"))
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()[0]["id"], DATA_ID)
        self.service.list_health_data.assert_awaited_once()
        self.service.get_health_record.assert_not_awaited()

    async def test_get_record_by_real_shape_id_still_works(self):
        response = await self.client.get(
            f"/api/health-records/{RECORD_ID}", headers=self.login_as("doctor"))
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["id"], RECORD_ID)
        self.service.get_health_record.assert_awaited_once_with(RECORD_ID)

    async def test_get_missing_record_by_id_is_not_found(self):
        self.service.get_health_record = AsyncMock(return_value=None)
        response = await self.client.get(
            f"/api/health-records/{ObjectId()}", headers=self.login_as("doctor"))
        self.assertEqual(response.status_code, 404, response.text)

    # -------- 未认证 401 --------

    async def test_unauthenticated_access_is_rejected(self):
        for path, params in [
            ("/api/health-records/followups", {"patient_id": PATIENT_ID}),
            ("/api/health-records/followups/upcoming", {}),
            ("/api/health-records/health-data", {"patient_id": PATIENT_ID}),
            (f"/api/health-records/{RECORD_ID}", {}),
        ]:
            response = await self.client.get(path, params=params)
            self.assertEqual(response.status_code, 401, f"GET {path}: {response.text}")
        for service_method in [self.service.list_followup_records,
                               self.service.get_upcoming_followups,
                               self.service.list_health_data,
                               self.service.get_health_record]:
            service_method.assert_not_awaited()

    async def test_invalid_token_is_rejected(self):
        response = await self.client.get(
            "/api/health-records/followups", params={"patient_id": PATIENT_ID},
            headers={"Authorization": "Bearer not-a-jwt"})
        self.assertEqual(response.status_code, 401, response.text)
        self.service.list_followup_records.assert_not_awaited()

    # -------- 权限正反用例 --------

    async def test_patient_can_read_own_record(self):
        response = await self.client.get(
            f"/api/health-records/{RECORD_ID}", headers=self.login_as("patient"))
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["patient_id"], PATIENT_ID)

    async def test_patient_cannot_read_other_patient_record(self):
        self.service.get_health_record = AsyncMock(
            return_value=make_record(patient_id=OTHER_PATIENT_ID))
        response = await self.client.get(
            f"/api/health-records/{RECORD_ID}", headers=self.login_as("patient"))
        self.assertEqual(response.status_code, 403, response.text)

    async def test_admin_can_read_any_patient_record(self):
        # admin 角色具备 VIEW_ANY_HEALTH_RECORD，可跨患者查看
        self.service.get_health_record = AsyncMock(
            return_value=make_record(patient_id=OTHER_PATIENT_ID))
        response = await self.client.get(
            f"/api/health-records/{RECORD_ID}", headers=self.login_as("admin"))
        self.assertEqual(response.status_code, 200, response.text)

    async def test_patient_followup_list_allows_self_and_denies_other(self):
        own = await self.client.get(
            "/api/health-records/followups", params={"patient_id": PATIENT_ID},
            headers=self.login_as("patient"))
        self.assertEqual(own.status_code, 200, own.text)

        other = await self.client.get(
            "/api/health-records/followups", params={"patient_id": OTHER_PATIENT_ID},
            headers=self.login_as("patient"))
        self.assertEqual(other.status_code, 403, other.text)
        self.service.list_followup_records.assert_awaited_once()  # 仅自己的那次

    async def test_patient_upcoming_forced_to_self_scope(self):
        self.service.get_upcoming_followups = AsyncMock(return_value=[])
        response = await self.client.get(
            "/api/health-records/followups/upcoming",
            params={"patient_id": OTHER_PATIENT_ID}, headers=self.login_as("patient"))
        self.assertEqual(response.status_code, 403, response.text)

        own = await self.client.get(
            "/api/health-records/followups/upcoming", headers=self.login_as("patient"))
        self.assertEqual(own.status_code, 200, own.text)
        # 未显式提供 patient_id 的患者被限制为只能查自己的随访
        self.assertEqual(self.service.get_upcoming_followups.await_args.args[0], PATIENT_ID)

    async def test_delete_record_requires_delete_permission(self):
        # doctor 角色无 HEALTH_RECORD_DELETE → 403；admin 有 → 200
        denied = await self.client.delete(
            f"/api/health-records/{RECORD_ID}", headers=self.login_as("doctor"))
        self.assertEqual(denied.status_code, 403, denied.text)
        self.service.delete_health_record.assert_not_awaited()

        allowed = await self.client.delete(
            f"/api/health-records/{RECORD_ID}", headers=self.login_as("admin"))
        self.assertEqual(allowed.status_code, 200, allowed.text)
        self.service.delete_health_record.assert_awaited_once_with(RECORD_ID)


if __name__ == "__main__":
    unittest.main()

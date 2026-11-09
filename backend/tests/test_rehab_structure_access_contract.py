"""REH01 方案结构化端点（版本/处方项/执行事件）对象级授权契约测试。

契约与既有康复对象级端点一致（见 test_rehab_agent_auth_contract.py）：
1. 未认证一律 401，文档加载与归属校验均不触发；
2. 先加载方案文档取 patient_id（不存在/畸形 → 404，不暴露存在性），
   再复用 ensure_patient_access 校验归属（非归属医生 403 PATIENT_NOT_ASSIGNED，
   admin 豁免），读写同一标准，结构服务零调用。
全部使用内存打桩与合成数据，不触碰真实数据库。
"""

import unittest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from bson import ObjectId
from jose import jwt

from app.core.config import settings
from app.core.dependencies import (
    get_database,
    get_rehab_plan_structure_service,
    get_rehabilitation_service,
)
from app.db.mongodb import get_database as db_get_database
from app.main import app
from app.schemas.user import UserResponse
from app.services.user_service import UserService

OPERATOR_ID = "507f1f77bcf86cd799439011"
PATIENT_ID = str(ObjectId())
PLAN_ID = str(ObjectId())
VERSION_ID = str(ObjectId())
ITEM_ID = "item-stable-001"


def make_operator(role="doctor", user_id=OPERATOR_ID):
    now = datetime.utcnow()
    return UserResponse(id=user_id, email="actor@example.com", name="合成操作者",
                        role=role, is_active=True, createdAt=now, updatedAt=now)


class RehabStructureAccessContractTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.operator = make_operator()
        self.patient_doc = {"_id": ObjectId(PATIENT_ID), "role": "patient",
                            "name": "合成患者", "practitioners": [OPERATOR_ID]}
        self.rehab_service = AsyncMock()
        self.rehab_service.get_rehab_plan = AsyncMock(
            return_value={"_id": PLAN_ID, "patient_id": PATIENT_ID, "name": "合成计划"})
        self.structure_service = AsyncMock()
        self.structure_service.create_plan_version = AsyncMock(
            return_value={"_id": VERSION_ID, "version_no": 1})
        self.structure_service.list_plan_versions = AsyncMock(return_value=[])
        self.structure_service.get_plan_version = AsyncMock(
            return_value={"_id": VERSION_ID, "version_no": 1})
        self.structure_service.add_prescription_item = AsyncMock(
            return_value={"item_id": ITEM_ID})
        self.structure_service.list_prescription_items = AsyncMock(return_value=[])
        self.structure_service.record_execution_event = AsyncMock(
            return_value={"event": {"event_id": "evt-1"}, "created": True})
        self.structure_service.list_execution_events = AsyncMock(return_value=[])

        app.dependency_overrides[get_rehabilitation_service] = lambda: self.rehab_service
        app.dependency_overrides[get_rehab_plan_structure_service] = \
            lambda: self.structure_service
        self.database = MagicMock()
        self.database.users.find_one = AsyncMock(return_value=self.patient_doc)

        async def fake_database():
            yield self.database

        # 两个覆盖点指向同一打桩库（app.db.mongodb.get_database 与 core 依赖一致）
        app.dependency_overrides[get_database] = fake_database
        app.dependency_overrides[db_get_database] = fake_database
        self.get_user_mock = AsyncMock(return_value=self.operator)
        self.lookup = patch.object(UserService, "get_user_by_id",
                                   new=self.get_user_mock)
        self.lookup.start()
        self.client = httpx.AsyncClient(app=app, base_url="http://test")

    async def asyncTearDown(self):
        await self.client.aclose()
        self.lookup.stop()
        app.dependency_overrides.clear()

    def auth(self):
        token = jwt.encode({"sub": self.operator.id, "token_type": "access",
                            "exp": datetime.utcnow() + timedelta(minutes=5)},
                           settings.SECRET_KEY, algorithm=settings.ALGORITHM)
        return {"Authorization": f"Bearer {token}"}

    def set_operator(self, role="doctor", user_id=OPERATOR_ID):
        self.operator = make_operator(role=role, user_id=user_id)
        self.get_user_mock.return_value = self.operator

    def structure_endpoints(self):
        """7 个方案结构化端点（method, path, kwargs）。"""
        return [
            ("post", f"/api/rehabilitation/plans/{PLAN_ID}/versions", {}),
            ("get", f"/api/rehabilitation/plans/{PLAN_ID}/versions", {}),
            ("get", f"/api/rehabilitation/plans/{PLAN_ID}/versions/{VERSION_ID}", {}),
            ("post", f"/api/rehabilitation/plans/{PLAN_ID}/versions/{VERSION_ID}/items",
             {"json": {"intervention_type": "exercise", "exercise_id": "ex-1"}}),
            ("get", f"/api/rehabilitation/plans/{PLAN_ID}/items", {}),
            ("post", f"/api/rehabilitation/plans/{PLAN_ID}/items/{ITEM_ID}/events",
             {"json": {"event_id": "evt-1"}}),
            ("get", f"/api/rehabilitation/plans/{PLAN_ID}/items/{ITEM_ID}/events", {}),
        ]

    def structure_business_mocks(self):
        return [
            self.structure_service.create_plan_version,
            self.structure_service.list_plan_versions,
            self.structure_service.get_plan_version,
            self.structure_service.add_prescription_item,
            self.structure_service.list_prescription_items,
            self.structure_service.record_execution_event,
            self.structure_service.list_execution_events,
        ]

    async def test_structure_endpoints_require_authentication(self):
        for method, path, kwargs in self.structure_endpoints():
            response = await getattr(self.client, method)(path, **kwargs)
            self.assertEqual(response.status_code, 401,
                             f"{method.upper()} {path}: {response.text}")
        for business_mock in self.structure_business_mocks():
            business_mock.assert_not_awaited()

    async def test_structure_endpoints_reject_unassigned_doctor(self):
        self.patient_doc["practitioners"] = ["someone-else"]
        headers = self.auth()
        for method, path, kwargs in self.structure_endpoints():
            response = await getattr(self.client, method)(path, headers=headers, **kwargs)
            self.assertEqual(response.status_code, 403,
                             f"{method.upper()} {path}: {response.text}")
            self.assertEqual(response.json()["error"], "PATIENT_NOT_ASSIGNED",
                             f"{method.upper()} {path}: {response.text}")
        # 默认拒绝：归属校验不通过时结构服务零调用
        for business_mock in self.structure_business_mocks():
            business_mock.assert_not_awaited()

    async def test_structure_endpoints_missing_plan_returns_404(self):
        self.rehab_service.get_rehab_plan = AsyncMock(return_value=None)
        headers = self.auth()
        for method, path, kwargs in self.structure_endpoints():
            response = await getattr(self.client, method)(path, headers=headers, **kwargs)
            self.assertEqual(response.status_code, 404,
                             f"{method.upper()} {path}: {response.text}")
        for business_mock in self.structure_business_mocks():
            business_mock.assert_not_awaited()

    async def test_structure_endpoints_malformed_plan_returns_404(self):
        self.rehab_service.get_rehab_plan = AsyncMock(
            return_value={"_id": PLAN_ID, "name": "无归属合成计划"})
        headers = self.auth()
        for method, path, kwargs in self.structure_endpoints():
            response = await getattr(self.client, method)(path, headers=headers, **kwargs)
            self.assertEqual(response.status_code, 404,
                             f"{method.upper()} {path}: {response.text}")
        for business_mock in self.structure_business_mocks():
            business_mock.assert_not_awaited()

    async def test_structure_endpoints_admin_bypass(self):
        self.set_operator(role="admin")
        self.patient_doc["practitioners"] = ["someone-else"]
        headers = self.auth()
        for method, path, kwargs in self.structure_endpoints():
            response = await getattr(self.client, method)(path, headers=headers, **kwargs)
            self.assertIn(response.status_code, (200, 201),
                          f"{method.upper()} {path}: {response.text}")
        # admin 豁免不查患者档案
        self.database.users.find_one.assert_not_awaited()

    async def test_structure_endpoints_allow_assigned_doctor(self):
        headers = self.auth()
        response = await self.client.post(
            f"/api/rehabilitation/plans/{PLAN_ID}/versions", headers=headers)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["version_no"], 1)

        response = await self.client.post(
            f"/api/rehabilitation/plans/{PLAN_ID}/versions/{VERSION_ID}/items",
            json={"intervention_type": "exercise", "exercise_id": "ex-1"},
            headers=headers)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["item_id"], ITEM_ID)

        response = await self.client.post(
            f"/api/rehabilitation/plans/{PLAN_ID}/items/{ITEM_ID}/events",
            json={"event_id": "evt-1"}, headers=headers)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()["created"])
        self.structure_service.record_execution_event.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()

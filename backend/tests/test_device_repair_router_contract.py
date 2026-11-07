"""设备维修记录路由契约测试（缺陷 A / 缺陷 B 收敛）。

device_repair_router 此前以 dict.get("roles", []) 访问认证用户，
而 get_current_user（core.dependencies 再导出 core.auth）返回 pydantic
UserResponse（单角色字段 .role），任何已认证请求在守卫处必然
AttributeError → 500。本测试锁定三层契约：
1. 未认证访问一律 401，数据库查询不被触发；
2. 守卫按 current_user.role 判断：维修记录属只读路径，医疗 staff
   （doctor / health_manager / admin）可查看，患者 403；
3. doctor / health_manager 认证后可正常取数（打桩 db，不触碰真实数据库）。
"""

import importlib
import unittest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from bson import ObjectId
from jose import jwt

from app.core.config import settings
from app.db.mongodb import get_database
from app.main import app
# 注意：app.api.routers 包属性 device_repair_router 被 __init__ 中的
# `router as device_repair_router` 遮蔽，必须用 importlib 取真实模块
device_repair_router = importlib.import_module(
    "app.api.routers.device_repair_router")
from app.schemas.user import UserResponse
from app.services.user_service import UserService

OPERATOR_ID = "507f1f77bcf86cd799439011"
REPAIR_ID = "64b0f1c2a3b4c5d6e7f80901"
DEVICE_ID = "64b0f1c2a3b4c5d6e7f80902"


def make_operator(role="patient", user_id=OPERATOR_ID):
    now = datetime.utcnow()
    return UserResponse(id=user_id, email="actor@example.com", name="合成操作者",
                        role=role, is_active=True, createdAt=now, updatedAt=now)


def make_repair_log():
    return {
        "_id": REPAIR_ID,
        "device_id": DEVICE_ID,
        "device_type": "血压计",
        "repair_time": datetime.utcnow(),
        "initial_status": {"status": "offline"},
        "repair_actions": ["重置设备连接"],
        "repair_results": [{"action": "重置设备连接", "success": True}],
        "overall_success": True,
    }


class DeviceRepairRouterContractTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.operator = make_operator()
        # 路由内以模块属性引用 get_db，直接替换模块属性打桩
        self.db = MagicMock()
        self.get_db_patch = patch.object(
            device_repair_router, "get_db", AsyncMock(return_value=self.db))
        self.get_db_patch.start()

        # 认证链的查库走 UserService 打桩，返回真实 UserResponse
        # （锁定 user 形态契约，而非 dict）
        app.dependency_overrides[get_database] = self._fake_database
        self.get_user_mock = AsyncMock(return_value=self.operator)
        self.lookup = patch.object(UserService, "get_user_by_id",
                                   new=self.get_user_mock)
        self.lookup.start()
        self.client = httpx.AsyncClient(app=app, base_url="http://test")

    @staticmethod
    async def _fake_database():
        yield MagicMock()

    async def asyncTearDown(self):
        await self.client.aclose()
        self.lookup.stop()
        self.get_db_patch.stop()
        app.dependency_overrides.clear()

    def auth(self):
        token = jwt.encode({"sub": self.operator.id, "token_type": "access",
                            "exp": datetime.utcnow() + timedelta(minutes=5)},
                           settings.SECRET_KEY, algorithm=settings.ALGORITHM)
        return {"Authorization": f"Bearer {token}"}

    def _stub_history_chain(self, logs):
        find_mock = MagicMock()
        find_mock.sort.return_value.limit.return_value.to_list = AsyncMock(
            return_value=logs)
        self.db.device_repair_logs.find = MagicMock(return_value=find_mock)

    def _stub_summary_chain(self, logs):
        find_mock = MagicMock()
        find_mock.to_list = AsyncMock(return_value=logs)
        self.db.device_repair_logs.find = MagicMock(return_value=find_mock)

    async def test_endpoints_require_authentication(self):
        # 未认证一律 401，且不触发任何数据库查询
        for method, path in (
            ("get", "/api/device-repairs/history"),
            ("get", f"/api/device-repairs/{REPAIR_ID}"),
            ("get", f"/api/device-repairs/device/{DEVICE_ID}/summary"),
        ):
            response = await getattr(self.client, method)(path)
            self.assertEqual(response.status_code, 401,
                             f"{method.upper()} {path}: {response.text}")
        self.db.device_repair_logs.find.assert_not_called()

    async def test_history_forbidden_for_patient(self):
        # 患者不可查看维修记录（只读守卫限医疗 staff）
        self.operator = make_operator(role="patient")
        self.get_user_mock.return_value = self.operator
        self._stub_history_chain([])
        response = await self.client.get(
            "/api/device-repairs/history", headers=self.auth())
        self.assertEqual(response.status_code, 403, response.text)
        self.db.device_repair_logs.find.assert_not_called()

    async def test_history_accessible_for_doctor(self):
        # 回归锁定（缺陷 A 实际形态）：此前 dict.get("roles") 访问
        # pydantic UserResponse 必然 AttributeError → 500，医生也拿不到历史
        self.operator = make_operator(role="doctor")
        self.get_user_mock.return_value = self.operator
        self._stub_history_chain([make_repair_log()])
        response = await self.client.get(
            "/api/device-repairs/history", headers=self.auth())
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload[0]["_id"], REPAIR_ID)
        self.db.device_repair_logs.find.assert_called_once()

    async def test_history_accessible_for_health_manager(self):
        # 缺陷 B 统一：维修记录属设备数据只读路径，健康管理师可查看
        self.operator = make_operator(role="health_manager")
        self.get_user_mock.return_value = self.operator
        self._stub_history_chain([])
        response = await self.client.get(
            "/api/device-repairs/history", headers=self.auth())
        self.assertEqual(response.status_code, 200, response.text)

    async def test_history_accessible_for_admin(self):
        self.operator = make_operator(role="admin")
        self.get_user_mock.return_value = self.operator
        self._stub_history_chain([])
        response = await self.client.get(
            "/api/device-repairs/history", headers=self.auth())
        self.assertEqual(response.status_code, 200, response.text)

    async def test_repair_details_forbidden_for_patient(self):
        self.operator = make_operator(role="patient")
        self.get_user_mock.return_value = self.operator
        self.db.device_repair_logs.find_one = AsyncMock(
            return_value=make_repair_log())
        response = await self.client.get(
            f"/api/device-repairs/{REPAIR_ID}", headers=self.auth())
        self.assertEqual(response.status_code, 403, response.text)
        self.db.device_repair_logs.find_one.assert_not_called()

    async def test_repair_details_accessible_for_doctor(self):
        self.operator = make_operator(role="doctor")
        self.get_user_mock.return_value = self.operator
        self.db.device_repair_logs.find_one = AsyncMock(
            return_value=make_repair_log())
        response = await self.client.get(
            f"/api/device-repairs/{REPAIR_ID}", headers=self.auth())
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["_id"], REPAIR_ID)

    async def test_repair_details_missing_returns_404(self):
        self.operator = make_operator(role="doctor")
        self.get_user_mock.return_value = self.operator
        self.db.device_repair_logs.find_one = AsyncMock(return_value=None)
        response = await self.client.get(
            f"/api/device-repairs/{REPAIR_ID}", headers=self.auth())
        self.assertEqual(response.status_code, 404, response.text)

    async def test_repair_summary_forbidden_for_patient(self):
        self.operator = make_operator(role="patient")
        self.get_user_mock.return_value = self.operator
        self._stub_summary_chain([])
        response = await self.client.get(
            f"/api/device-repairs/device/{DEVICE_ID}/summary",
            headers=self.auth())
        self.assertEqual(response.status_code, 403, response.text)
        self.db.device_repair_logs.find.assert_not_called()

    async def test_repair_summary_accessible_for_health_manager(self):
        # 缺陷 B 统一：只读统计路径对健康管理师放行
        self.operator = make_operator(role="health_manager")
        self.get_user_mock.return_value = self.operator
        self._stub_summary_chain([make_repair_log()])
        response = await self.client.get(
            f"/api/device-repairs/device/{DEVICE_ID}/summary",
            headers=self.auth())
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["total_repairs"], 1)
        self.assertEqual(payload["successful_repairs"], 1)
        self.assertEqual(payload["success_rate"], 100.0)


if __name__ == "__main__":
    unittest.main()

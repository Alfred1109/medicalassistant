"""康复计划/Agent 路由登录契约测试（AUTH01 阶段一）。

两个 router 原先完全没有鉴权；本测试锁定「必须登录」这一层契约：
未认证访问一律 401，带有效 JWT 才进入业务逻辑。对象级授权待 AUTH01 后续收敛。
全部使用内存打桩与合成数据，不触碰真实数据库。
"""

import unittest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from jose import jwt

from app.core.config import settings
from app.core.dependencies import get_agent_service, get_rehabilitation_service
from app.db.mongodb import get_database
from app.main import app
from app.schemas.user import UserResponse
from app.services.user_service import UserService

OPERATOR_ID = "507f1f77bcf86cd799439011"


def make_operator(role="doctor", user_id=OPERATOR_ID):
    now = datetime.utcnow()
    return UserResponse(id=user_id, email="actor@example.com", name="合成操作者",
                        role=role, is_active=True, createdAt=now, updatedAt=now)


class RehabAgentAuthContractTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.operator = make_operator()
        self.rehab_service = AsyncMock()
        self.rehab_service.list_rehab_plans = AsyncMock(return_value=[])
        self.rehab_service.get_rehab_plan = AsyncMock(return_value={"id": "synthetic"})
        self.rehab_service.create_rehab_plan = AsyncMock(return_value={"id": "synthetic"})
        self.rehab_service.delete_rehab_plan = AsyncMock(return_value=True)
        self.rehab_service.generate_rehab_plan_with_llm = AsyncMock(
            return_value={"patient_id": "synthetic"})
        self.agent_service = AsyncMock()
        self.agent_service.list_agents = AsyncMock(return_value=[])
        self.agent_service.create_agent = AsyncMock(return_value={"id": "synthetic"})

        app.dependency_overrides[get_rehabilitation_service] = lambda: self.rehab_service
        app.dependency_overrides[get_agent_service] = lambda: self.agent_service
        # get_current_user 依赖 get_database；认证链的查库走 UserService 打桩，库连接本身不打真实 MongoDB
        async def fake_database():
            yield MagicMock()

        app.dependency_overrides[get_database] = fake_database
        # get_current_user 内部通过 UserService 查库；按既有契约测试模式打桩
        self.get_user_mock = AsyncMock(return_value=self.operator)
        self.lookup = patch.object(UserService, "get_user_by_id", new=self.get_user_mock)
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

    async def assert_unauthorized(self, method, path, **kwargs):
        response = await getattr(self.client, method)(path, **kwargs)
        self.assertEqual(response.status_code, 401, f"{method.upper()} {path}: {response.text}")

    async def test_rehabilitation_endpoints_require_authentication(self):
        # 覆盖 GET / POST / PUT / DELETE 四类方法各至少一个代表端点
        await self.assert_unauthorized("get", "/api/rehabilitation/plans")
        await self.assert_unauthorized(
            "post", "/api/rehabilitation/plans/generate",
            json={"patient_id": "synthetic", "patient_name": "Synthetic",
                  "condition": "Synthetic", "goal": "Synthetic"})
        await self.assert_unauthorized(
            "put", "/api/rehabilitation/plans/synthetic",
            json={"goal": "Synthetic"})
        await self.assert_unauthorized("delete", "/api/rehabilitation/plans/synthetic")
        # 未认证时业务逻辑不应被触发
        self.rehab_service.list_rehab_plans.assert_not_awaited()

    async def test_agent_endpoints_require_authentication(self):
        await self.assert_unauthorized("get", "/api/agents/")
        await self.assert_unauthorized("post", "/api/agents/",
                                       json={"name": "Synthetic", "description": "Synthetic"})
        await self.assert_unauthorized("get", "/api/agents/synthetic")
        await self.assert_unauthorized(
            "post", "/api/agents/synthetic/query", json={"query": "Synthetic"})
        self.agent_service.list_agents.assert_not_awaited()

    async def test_authenticated_request_reaches_rehabilitation_business_logic(self):
        response = await self.client.get("/api/rehabilitation/plans", headers=self.auth())
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), [])
        self.rehab_service.list_rehab_plans.assert_awaited_once()

    async def test_authenticated_request_reaches_agent_business_logic(self):
        response = await self.client.get("/api/agents/", headers=self.auth())
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), [])
        self.agent_service.list_agents.assert_awaited_once()

    async def test_invalid_token_rejected_even_with_service_override(self):
        response = await self.client.get(
            "/api/rehabilitation/plans", headers={"Authorization": "Bearer not-a-jwt"})
        self.assertEqual(response.status_code, 401)
        self.rehab_service.list_rehab_plans.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()

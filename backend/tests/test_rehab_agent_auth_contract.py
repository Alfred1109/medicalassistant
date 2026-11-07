"""康复计划/Agent 路由鉴权契约测试（AUTH01）。

三层契约：
1. 登录层——未认证访问一律 401，带有效 JWT 才进入业务逻辑；
2. 对象级授权第一层——带患者标识的康复端点校验操作者与患者归属
   （操作者须在患者档案 practitioners 列表中，admin 豁免，否则 403 PATIENT_NOT_ASSIGNED）；
3. 对象级授权第二层——仅持 plan_id/assessment_id 的端点先加载文档取 patient_id
   （文档不存在 → 404 PATIENT_NOT_FOUND 语义，畸形文档不暴露存在性），
   再按同一归属规则校验，读写同一标准，业务逻辑零调用。
全部使用内存打桩与合成数据，不触碰真实数据库。
"""

import unittest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from bson import ObjectId
from jose import jwt

from app.core.config import settings
from app.core.dependencies import get_agent_service, get_rehabilitation_service
from app.db.mongodb import get_database
from app.main import app
from app.schemas.user import UserResponse
from app.services.user_service import UserService

OPERATOR_ID = "507f1f77bcf86cd799439011"
PATIENT_ID = str(ObjectId())
PLAN_ID = str(ObjectId())
ASSESSMENT_ID = str(ObjectId())


def make_operator(role="doctor", user_id=OPERATOR_ID):
    now = datetime.utcnow()
    return UserResponse(id=user_id, email="actor@example.com", name="合成操作者",
                        role=role, is_active=True, createdAt=now, updatedAt=now)


class RehabAgentAuthContractTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.operator = make_operator()
        self.patient_doc = {"_id": ObjectId(PATIENT_ID), "role": "patient",
                            "name": "合成患者", "practitioners": [OPERATOR_ID]}
        self.rehab_service = AsyncMock()
        self.rehab_service.list_rehab_plans = AsyncMock(return_value=[])
        self.rehab_service.get_rehab_plan = AsyncMock(
            return_value={"_id": PLAN_ID, "patient_id": PATIENT_ID, "name": "合成计划"})
        self.rehab_service.create_rehab_plan = AsyncMock(return_value={"id": "synthetic"})
        self.rehab_service.update_rehab_plan = AsyncMock(return_value={"id": "synthetic"})
        self.rehab_service.delete_rehab_plan = AsyncMock(return_value=True)
        self.rehab_service.generate_rehab_plan_with_llm = AsyncMock(
            return_value={"patient_id": "synthetic"})
        self.rehab_service.approve_generated_plan = AsyncMock(
            return_value={"_id": PLAN_ID, "status": "active"})
        self.rehab_service.add_exercises_to_plan = AsyncMock(
            return_value={"_id": PLAN_ID, "patient_id": PATIENT_ID})
        self.rehab_service.update_rehab_plan_phase = AsyncMock(
            return_value={"_id": PLAN_ID, "patient_id": PATIENT_ID, "current_phase": "进步期"})
        self.rehab_service.log_exercise_progress = AsyncMock(
            return_value={"_id": PLAN_ID, "patient_id": PATIENT_ID})
        self.rehab_service.apply_plan_adjustment = AsyncMock(
            return_value={"_id": PLAN_ID, "patient_id": PATIENT_ID})
        self.rehab_service.calculate_plan_statistics = AsyncMock(
            return_value={"plan_id": PLAN_ID, "completion_rate": 0.8})
        self.rehab_service.get_exercise_trends = AsyncMock(
            return_value={"plan_id": PLAN_ID, "trend": []})
        self.rehab_service.get_recommendations = AsyncMock(return_value=[])
        self.rehab_service.list_patient_assessments = AsyncMock(return_value=[])
        self.rehab_service.get_assessment_comparison = AsyncMock(
            return_value={"patient_id": PATIENT_ID})
        self.rehab_service.get_assessment = AsyncMock(
            return_value={"_id": ASSESSMENT_ID, "patient_id": PATIENT_ID,
                          "assessment_type": "initial"})
        self.rehab_service.update_assessment = AsyncMock(
            return_value={"_id": ASSESSMENT_ID, "patient_id": PATIENT_ID})
        self.rehab_service.create_assessment = AsyncMock(return_value={"id": "synthetic"})
        self.agent_service = AsyncMock()
        self.agent_service.list_agents = AsyncMock(return_value=[])
        self.agent_service.create_agent = AsyncMock(return_value={"id": "synthetic"})

        app.dependency_overrides[get_rehabilitation_service] = lambda: self.rehab_service
        app.dependency_overrides[get_agent_service] = lambda: self.agent_service
        # get_current_user 依赖 get_database；认证链的查库走 UserService 打桩，
        # 患者归属校验走 db.users.find_one 打桩，库连接本身不打真实 MongoDB
        self.database = MagicMock()
        self.database.users.find_one = AsyncMock(return_value=self.patient_doc)

        async def fake_database():
            yield self.database

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

    def set_operator(self, role="doctor", user_id=OPERATOR_ID):
        """切换当前操作者（认证链打桩同步更新）。"""
        self.operator = make_operator(role=role, user_id=user_id)
        self.get_user_mock.return_value = self.operator
        return self.operator

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

    # ── AUTH01 对象级授权第一层：患者归属校验 ─────────────────────────────

    def plan_payload(self):
        return {"name": "合成计划", "description": "合成描述", "patient_id": PATIENT_ID,
                "start_date": datetime.utcnow().isoformat(), "goal": "恢复行走"}

    def generate_payload(self):
        return {"patient_id": PATIENT_ID, "patient_name": "合成患者",
                "condition": "膝关節术后", "goal": "恢复行走"}

    def assessment_payload(self):
        return {"patient_id": PATIENT_ID, "assessment_type": "initial"}

    async def test_patient_endpoints_allow_assigned_doctor(self):
        # 查询参数来源
        response = await self.client.get(
            f"/api/rehabilitation/plans?patient_id={PATIENT_ID}", headers=self.auth())
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), [])
        response = await self.client.get(
            f"/api/rehabilitation/exercises/recommendations?patient_id={PATIENT_ID}",
            headers=self.auth())
        self.assertEqual(response.status_code, 200, response.text)
        # 路径参数来源
        response = await self.client.get(
            f"/api/rehabilitation/patients/{PATIENT_ID}/assessments", headers=self.auth())
        self.assertEqual(response.status_code, 200, response.text)
        response = await self.client.get(
            f"/api/rehabilitation/assessments/synthetic/comparison?patient_id={PATIENT_ID}",
            headers=self.auth())
        self.assertEqual(response.status_code, 200, response.text)
        # 请求体来源
        response = await self.client.post("/api/rehabilitation/plans",
                                          json=self.plan_payload(), headers=self.auth())
        self.assertEqual(response.status_code, 200, response.text)
        response = await self.client.post("/api/rehabilitation/plans/generate",
                                          json=self.generate_payload(), headers=self.auth())
        self.assertEqual(response.status_code, 200, response.text)
        response = await self.client.post("/api/rehabilitation/assessments",
                                          json=self.assessment_payload(), headers=self.auth())
        self.assertEqual(response.status_code, 200, response.text)

    async def test_patient_endpoints_reject_unassigned_doctor(self):
        self.patient_doc["practitioners"] = ["someone-else"]
        headers = self.auth()
        for method, path, kwargs in [
            ("get", f"/api/rehabilitation/plans?patient_id={PATIENT_ID}", {}),
            ("get", f"/api/rehabilitation/exercises/recommendations?patient_id={PATIENT_ID}", {}),
            ("get", f"/api/rehabilitation/patients/{PATIENT_ID}/assessments", {}),
            ("get", f"/api/rehabilitation/assessments/synthetic/comparison?patient_id={PATIENT_ID}", {}),
            ("post", "/api/rehabilitation/plans", {"json": self.plan_payload()}),
            ("post", "/api/rehabilitation/plans/generate", {"json": self.generate_payload()}),
            ("post", "/api/rehabilitation/assessments", {"json": self.assessment_payload()}),
        ]:
            response = await getattr(self.client, method)(path, headers=headers, **kwargs)
            self.assertEqual(response.status_code, 403, f"{method.upper()} {path}: {response.text}")
            self.assertEqual(response.json()["error"], "PATIENT_NOT_ASSIGNED",
                             f"{method.upper()} {path}: {response.text}")
        # 默认拒绝：业务逻辑不应被触发
        self.rehab_service.list_rehab_plans.assert_not_awaited()
        self.rehab_service.get_recommendations.assert_not_awaited()
        self.rehab_service.list_patient_assessments.assert_not_awaited()
        self.rehab_service.create_rehab_plan.assert_not_awaited()
        self.rehab_service.generate_rehab_plan_with_llm.assert_not_awaited()
        self.rehab_service.create_assessment.assert_not_awaited()

    async def test_admin_bypasses_patient_assignment(self):
        self.set_operator(role="admin")
        self.patient_doc["practitioners"] = ["someone-else"]
        response = await self.client.get(
            f"/api/rehabilitation/plans?patient_id={PATIENT_ID}", headers=self.auth())
        self.assertEqual(response.status_code, 200, response.text)
        # admin 豁免不查患者档案
        self.database.users.find_one.assert_not_awaited()

    async def test_missing_patient_returns_404(self):
        self.database.users.find_one = AsyncMock(return_value=None)
        response = await self.client.get(
            f"/api/rehabilitation/plans?patient_id={PATIENT_ID}", headers=self.auth())
        self.assertEqual(response.status_code, 404, response.text)
        self.assertEqual(response.json()["error"], "PATIENT_NOT_FOUND")

    async def test_patient_endpoints_require_authentication(self):
        # 未认证时先 401，归属校验不触发
        await self.assert_unauthorized(
            "get", f"/api/rehabilitation/plans?patient_id={PATIENT_ID}")
        await self.assert_unauthorized(
            "get", f"/api/rehabilitation/patients/{PATIENT_ID}/assessments")
        await self.assert_unauthorized(
            "post", "/api/rehabilitation/plans", json=self.plan_payload())
        self.database.users.find_one.assert_not_awaited()


    # ── AUTH01 对象级授权第二层：仅持 plan_id/assessment_id 的端点 ──────────

    def object_level_endpoints(self):
        """13 个仅持 plan_id/assessment_id 的端点（method, path, kwargs）。"""
        return [
            ("post", f"/api/rehabilitation/plans/{PLAN_ID}/approve", {}),
            ("get", f"/api/rehabilitation/plans/{PLAN_ID}", {}),
            ("put", f"/api/rehabilitation/plans/{PLAN_ID}",
             {"json": {"goal": "恢复行走"}}),
            ("delete", f"/api/rehabilitation/plans/{PLAN_ID}", {}),
            ("post", f"/api/rehabilitation/plans/{PLAN_ID}/exercises",
             {"json": {"exercise_ids": []}}),
            ("get", f"/api/rehabilitation/assessments/{ASSESSMENT_ID}", {}),
            ("put", f"/api/rehabilitation/assessments/{ASSESSMENT_ID}",
             {"json": {"notes": "合成备注"}}),
            ("put", f"/api/rehabilitation/plans/{PLAN_ID}/phase",
             {"json": {"phase": "进步期"}}),
            ("post", f"/api/rehabilitation/plans/{PLAN_ID}/exercises/合成运动/progress",
             {"json": {"completed": True}}),
            ("put", f"/api/rehabilitation/plans/{PLAN_ID}/adjustments/合成调整",
             {"json": {"apply": True}}),
            ("get", f"/api/rehabilitation/plans/{PLAN_ID}/detailed", {}),
            ("get", f"/api/rehabilitation/plans/{PLAN_ID}/statistics", {}),
            ("get", f"/api/rehabilitation/plans/{PLAN_ID}/trends", {}),
        ]

    def object_level_business_mocks(self):
        """第二层端点背后的业务方法（403/404 时必须零调用）。"""
        return [
            self.rehab_service.approve_generated_plan,
            self.rehab_service.update_rehab_plan,
            self.rehab_service.delete_rehab_plan,
            self.rehab_service.add_exercises_to_plan,
            self.rehab_service.update_assessment,
            self.rehab_service.update_rehab_plan_phase,
            self.rehab_service.log_exercise_progress,
            self.rehab_service.apply_plan_adjustment,
            self.rehab_service.calculate_plan_statistics,
            self.rehab_service.get_exercise_trends,
        ]

    async def test_object_level_endpoints_reject_unassigned_doctor(self):
        self.patient_doc["practitioners"] = ["someone-else"]
        headers = self.auth()
        for method, path, kwargs in self.object_level_endpoints():
            response = await getattr(self.client, method)(path, headers=headers, **kwargs)
            self.assertEqual(response.status_code, 403, f"{method.upper()} {path}: {response.text}")
            self.assertEqual(response.json()["error"], "PATIENT_NOT_ASSIGNED",
                             f"{method.upper()} {path}: {response.text}")
        # 默认拒绝：归属校验不通过时业务逻辑零调用
        for business_mock in self.object_level_business_mocks():
            business_mock.assert_not_awaited()

    async def test_object_level_endpoints_admin_bypass(self):
        self.set_operator(role="admin")
        self.patient_doc["practitioners"] = ["someone-else"]
        headers = self.auth()
        for method, path, kwargs in self.object_level_endpoints():
            response = await getattr(self.client, method)(path, headers=headers, **kwargs)
            self.assertIn(response.status_code, (200, 204),
                          f"{method.upper()} {path}: {response.text}")
        # admin 豁免不查患者档案
        self.database.users.find_one.assert_not_awaited()

    async def test_object_level_endpoints_missing_document_returns_404(self):
        self.rehab_service.get_rehab_plan = AsyncMock(return_value=None)
        self.rehab_service.get_assessment = AsyncMock(return_value=None)
        headers = self.auth()
        for method, path, kwargs in self.object_level_endpoints():
            response = await getattr(self.client, method)(path, headers=headers, **kwargs)
            self.assertEqual(response.status_code, 404, f"{method.upper()} {path}: {response.text}")
        # 文档不存在时不进入业务逻辑
        for business_mock in self.object_level_business_mocks():
            business_mock.assert_not_awaited()

    async def test_object_level_endpoints_malformed_document_returns_404(self):
        # 畸形文档（缺失 patient_id 字段）按 404 处置，不暴露存在性
        self.rehab_service.get_rehab_plan = AsyncMock(
            return_value={"_id": PLAN_ID, "name": "无归属合成计划"})
        self.rehab_service.get_assessment = AsyncMock(
            return_value={"_id": ASSESSMENT_ID, "assessment_type": "initial"})
        headers = self.auth()
        for method, path, kwargs in self.object_level_endpoints():
            response = await getattr(self.client, method)(path, headers=headers, **kwargs)
            self.assertEqual(response.status_code, 404, f"{method.upper()} {path}: {response.text}")
        for business_mock in self.object_level_business_mocks():
            business_mock.assert_not_awaited()

    async def test_object_level_endpoints_allow_assigned_doctor(self):
        # 只读与变更端点同一归属规则：归属医生全部放行
        headers = self.auth()
        response = await self.client.get(
            f"/api/rehabilitation/plans/{PLAN_ID}", headers=headers)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["patient_id"], PATIENT_ID)

        response = await self.client.put(
            f"/api/rehabilitation/plans/{PLAN_ID}",
            json={"goal": "恢复行走"}, headers=headers)
        self.assertEqual(response.status_code, 200, response.text)
        self.rehab_service.update_rehab_plan.assert_awaited_once()

        response = await self.client.get(
            f"/api/rehabilitation/assessments/{ASSESSMENT_ID}", headers=headers)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["patient_id"], PATIENT_ID)

        response = await self.client.post(
            f"/api/rehabilitation/plans/{PLAN_ID}/exercises/合成运动/progress",
            json={"completed": True}, headers=headers)
        self.assertEqual(response.status_code, 200, response.text)
        self.rehab_service.log_exercise_progress.assert_awaited_once()

    async def test_object_level_endpoints_require_authentication(self):
        # 未认证先 401，文档加载与归属校验均不触发
        await self.assert_unauthorized("get", f"/api/rehabilitation/plans/{PLAN_ID}")
        await self.assert_unauthorized(
            "put", f"/api/rehabilitation/assessments/{ASSESSMENT_ID}",
            json={"notes": "合成备注"})
        self.rehab_service.get_rehab_plan.assert_not_awaited()
        self.rehab_service.get_assessment.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()

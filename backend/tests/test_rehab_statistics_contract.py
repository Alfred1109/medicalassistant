"""康复计划统计/趋势端点契约测试（statistics / trends）。

覆盖 GET /api/rehabilitation/plans/{plan_id}/statistics 与
GET /api/rehabilitation/plans/{plan_id}/trends：
1. 归属医生 200 + 聚合数据正确（合成计划文档，真实 RehabilitationService，
   仅打桩 plans_collection，不触碰真实数据库）；
2. 计划内无进度数据时 200 + 空/null 标注（不 404、不 500）；
3. 非归属医生 403 PATIENT_NOT_ASSIGNED，服务统计方法零调用
   （沿用 AUTH01 第二层契约测试模式）；
4. 计划不存在 404；
5. 非法查询参数（metric/time_range/days）422。
聚合语义见 RehabilitationService.calculate_plan_statistics /
get_exercise_trends 的文档字符串：数据源为 rehab_plans 文档内嵌
exercises[].progress[]（生产唯一真实写入路径），不读无写入方的
rehab_progress 集合；活动度/肌力无对应字段，返回 null 并标注。
"""

import unittest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from bson import ObjectId
from jose import jwt

from app.core.config import settings
from app.core.dependencies import get_rehabilitation_service
from app.db.mongodb import get_database
from app.main import app
from app.schemas.user import UserResponse
from app.services.rehabilitation_service import RehabilitationService
from app.services.user_service import UserService

OPERATOR_ID = "507f1f77bcf86cd799439011"
PATIENT_ID = str(ObjectId())
PLAN_ID = str(ObjectId())


def make_operator(role="doctor", user_id=OPERATOR_ID):
    now = datetime.utcnow()
    return UserResponse(id=user_id, email="actor@example.com", name="合成操作者",
                        role=role, is_active=True, createdAt=now, updatedAt=now)


def days_ago_iso(days: int) -> str:
    """与 log_exercise_progress 写入格式一致：utcnow 的 ISO 字符串。"""
    return (datetime.utcnow() - timedelta(days=days)).isoformat()


def make_plan_doc():
    """合成计划文档：两个运动、7 条内嵌进度记录（含 1 条 40 天前、1 条 20 天前）。

    预期（time_range=all）：total=7, completed=5, rate=71.4，
    avg_pain=(3+2+5+4+1)/5=3.0，avg_difficulty=(2+3+6)/3=3.7。
    month（近30天）：去掉 40 天前 1 条 → total=6, completed=4, rate=66.7。
    week（近7天）：再去掉 20 天前 1 条 → total=5, completed=3, rate=60.0。
    """
    return {
        "_id": ObjectId(PLAN_ID),
        "patient_id": PATIENT_ID,
        "name": "合成计划",
        "status": "active",
        "exercises": [
            {
                "id": "ex1",
                "name": "下肢伸展",
                "progress": [
                    {"date": days_ago_iso(1), "completed": True,
                     "pain_level": 3, "difficulty_rating": 2},
                    {"date": days_ago_iso(2), "completed": True,
                     "pain_level": 2, "difficulty_rating": 3},
                    {"date": days_ago_iso(3), "completed": False,
                     "pain_level": 5, "difficulty_rating": 6},
                    {"date": days_ago_iso(40), "completed": True,
                     "pain_level": None, "difficulty_rating": None},
                ],
            },
            {
                "id": "ex2",
                "name": "平衡训练",
                "progress": [
                    {"date": days_ago_iso(1), "completed": False,
                     "pain_level": None, "difficulty_rating": None},
                    {"date": days_ago_iso(2), "completed": True,
                     "pain_level": 4, "difficulty_rating": None},
                    {"date": days_ago_iso(20), "completed": True,
                     "pain_level": 1, "difficulty_rating": None},
                ],
            },
        ],
    }


class RehabStatisticsContractTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.operator = make_operator()
        self.patient_doc = {"_id": ObjectId(PATIENT_ID), "role": "patient",
                            "name": "合成患者", "practitioners": [OPERATOR_ID]}
        self.plan_doc = make_plan_doc()

        # 真实服务，仅打桩 plans_collection（统计逻辑真实执行）
        self.rehab_service = RehabilitationService(MagicMock())
        self.plans_collection = MagicMock()
        self.plans_collection.find_one = AsyncMock(return_value=self.plan_doc)
        self.rehab_service.plans_collection = self.plans_collection

        app.dependency_overrides[get_rehabilitation_service] = \
            lambda: self.rehab_service
        # 患者归属校验走 db.users.find_one 打桩，不连真实 MongoDB
        self.database = MagicMock()
        self.database.users.find_one = AsyncMock(return_value=self.patient_doc)

        async def fake_database():
            yield self.database

        app.dependency_overrides[get_database] = fake_database
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

    @staticmethod
    def week_start_of(days_ago: int) -> str:
        """与服务端一致的周起点（周一）计算，用于生成期望值。"""
        day = (datetime.utcnow() - timedelta(days=days_ago)).date()
        return (day - timedelta(days=day.weekday())).isoformat()

    # ── 归属医生 200 + 聚合数据正确 ────────────────────────────────────────

    async def test_statistics_returns_aggregated_data_for_assigned_doctor(self):
        response = await self.client.get(
            f"/api/rehabilitation/plans/{PLAN_ID}/statistics", headers=self.auth())
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["plan_id"], PLAN_ID)
        self.assertEqual(body["total_records"], 7)
        self.assertEqual(body["completed_records"], 5)
        self.assertEqual(body["completion_rate"], 71.4)
        self.assertEqual(body["avg_pain_level"], 3.0)
        self.assertEqual(body["avg_difficulty_rating"], 3.7)
        # 无对应字段的指标：null + 标注，不模拟
        self.assertIsNone(body["range_of_motion"])
        self.assertIsNone(body["muscle_strength"])
        self.assertEqual(body["unsupported_metrics"],
                         ["range_of_motion", "muscle_strength"])
        self.assertEqual(body["data_source"],
                         "rehab_plans.exercises[].progress")
        self.assertEqual(body["data_notes"], [])
        # 周完成率：3 个自然周桶，各桶总数合计 7
        weekly = body["weekly_completion"]
        self.assertEqual([w["week_start"] for w in weekly],
                         sorted({self.week_start_of(1), self.week_start_of(20),
                                 self.week_start_of(40)}))
        self.assertEqual(sum(w["total"] for w in weekly), 7)
        self.assertEqual(sum(w["completed"] for w in weekly), 5)
        latest_week = weekly[-1]
        self.assertEqual(latest_week["total"], 5)
        self.assertEqual(latest_week["completed"], 3)
        self.assertEqual(latest_week["completion_rate"], 60.0)
        # 按运动拆分
        per_exercise = {e["exercise_id"]: e for e in body["per_exercise"]}
        self.assertEqual(per_exercise["ex1"]["total"], 4)
        self.assertEqual(per_exercise["ex1"]["completed"], 3)
        self.assertEqual(per_exercise["ex1"]["avg_pain_level"], 3.3)
        self.assertEqual(per_exercise["ex1"]["avg_difficulty_rating"], 3.7)
        self.assertEqual(per_exercise["ex2"]["total"], 3)
        self.assertEqual(per_exercise["ex2"]["completed"], 2)
        self.assertEqual(per_exercise["ex2"]["avg_pain_level"], 2.5)
        self.assertIsNone(per_exercise["ex2"]["avg_difficulty_rating"])

    async def test_statistics_time_range_filters_by_date(self):
        for time_range, total, completed, rate in [
            ("week", 5, 3, 60.0),
            ("month", 6, 4, 66.7),
        ]:
            response = await self.client.get(
                f"/api/rehabilitation/plans/{PLAN_ID}/statistics",
                params={"time_range": time_range}, headers=self.auth())
            self.assertEqual(response.status_code, 200, response.text)
            body = response.json()
            self.assertEqual(body["time_range"], time_range)
            self.assertEqual(body["total_records"], total)
            self.assertEqual(body["completed_records"], completed)
            self.assertEqual(body["completion_rate"], rate)

    async def test_trends_pain_metric_daily_average(self):
        response = await self.client.get(
            f"/api/rehabilitation/plans/{PLAN_ID}/trends",
            params={"metric": "pain", "days": 30}, headers=self.auth())
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["plan_id"], PLAN_ID)
        self.assertEqual(body["metric"], "pain")
        self.assertEqual(body["total_records"], 6)
        # 近30天内有疼痛值的日期：d-20/d-3/d-2/d-1，按日期升序；
        # d-2 有两条记录（ex1 疼痛2、ex2 疼痛4），日均 3.0
        self.assertEqual(body["series"], [
            {"date": self.day_date(20), "value": 1.0},
            {"date": self.day_date(3), "value": 5.0},
            {"date": self.day_date(2), "value": 3.0},
            {"date": self.day_date(1), "value": 3.0},
        ])

    async def test_trends_completion_metric_daily_rate(self):
        response = await self.client.get(
            f"/api/rehabilitation/plans/{PLAN_ID}/trends",
            params={"metric": "completion", "days": 7}, headers=self.auth())
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["total_records"], 5)
        self.assertEqual(body["series"], [
            {"date": self.day_date(3), "total": 1, "completed": 0,
             "completion_rate": 0.0},
            {"date": self.day_date(2), "total": 2, "completed": 2,
             "completion_rate": 100.0},
            {"date": self.day_date(1), "total": 2, "completed": 1,
             "completion_rate": 50.0},
        ])

    async def test_trends_filter_by_exercise(self):
        response = await self.client.get(
            f"/api/rehabilitation/plans/{PLAN_ID}/trends",
            params={"metric": "completion", "exercise_id": "ex1", "days": 30},
            headers=self.auth())
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["exercise_id"], "ex1")
        self.assertEqual(body["total_records"], 3)
        self.assertEqual(len(body["series"]), 3)

    @staticmethod
    def day_date(days_ago: int) -> str:
        return (datetime.utcnow() - timedelta(days=days_ago)).date().isoformat()

    # ── 无进度数据：200 + 空/null 标注 ────────────────────────────────────

    async def test_statistics_without_progress_returns_null_marked_payload(self):
        self.plan_doc["exercises"] = [
            {"id": "ex1", "name": "下肢伸展", "progress": []}]
        response = await self.client.get(
            f"/api/rehabilitation/plans/{PLAN_ID}/statistics", headers=self.auth())
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["total_records"], 0)
        self.assertEqual(body["completed_records"], 0)
        self.assertIsNone(body["completion_rate"])
        self.assertIsNone(body["avg_pain_level"])
        self.assertIsNone(body["avg_difficulty_rating"])
        self.assertEqual(body["weekly_completion"], [])
        self.assertEqual(body["per_exercise"], [])
        self.assertTrue(body["data_notes"])

    async def test_trends_without_progress_returns_empty_series(self):
        self.plan_doc["exercises"] = []
        response = await self.client.get(
            f"/api/rehabilitation/plans/{PLAN_ID}/trends", headers=self.auth())
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["series"], [])
        self.assertEqual(body["total_records"], 0)
        self.assertTrue(body["data_notes"])

    # ── 对象级授权：非归属医生 403 / 计划不存在 404 ────────────────────────

    async def test_statistics_and_trends_reject_unassigned_doctor(self):
        self.patient_doc["practitioners"] = ["someone-else"]
        stats_mock = AsyncMock(return_value={"plan_id": PLAN_ID})
        trends_mock = AsyncMock(return_value={"plan_id": PLAN_ID})
        with patch.object(self.rehab_service, "calculate_plan_statistics",
                          stats_mock), \
             patch.object(self.rehab_service, "get_exercise_trends",
                          trends_mock):
            response = await self.client.get(
                f"/api/rehabilitation/plans/{PLAN_ID}/statistics",
                headers=self.auth())
            self.assertEqual(response.status_code, 403, response.text)
            self.assertEqual(response.json()["error"], "PATIENT_NOT_ASSIGNED")
            response = await self.client.get(
                f"/api/rehabilitation/plans/{PLAN_ID}/trends",
                headers=self.auth())
            self.assertEqual(response.status_code, 403, response.text)
            self.assertEqual(response.json()["error"], "PATIENT_NOT_ASSIGNED")
        stats_mock.assert_not_awaited()
        trends_mock.assert_not_awaited()

    async def test_statistics_and_trends_admin_bypass(self):
        self.operator = make_operator(role="admin")
        self.get_user_mock.return_value = self.operator
        self.patient_doc["practitioners"] = ["someone-else"]
        for path in (f"/api/rehabilitation/plans/{PLAN_ID}/statistics",
                     f"/api/rehabilitation/plans/{PLAN_ID}/trends"):
            response = await self.client.get(path, headers=self.auth())
            self.assertEqual(response.status_code, 200, response.text)
        self.database.users.find_one.assert_not_awaited()

    async def test_statistics_and_trends_missing_plan_returns_404(self):
        self.plans_collection.find_one = AsyncMock(return_value=None)
        for path in (f"/api/rehabilitation/plans/{PLAN_ID}/statistics",
                     f"/api/rehabilitation/plans/{PLAN_ID}/trends"):
            response = await self.client.get(path, headers=self.auth())
            self.assertEqual(response.status_code, 404, response.text)

    # ── 非法查询参数 422 ─────────────────────────────────────────────────

    async def test_invalid_query_params_return_422(self):
        headers = self.auth()
        response = await self.client.get(
            f"/api/rehabilitation/plans/{PLAN_ID}/trends",
            params={"metric": "bogus"}, headers=headers)
        self.assertEqual(response.status_code, 422, response.text)
        response = await self.client.get(
            f"/api/rehabilitation/plans/{PLAN_ID}/statistics",
            params={"time_range": "year"}, headers=headers)
        self.assertEqual(response.status_code, 422, response.text)
        response = await self.client.get(
            f"/api/rehabilitation/plans/{PLAN_ID}/trends",
            params={"days": 0}, headers=headers)
        self.assertEqual(response.status_code, 422, response.text)

    # ── 未认证 401 ───────────────────────────────────────────────────────

    async def test_statistics_and_trends_require_authentication(self):
        for path in (f"/api/rehabilitation/plans/{PLAN_ID}/statistics",
                     f"/api/rehabilitation/plans/{PLAN_ID}/trends"):
            response = await self.client.get(path)
            self.assertEqual(response.status_code, 401, response.text)
        self.plans_collection.find_one.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()

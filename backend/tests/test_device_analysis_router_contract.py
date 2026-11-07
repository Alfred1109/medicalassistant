"""设备分析路由注册契约测试（AUTH01 阶段一）。

device_analysis_router 此前已在包 __init__ 导入但 main.py 从未注册，端点完全不可达。
本测试锁定三层契约：
1. 未认证访问一律 401，业务逻辑（service）不被触发；
2. 带有效 JWT 时请求进入 service（打桩返回合成数据），AUTH01 对象级授权生效：
   属主患者本人放行（属主语义），admin 豁免，医护须在患者 practitioners
   列表（非归属 403 PATIENT_NOT_ASSIGNED，患者/设备文档缺失 404 先于 403）；
3. service 打桩抛错时如实透传（500 INTERNAL_SERVER_ERROR），不伪装成业务响应。
全部使用内存打桩与合成数据，不触碰真实数据库。
"""

import importlib
import unittest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from jose import jwt

from app.core.config import settings
from app.db.mongodb import get_database
from app.main import app
# 注意：app.api.routers 包属性 device_analysis_router 被 __init__ 中的
# `router as device_analysis_router` 遮蔽，必须用 importlib 取真实模块
device_analysis_router = importlib.import_module(
    "app.api.routers.device_analysis_router")
from app.schemas.user import UserResponse
from app.services.user_service import UserService

OPERATOR_ID = "507f1f77bcf86cd799439011"
# 路由层现对 device_id 做 ObjectId.is_valid 粗判（畸形 ID → 404），
# 因此合成设备 ID 必须是合法 ObjectId 十六进制串
DEVICE_ID = "64b0f1c2a3b4c5d6e7f80901"
OTHER_DEVICE_ID = "64b0f1c2a3b4c5d6e7f80902"
MALFORMED_DEVICE_ID = "not-an-objectid"
OTHER_PATIENT_ID = "other-patient"


def make_operator(role="patient", user_id=OPERATOR_ID):
    now = datetime.utcnow()
    return UserResponse(id=user_id, email="actor@example.com", name="合成操作者",
                        role=role, is_active=True, createdAt=now, updatedAt=now)


def make_patient_doc(patient_id=OTHER_PATIENT_ID, practitioners=()):
    """users 集合中的患者档案（AUTH01 归属校验读取 practitioners 列表）"""
    return {"_id": patient_id, "role": "patient", "name": "合成患者",
            "practitioners": list(practitioners)}


class DeviceAnalysisRouterContractTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.operator = make_operator()
        # 路由内以模块属性引用单例 service，直接替换模块属性即可整体打桩
        self.analysis_service = AsyncMock()
        self.analysis_service.detect_data_anomalies = AsyncMock(return_value=[
            {"data_type": "heart_rate", "value": 190.0, "unit": "bpm",
             "timestamp": datetime.utcnow(), "anomaly_score": 92.0,
             "detection_method": "z_score"}])
        self.analysis_service.analyze_data_trend = AsyncMock(return_value={
            "status": "success", "data_type": "heart_rate", "device_id": DEVICE_ID,
            "statistics": {}, "trend": {}, "aggregated_data": [], "prediction": {}})
        self.analysis_service.monitor_device_status = AsyncMock(return_value=[])
        self.analysis_service.generate_device_alerts = AsyncMock(return_value=[])
        self.analysis_service.predict_data_advanced = AsyncMock(return_value={
            "status": "success", "data_type": "heart_rate", "device_id": DEVICE_ID,
            "days_analyzed": 30, "prediction_days": 7, "method": "linear",
            "data_points": 10, "prediction": {}, "all_predictions": None,
            "history": {}})
        # 设备访问粗判所用的 device_service.get_device 同样打桩
        self.device_service = AsyncMock()
        self.device_service.get_device = AsyncMock(return_value={
            "_id": DEVICE_ID, "name": "合成设备",
            "patient_id": OPERATOR_ID})

        self.analysis_patch = patch.object(
            device_analysis_router, "device_analysis_service", self.analysis_service)
        self.device_patch = patch.object(
            device_analysis_router, "device_service", self.device_service)
        self.analysis_patch.start()
        self.device_patch.start()

        # get_database 依赖同时服务认证链与 AUTH01 归属校验
        # （ensure_patient_access 读 db.users.find_one），打桩为可按用例控制
        self.db = MagicMock()
        self.db.users.find_one = AsyncMock(return_value=None)
        app.dependency_overrides[get_database] = self._fake_database
        self.get_user_mock = AsyncMock(return_value=self.operator)
        self.lookup = patch.object(UserService, "get_user_by_id", new=self.get_user_mock)
        self.lookup.start()
        self.client = httpx.AsyncClient(app=app, base_url="http://test")

    async def _fake_database(self):
        yield self.db

    async def asyncTearDown(self):
        await self.client.aclose()
        self.lookup.stop()
        self.analysis_patch.stop()
        self.device_patch.stop()
        app.dependency_overrides.clear()

    def auth(self):
        token = jwt.encode({"sub": self.operator.id, "token_type": "access",
                            "exp": datetime.utcnow() + timedelta(minutes=5)},
                           settings.SECRET_KEY, algorithm=settings.ALGORITHM)
        return {"Authorization": f"Bearer {token}"}

    async def assert_unauthorized(self, path):
        response = await self.client.get(path)
        self.assertEqual(response.status_code, 401, f"GET {path}: {response.text}")

    async def test_router_is_registered(self):
        # 回归锁定：main.py 必须 include 该 router，否则端点 404
        paths = {route.path for route in app.routes}
        self.assertTrue(
            any("/api/device-analysis" in path for path in paths),
            "device_analysis_router 未注册到 app")

    async def test_endpoints_require_authentication(self):
        # 代表性端点：设备维度 / 患者维度 / 预测各一个
        await self.assert_unauthorized(f"/api/device-analysis/anomalies/{DEVICE_ID}")
        await self.assert_unauthorized("/api/device-analysis/patient-devices/synthetic")
        await self.assert_unauthorized(
            f"/api/device-analysis/predict-advanced/{DEVICE_ID}?data_type=heart_rate")
        # 未认证时业务逻辑不应被触发
        self.analysis_service.detect_data_anomalies.assert_not_awaited()
        self.analysis_service.monitor_device_status.assert_not_awaited()
        self.analysis_service.predict_data_advanced.assert_not_awaited()

    async def test_authenticated_request_reaches_service(self):
        response = await self.client.get(
            f"/api/device-analysis/anomalies/{DEVICE_ID}?data_type=heart_rate",
            headers=self.auth())
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload[0]["data_type"], "heart_rate")
        self.assertEqual(payload[0]["detection_method"], "z_score")
        self.analysis_service.detect_data_anomalies.assert_awaited_once_with(
            device_id=DEVICE_ID, data_type="heart_rate", days=30,
            method="z_score")
        self.device_service.get_device.assert_awaited_once_with(DEVICE_ID)

    async def test_patient_scoped_endpoint_reaches_service(self):
        response = await self.client.get(
            f"/api/device-analysis/patient-devices/{OPERATOR_ID}", headers=self.auth())
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), [])
        self.analysis_service.monitor_device_status.assert_awaited_once_with(
            patient_id=OPERATOR_ID, hours=24)

    async def test_patient_scoped_forbidden_for_other_patient(self):
        # AUTH01：患者访问他人聚合数据一律 403（不泄露患者存在性），
        # service 零调用
        for path in (f"/api/device-analysis/patient-devices/{OTHER_PATIENT_ID}",
                     f"/api/device-analysis/alerts/patient/{OTHER_PATIENT_ID}"):
            response = await self.client.get(path, headers=self.auth())
            self.assertEqual(response.status_code, 403, f"GET {path}: {response.text}")
        self.analysis_service.monitor_device_status.assert_not_awaited()
        self.analysis_service.generate_device_alerts.assert_not_awaited()

    async def test_patient_scoped_assigned_doctor_reaches_service(self):
        # AUTH01：归属医护（practitioners 成员）可查看患者聚合数据
        self.operator = make_operator(role="doctor")
        self.get_user_mock.return_value = self.operator
        self.db.users.find_one = AsyncMock(return_value=make_patient_doc(
            practitioners=[OPERATOR_ID]))
        response = await self.client.get(
            f"/api/device-analysis/patient-devices/{OTHER_PATIENT_ID}",
            headers=self.auth())
        self.assertEqual(response.status_code, 200, response.text)
        self.analysis_service.monitor_device_status.assert_awaited_once_with(
            patient_id=OTHER_PATIENT_ID, hours=24)

    async def test_patient_scoped_unassigned_doctor_403_and_no_business_call(self):
        # AUTH01：非归属医生访问患者聚合数据 403 PATIENT_NOT_ASSIGNED
        self.operator = make_operator(role="doctor")
        self.get_user_mock.return_value = self.operator
        self.db.users.find_one = AsyncMock(return_value=make_patient_doc(
            practitioners=["another-doctor"]))
        for path in (f"/api/device-analysis/patient-devices/{OTHER_PATIENT_ID}",
                     f"/api/device-analysis/alerts/patient/{OTHER_PATIENT_ID}"):
            response = await self.client.get(path, headers=self.auth())
            self.assertEqual(response.status_code, 403, f"GET {path}: {response.text}")
            self.assertEqual(response.json()["error"], "PATIENT_NOT_ASSIGNED",
                             f"GET {path}: {response.text}")
        self.analysis_service.monitor_device_status.assert_not_awaited()
        self.analysis_service.generate_device_alerts.assert_not_awaited()

    async def test_patient_scoped_missing_patient_404_for_doctor(self):
        # AUTH01：患者档案不存在 → 404 PATIENT_NOT_FOUND（404 先于 403）
        self.operator = make_operator(role="doctor")
        self.get_user_mock.return_value = self.operator
        response = await self.client.get(
            f"/api/device-analysis/alerts/patient/{OTHER_PATIENT_ID}",
            headers=self.auth())
        self.assertEqual(response.status_code, 404, response.text)
        self.assertEqual(response.json()["error"], "PATIENT_NOT_FOUND")
        self.analysis_service.generate_device_alerts.assert_not_awaited()

    async def test_patient_scoped_admin_exempt(self):
        # AUTH01：admin 豁免归属校验，且不触发患者档案查询
        self.operator = make_operator(role="admin")
        self.get_user_mock.return_value = self.operator
        response = await self.client.get(
            f"/api/device-analysis/patient-devices/{OTHER_PATIENT_ID}",
            headers=self.auth())
        self.assertEqual(response.status_code, 200, response.text)
        self.db.users.find_one.assert_not_awaited()

    async def test_device_scoped_unassigned_doctor_403_and_no_business_call(self):
        # AUTH01：非归属医生访问他人设备分析数据 403，service 零调用
        self.operator = make_operator(role="doctor")
        self.get_user_mock.return_value = self.operator
        self.db.users.find_one = AsyncMock(return_value=make_patient_doc(
            practitioners=["another-doctor"]))
        self.device_service.get_device = AsyncMock(return_value={
            "_id": OTHER_DEVICE_ID, "name": "他人设备",
            "patient_id": OTHER_PATIENT_ID})
        response = await self.client.get(
            f"/api/device-analysis/anomalies/{OTHER_DEVICE_ID}",
            headers=self.auth())
        self.assertEqual(response.status_code, 403, response.text)
        self.assertEqual(response.json()["error"], "PATIENT_NOT_ASSIGNED")
        self.analysis_service.detect_data_anomalies.assert_not_awaited()

    async def test_device_scoped_admin_exempt(self):
        # AUTH01：admin 豁免归属校验，可访问任意设备的分析数据
        self.operator = make_operator(role="admin")
        self.get_user_mock.return_value = self.operator
        self.device_service.get_device = AsyncMock(return_value={
            "_id": OTHER_DEVICE_ID, "name": "他人设备",
            "patient_id": OTHER_PATIENT_ID})
        response = await self.client.get(
            f"/api/device-analysis/anomalies/{OTHER_DEVICE_ID}",
            headers=self.auth())
        self.assertEqual(response.status_code, 200, response.text)
        self.analysis_service.detect_data_anomalies.assert_awaited_once()
        self.db.users.find_one.assert_not_awaited()

    async def test_forbidden_when_device_owned_by_other_patient(self):
        # 患者角色访问他人设备：对象级粗判应拒绝，service 不被调用
        self.device_service.get_device = AsyncMock(return_value={
            "_id": OTHER_DEVICE_ID, "name": "他人设备", "patient_id": "other-patient"})
        response = await self.client.get(
            f"/api/device-analysis/anomalies/{OTHER_DEVICE_ID}", headers=self.auth())
        self.assertEqual(response.status_code, 403, response.text)
        self.analysis_service.detect_data_anomalies.assert_not_awaited()

    async def test_owner_passes_when_patient_id_stored_as_object_id(self):
        # 回归锁定：库中 patient_id 若以 ObjectId 形态存储，属主比较需 str 规范化，
        # 否则属主患者本人会被误判 403
        from bson import ObjectId
        self.device_service.get_device = AsyncMock(return_value={
            "_id": DEVICE_ID, "name": "合成设备",
            "patient_id": ObjectId(OPERATOR_ID)})
        response = await self.client.get(
            f"/api/device-analysis/anomalies/{DEVICE_ID}?data_type=heart_rate",
            headers=self.auth())
        self.assertEqual(response.status_code, 200, response.text)
        self.analysis_service.detect_data_anomalies.assert_awaited_once()

    async def test_malformed_device_id_returns_404(self):
        # 回归锁定：畸形 device_id 不应触发 device_service.get_device 内的
        # ObjectId() 解析异常（此前为 500），应与"设备不存在"语义一致返回 404
        for path in (
            f"/api/device-analysis/anomalies/{MALFORMED_DEVICE_ID}",
            f"/api/device-analysis/monitor/{MALFORMED_DEVICE_ID}",
            f"/api/device-analysis/predict-advanced/{MALFORMED_DEVICE_ID}?data_type=heart_rate",
        ):
            response = await self.client.get(path, headers=self.auth())
            self.assertEqual(response.status_code, 404, f"GET {path}: {response.text}")
        self.device_service.get_device.assert_not_awaited()

    async def test_missing_device_returns_404(self):
        self.device_service.get_device = AsyncMock(return_value=None)
        response = await self.client.get(
            f"/api/device-analysis/anomalies/{OTHER_DEVICE_ID}", headers=self.auth())
        self.assertEqual(response.status_code, 404, response.text)
        self.analysis_service.detect_data_anomalies.assert_not_awaited()

    async def test_predict_advanced_service_error_maps_to_400(self):
        # service 返回 error（如"数据点不足"）时，路由层应转为 400 业务错误，
        # 且该载荷必须能通过 AdvancedPredictionResponse 校验链路（不走响应模型）
        self.analysis_service.predict_data_advanced = AsyncMock(return_value={
            "status": "error",
            "message": "聚合后数据点不足（1 个），无法进行有效的预测分析",
            "data_type": "heart_rate", "device_id": DEVICE_ID})
        response = await self.client.get(
            f"/api/device-analysis/predict-advanced/{DEVICE_ID}?data_type=heart_rate",
            headers=self.auth())
        self.assertEqual(response.status_code, 400, response.text)
        self.assertIn("数据点不足", response.json()["detail"])
        self.analysis_service.predict_data_advanced.assert_awaited_once()

    async def test_service_exception_passes_through(self):
        # service 抛错时如实透传为 500，不伪装成 200/404 之类的业务响应
        self.analysis_service.detect_data_anomalies = AsyncMock(
            side_effect=RuntimeError("synthetic service failure"))
        response = await self.client.get(
            f"/api/device-analysis/anomalies/{DEVICE_ID}", headers=self.auth())
        self.assertEqual(response.status_code, 500, response.text)
        self.assertEqual(response.json()["error"], "INTERNAL_SERVER_ERROR")
        self.analysis_service.detect_data_anomalies.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()

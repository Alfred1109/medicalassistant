"""设备主路由契约测试（AUTH01 阶段一）。

device_router 此前以字典方式访问认证用户（user["_id"] / user.get("role")），
而 get_current_user 返回 pydantic UserResponse，绑定等写路径必然 TypeError → 500。
本测试锁定三层契约：
1. 未认证访问一律 401，业务逻辑（service）不被触发；
2. 带有效 JWT 时以真实 UserResponse 形态进入端点（current_user.id / .role），
   绑定属主匹配可成功落库（打桩 db，不触碰真实数据库）；
3. 畸形设备 ID 与不存在的设备语义一致返回 404；
   device_service 层畸形 ID 返回 None / False（既有"资源不存在"约定）；
4. AUTH01 对象级授权：属主患者本人放行（属主语义），admin 豁免，
   医护须在患者 practitioners 列表（非归属 403 PATIENT_NOT_ASSIGNED，
   患者/设备文档缺失 404 先于 403）。
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
# 注意：app.api.routers 包属性 device_router 被 __init__ 中的
# `router as device_router` 遮蔽，必须用 importlib 取真实模块
device_router = importlib.import_module("app.api.routers.device_router")
from app.schemas.user import UserResponse
from app.services import device_service as device_service_module
from app.services.user_service import UserService

OPERATOR_ID = "507f1f77bcf86cd799439011"
# 路由层对 device_id 做 ObjectId.is_valid 粗判（畸形 ID → 404），
# 合成设备 ID 必须是合法 ObjectId 十六进制串
DEVICE_ID = "64b0f1c2a3b4c5d6e7f80901"
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


def make_device_doc(patient_id=OPERATOR_ID, device_id=DEVICE_ID):
    now = datetime.utcnow()
    return {
        "_id": device_id,
        "device_id": device_id,
        "device_type": "血压计",
        "name": "合成设备",
        "manufacturer": None,
        "model": None,
        "connection_type": "bluetooth",
        "firmware_version": "1.0.0",
        "settings": {},
        "patient_id": patient_id,
        "status": "active",
        "last_connected": now,
        "battery_level": 80,
        "created_at": now,
        "updated_at": now,
    }


class DeviceRouterContractTests(unittest.IsolatedAsyncioTestCase):
    """路由层契约：认证、属主粗判、畸形 ID 语义。"""

    def setUp(self):
        self.operator = make_operator()
        # 路由内以模块属性引用单例 service，直接替换模块属性即可整体打桩
        self.device_service = AsyncMock()
        self.device_service.get_device = AsyncMock(
            return_value=make_device_doc())
        self.device_patch = patch.object(
            device_router, "device_service", self.device_service)
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
        self.device_patch.stop()
        app.dependency_overrides.clear()

    def auth(self, role="patient", user_id=OPERATOR_ID):
        token = jwt.encode({"sub": user_id, "token_type": "access",
                            "exp": datetime.utcnow() + timedelta(minutes=5)},
                           settings.SECRET_KEY, algorithm=settings.ALGORITHM)
        return {"Authorization": f"Bearer {token}"}

    async def test_endpoints_require_authentication(self):
        # 代表性端点：列表读 / 绑定写 / 对象读各一个
        for method, path, kwargs in (
            ("get", "/api/devices/", {}),
            ("post", "/api/devices/bind",
             {"json": {"device_type": "血压计", "name": "合成设备"}}),
            ("get", f"/api/devices/{DEVICE_ID}", {}),
        ):
            response = await getattr(self.client, method)(path, **kwargs)
            self.assertEqual(response.status_code, 401,
                             f"{method.upper()} {path}: {response.text}")
        # 未认证时业务逻辑不应被触发
        self.device_service.get_user_devices.assert_not_awaited()
        self.device_service.bind_device.assert_not_awaited()
        self.device_service.get_device.assert_not_awaited()

    async def test_bind_with_valid_jwt_persists_with_real_user_response(self):
        # 回归锁定：端点必须以 current_user.id 访问认证用户（真实 UserResponse），
        # 此前的 user["_id"] 字典访问在绑定写路径必然 TypeError
        inserted_id = ObjectId(DEVICE_ID)
        db = MagicMock()
        db.devices.insert_one = AsyncMock(
            return_value=MagicMock(inserted_id=inserted_id))
        # 此测试走真实 device_service（打桩 db 落库），需恢复被 setUp
        # 打桩掉的路由模块属性
        with patch.object(device_router, "device_service",
                          device_service_module.device_service), \
             patch.object(device_service_module, "get_db",
                          AsyncMock(return_value=db)):
            response = await self.client.post(
                "/api/devices/bind",
                json={"device_type": "血压计", "name": "家用血压计"},
                headers=self.auth())
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["id"], str(inserted_id))
        self.assertEqual(payload["patient_id"], OPERATOR_ID)
        self.assertEqual(payload["status"], "active")
        db.devices.insert_one.assert_awaited_once()

    async def test_get_device_owner_match_returns_device(self):
        response = await self.client.get(
            f"/api/devices/{DEVICE_ID}", headers=self.auth())
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["name"], "合成设备")
        self.device_service.get_device.assert_awaited_once_with(DEVICE_ID)

    async def test_owner_match_when_patient_id_stored_as_object_id(self):
        # 回归锁定：库中 patient_id 若以 ObjectId 形态存储，属主比较需 str 规范化
        self.device_service.get_device = AsyncMock(return_value=make_device_doc(
            patient_id=ObjectId(OPERATOR_ID)))
        response = await self.client.get(
            f"/api/devices/{DEVICE_ID}", headers=self.auth())
        self.assertEqual(response.status_code, 200, response.text)

    async def test_forbidden_when_device_owned_by_other_patient(self):
        self.device_service.get_device = AsyncMock(return_value=make_device_doc(
            patient_id="other-patient"))
        response = await self.client.get(
            f"/api/devices/{DEVICE_ID}", headers=self.auth())
        self.assertEqual(response.status_code, 403, response.text)

    async def test_unbind_forbidden_for_other_patient(self):
        # 解绑权限比读取更严：仅属主或管理员
        self.device_service.get_device = AsyncMock(return_value=make_device_doc(
            patient_id="other-patient"))
        response = await self.client.delete(
            f"/api/devices/{DEVICE_ID}/unbind", headers=self.auth())
        self.assertEqual(response.status_code, 403, response.text)
        self.device_service.unbind_device.assert_not_awaited()

    async def test_missing_device_returns_404(self):
        self.device_service.get_device = AsyncMock(return_value=None)
        response = await self.client.get(
            f"/api/devices/{DEVICE_ID}", headers=self.auth())
        self.assertEqual(response.status_code, 404, response.text)

    async def test_sync_returns_503_for_owner_without_mock_data(self):
        # 去模拟化（REM02）：设备真实数据源未接入，同步端点如实 503，
        # 不再随机生成心率/睡眠等数据伪装同步成功
        self.device_service.sync_device_data = AsyncMock(
            return_value={"success": False,
                          "message": "设备数据源未接入，无法同步真实采集数据"})
        response = await self.client.post(
            f"/api/devices/{DEVICE_ID}/sync", headers=self.auth())
        self.assertEqual(response.status_code, 503, response.text)
        self.assertIn("设备数据源未接入", response.json()["detail"])
        self.device_service.sync_device_data.assert_awaited_once_with(DEVICE_ID)

    async def test_assigned_doctor_can_configure_patient_device(self):
        # AUTH01：医生对他人设备的变更操作须为该患者的主管医护
        # （practitioners 列表成员），变更授权角色仍生效
        # （原以此锁定 repair 端点；该端点因伪造修复结果已删除，改由
        # configure 这一真实变更操作承载同等授权语义）
        self.operator = make_operator(role="doctor")
        self.get_user_mock.return_value = self.operator
        self.db.users.find_one = AsyncMock(return_value=make_patient_doc(
            practitioners=[OPERATOR_ID]))
        self.device_service.get_device = AsyncMock(return_value=make_device_doc(
            patient_id=OTHER_PATIENT_ID))
        self.device_service.configure_device = AsyncMock(
            return_value={"success": True, "message": "设备配置已更新"})
        response = await self.client.put(
            f"/api/devices/{DEVICE_ID}/config",
            json={"sync_frequency": "hourly"}, headers=self.auth())
        self.assertEqual(response.status_code, 200, response.text)
        self.device_service.configure_device.assert_awaited_once()

    async def test_configure_forbidden_for_other_patient(self):
        # 非属主患者配置他人设备：403，service 不被触发
        self.device_service.get_device = AsyncMock(return_value=make_device_doc(
            patient_id="other-patient"))
        self.device_service.configure_device = AsyncMock()
        response = await self.client.put(
            f"/api/devices/{DEVICE_ID}/config",
            json={"sync_frequency": "hourly"}, headers=self.auth())
        self.assertEqual(response.status_code, 403, response.text)
        self.device_service.configure_device.assert_not_awaited()

    async def test_assigned_health_manager_can_read_device_detail(self):
        # 健康管理师可查看其负责患者的设备数据（只读路径放行，须有归属关系）
        self.operator = make_operator(role="health_manager")
        self.get_user_mock.return_value = self.operator
        self.db.users.find_one = AsyncMock(return_value=make_patient_doc(
            practitioners=[OPERATOR_ID]))
        self.device_service.get_device = AsyncMock(return_value=make_device_doc(
            patient_id=OTHER_PATIENT_ID))
        response = await self.client.get(
            f"/api/devices/{DEVICE_ID}", headers=self.auth())
        self.assertEqual(response.status_code, 200, response.text)

    async def test_health_manager_can_read_device_data_and_status(self):
        # 只读路径（data/status）对有归属关系的健康管理师保持放行
        self.operator = make_operator(role="health_manager")
        self.get_user_mock.return_value = self.operator
        self.db.users.find_one = AsyncMock(return_value=make_patient_doc(
            practitioners=[OPERATOR_ID]))
        self.device_service.get_device = AsyncMock(return_value=make_device_doc(
            patient_id=OTHER_PATIENT_ID))
        self.device_service.get_device_data = AsyncMock(return_value=[])
        self.device_service.get_device_status = AsyncMock(return_value={
            "status": "active", "battery_level": 80, "signal_strength": 4,
            "last_sync_time": None})
        data_resp = await self.client.get(
            f"/api/devices/{DEVICE_ID}/data", headers=self.auth())
        status_resp = await self.client.get(
            f"/api/devices/{DEVICE_ID}/status", headers=self.auth())
        self.assertEqual(data_resp.status_code, 200, data_resp.text)
        self.assertEqual(status_resp.status_code, 200, status_resp.text)

    async def test_unassigned_doctor_read_forbidden_and_no_business_call(self):
        # AUTH01：非归属医生即使具备设备只读角色，未在患者 practitioners
        # 列表中也是 403 PATIENT_NOT_ASSIGNED，且业务逻辑零调用
        self.operator = make_operator(role="doctor")
        self.get_user_mock.return_value = self.operator
        self.db.users.find_one = AsyncMock(return_value=make_patient_doc(
            practitioners=["another-doctor"]))
        self.device_service.get_device = AsyncMock(return_value=make_device_doc(
            patient_id=OTHER_PATIENT_ID))
        self.device_service.get_device_data = AsyncMock()
        self.device_service.get_device_status = AsyncMock()
        for path in (f"/api/devices/{DEVICE_ID}",
                     f"/api/devices/{DEVICE_ID}/data",
                     f"/api/devices/{DEVICE_ID}/status",
                     f"/api/devices/{DEVICE_ID}/sync"):
            method = "post" if path.endswith("/sync") else "get"
            response = await getattr(self.client, method)(
                path, headers=self.auth())
            self.assertEqual(response.status_code, 403,
                             f"{method.upper()} {path}: {response.text}")
            self.assertEqual(response.json()["error"], "PATIENT_NOT_ASSIGNED",
                             f"{method.upper()} {path}: {response.text}")
        self.device_service.get_device_data.assert_not_awaited()
        self.device_service.get_device_status.assert_not_awaited()

    async def test_unassigned_doctor_mutate_forbidden_and_no_business_call(self):
        # AUTH01：非归属医生的变更请求（同步/配置）同样 403，service 零调用
        self.operator = make_operator(role="doctor")
        self.get_user_mock.return_value = self.operator
        self.db.users.find_one = AsyncMock(return_value=make_patient_doc(
            practitioners=["another-doctor"]))
        self.device_service.get_device = AsyncMock(return_value=make_device_doc(
            patient_id=OTHER_PATIENT_ID))
        self.device_service.sync_device_data = AsyncMock()
        self.device_service.configure_device = AsyncMock()
        sync_resp = await self.client.post(
            f"/api/devices/{DEVICE_ID}/sync", headers=self.auth())
        config_resp = await self.client.put(
            f"/api/devices/{DEVICE_ID}/config",
            json={"sync_frequency": "hourly"}, headers=self.auth())
        self.assertEqual(sync_resp.status_code, 403, sync_resp.text)
        self.assertEqual(config_resp.status_code, 403, config_resp.text)
        self.device_service.sync_device_data.assert_not_awaited()
        self.device_service.configure_device.assert_not_awaited()

    async def test_admin_exempt_from_patient_assignment(self):
        # AUTH01：admin 豁免归属校验（不查 practitioners），可访问任意设备
        self.operator = make_operator(role="admin")
        self.get_user_mock.return_value = self.operator
        self.device_service.get_device = AsyncMock(return_value=make_device_doc(
            patient_id=OTHER_PATIENT_ID))
        self.device_service.get_device_data = AsyncMock(return_value=[])
        self.device_service.get_device_status = AsyncMock(return_value={
            "status": "active", "battery_level": 80, "signal_strength": 4,
            "last_sync_time": None})
        detail_resp = await self.client.get(
            f"/api/devices/{DEVICE_ID}", headers=self.auth())
        data_resp = await self.client.get(
            f"/api/devices/{DEVICE_ID}/data", headers=self.auth())
        status_resp = await self.client.get(
            f"/api/devices/{DEVICE_ID}/status", headers=self.auth())
        self.assertEqual(detail_resp.status_code, 200, detail_resp.text)
        self.assertEqual(data_resp.status_code, 200, data_resp.text)
        self.assertEqual(status_resp.status_code, 200, status_resp.text)
        # admin 豁免路径不触发患者档案查询
        self.db.users.find_one.assert_not_awaited()

    async def test_device_without_patient_id_404_for_staff(self):
        # AUTH01：设备文档缺 patient_id 的畸形数据按 404 处置（不暴露存在性），
        # 与设备本身不存在语义一致
        self.operator = make_operator(role="doctor")
        self.get_user_mock.return_value = self.operator
        self.device_service.get_device = AsyncMock(return_value=make_device_doc(
            patient_id=None))
        response = await self.client.get(
            f"/api/devices/{DEVICE_ID}", headers=self.auth())
        self.assertEqual(response.status_code, 404, response.text)

    async def test_missing_patient_doc_404_for_staff(self):
        # AUTH01：设备指向的患者档案不存在 → 404 PATIENT_NOT_FOUND
        # （患者不存在先于归属判定，与 7c5d690 语义一致）
        self.operator = make_operator(role="doctor")
        self.get_user_mock.return_value = self.operator
        self.db.users.find_one = AsyncMock(return_value=None)
        self.device_service.get_device = AsyncMock(return_value=make_device_doc(
            patient_id=OTHER_PATIENT_ID))
        response = await self.client.get(
            f"/api/devices/{DEVICE_ID}/data", headers=self.auth())
        self.assertEqual(response.status_code, 404, response.text)
        self.assertEqual(response.json()["error"], "PATIENT_NOT_FOUND")

    async def test_configure_forbidden_for_health_manager(self):
        # 回归锁定（缺陷 B）：配置属变更操作，健康管理师不可执行
        self.operator = make_operator(role="health_manager")
        self.get_user_mock.return_value = self.operator
        self.device_service.get_device = AsyncMock(return_value=make_device_doc(
            patient_id="other-patient"))
        self.device_service.configure_device = AsyncMock()
        response = await self.client.put(
            f"/api/devices/{DEVICE_ID}/config",
            json={"sync_frequency": "hourly"}, headers=self.auth())
        self.assertEqual(response.status_code, 403, response.text)
        self.device_service.configure_device.assert_not_awaited()

    async def test_owner_patient_can_configure_own_device(self):
        # 属主患者可配置自己名下设备（变更守卫含属主本人）
        self.device_service.configure_device = AsyncMock(
            return_value={"success": True, "message": "设备配置已更新"})
        response = await self.client.put(
            f"/api/devices/{DEVICE_ID}/config",
            json={"sync_frequency": "hourly"}, headers=self.auth())
        self.assertEqual(response.status_code, 200, response.text)
        self.device_service.configure_device.assert_awaited_once()

    async def test_malformed_device_id_returns_404(self):
        # 回归锁定：畸形 device_id 不应触发 ObjectId() 解析异常（此前 500），
        # 应与"设备不存在"语义一致返回 404，且不触发 service 查询
        for method, path, kwargs in (
            ("get", f"/api/devices/{MALFORMED_DEVICE_ID}", {}),
            ("delete", f"/api/devices/{MALFORMED_DEVICE_ID}/unbind", {}),
            ("get", f"/api/devices/{MALFORMED_DEVICE_ID}/data", {}),
            ("get", f"/api/devices/{MALFORMED_DEVICE_ID}/status", {}),
            ("post", f"/api/devices/{MALFORMED_DEVICE_ID}/sync", {}),
            ("put", f"/api/devices/{MALFORMED_DEVICE_ID}/config",
             {"json": {"sync_frequency": "hourly"}}),
        ):
            response = await getattr(self.client, method)(
                path, headers=self.auth(), **kwargs)
            self.assertEqual(response.status_code, 404,
                             f"{method.upper()} {path}: {response.text}")
        self.device_service.get_device.assert_not_awaited()


class DeviceServiceMalformedIdContractTests(unittest.IsolatedAsyncioTestCase):
    """服务层契约：畸形 ID 返回既有"资源不存在"约定值，不抛 InvalidId。"""

    def setUp(self):
        self.db = MagicMock()
        self.db.devices.insert_one = AsyncMock(
            return_value=MagicMock(inserted_id=ObjectId(DEVICE_ID)))
        self.db.devices.find_one = AsyncMock(return_value=None)
        self.db.devices.update_one = AsyncMock(
            return_value=MagicMock(modified_count=1))
        self.get_db_patch = patch.object(
            device_service_module, "get_db", AsyncMock(return_value=self.db))
        self.get_db_patch.start()

    async def asyncTearDown(self):
        self.get_db_patch.stop()

    async def test_get_device_malformed_id_returns_none(self):
        result = await device_service_module.device_service.get_device(
            MALFORMED_DEVICE_ID)
        self.assertIsNone(result)
        self.db.devices.find_one.assert_not_awaited()

    async def test_unbind_device_malformed_id_returns_false(self):
        result = await device_service_module.device_service.unbind_device(
            OPERATOR_ID, MALFORMED_DEVICE_ID)
        self.assertFalse(result)
        self.db.devices.update_one.assert_not_awaited()

    async def test_bind_device_persists_with_owner_and_string_id(self):
        result = await device_service_module.device_service.bind_device(
            OPERATOR_ID, {"device_type": "血压计", "name": "家用血压计"})
        self.assertIsNone(result.get("error"))
        self.assertEqual(result["_id"], str(ObjectId(DEVICE_ID)))
        self.assertEqual(result["patient_id"], OPERATOR_ID)
        self.assertEqual(result["status"], "active")
        self.db.devices.insert_one.assert_awaited_once()

    async def test_get_device_valid_id_normalizes_object_id(self):
        self.db.devices.find_one = AsyncMock(
            return_value=make_device_doc(patient_id=OPERATOR_ID))
        result = await device_service_module.device_service.get_device(DEVICE_ID)
        self.assertEqual(result["_id"], DEVICE_ID)
        self.db.devices.find_one.assert_awaited_once_with(
            {"_id": ObjectId(DEVICE_ID)})

    async def test_sync_device_data_refuses_without_device_source(self):
        # 去模拟化（REM02）：设备真实数据源未接入时如实拒绝，
        # 不生成任何采集数据、不更新 last_connected
        self.db.devices.find_one = AsyncMock(
            return_value=make_device_doc(patient_id=OPERATOR_ID))
        result = await device_service_module.device_service.sync_device_data(
            DEVICE_ID)
        self.assertFalse(result["success"])
        self.assertIn("设备数据源未接入", result["message"])
        self.db.device_data.insert_many.assert_not_called()
        self.db.devices.update_one.assert_not_awaited()

    async def test_get_device_status_reports_unreported_fields_as_none(self):
        # 去模拟化：电量/信号全库无真实上报路径（bind_device 不采集），
        # 状态仅由 last_connected 真实推导，不再随机生成 30-100 电量与
        # 1-5 信号格；库中未存储电量时如实为 None
        doc = make_device_doc(patient_id=OPERATOR_ID)
        doc["last_connected"] = datetime.utcnow()
        doc["battery_level"] = None
        self.db.devices.find_one = AsyncMock(return_value=doc)
        result = await device_service_module.device_service.get_device_status(
            DEVICE_ID)
        self.assertEqual(result["status"], "online")
        self.assertIsNone(result["battery_level"])
        self.assertIsNone(result["signal_strength"])
        self.assertEqual(result["last_sync_time"], doc["last_connected"])


if __name__ == "__main__":
    unittest.main()

"""设备分析服务层契约测试。

锁定 device_analysis_service 三个已修复缺陷的回归行为：
1. predict_data_advanced 曾以不存在的 "value" 键读取聚合结果（键实为
   timestamp/count/mean/median/max/min/std），设备有足够数据时必然 KeyError；
   现按算法语义取每期 mean，聚合点充足时正常返回预测。
2. monitor_device_status 曾直接 ObjectId(device_id)，畸形 ID 抛 InvalidId；
   现畸形 ID 视为设备不存在，返回空列表（路由层 404 语义一致）。
3. _linear_prediction 残差标准差除以 (n-2)，聚合点数 <3 时除零/负数开方；
   现聚合点不足时服务层返回明确的 error 状态，置信区间计算也有内部防护。
全部使用内存打桩与合成数据，不触碰真实数据库。
"""

import unittest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from bson import ObjectId

from app.services import device_analysis_service as damodule
from app.services.device_analysis_service import device_analysis_service

OPERATOR_ID = "507f1f77bcf86cd799439011"
DEVICE_ID = "64b0f1c2a3b4c5d6e7f80901"
MALFORMED_DEVICE_ID = "not-an-objectid"


def make_device_data(count, spacing_hours=24, start=None):
    """合成设备数据：默认每条间隔一天（聚合后 count 个日聚合点）。

    spacing_hours=0 时所有点落在同一小时，聚合后仅 1 个聚合点。
    """
    start = start or datetime(2026, 1, 1, 8, 0, 0)
    return [
        {
            "device_id": DEVICE_ID,
            "data_type": "heart_rate",
            "value": 70.0 + i,
            "unit": "bpm",
            "timestamp": start + timedelta(hours=i * spacing_hours),
        }
        for i in range(count)
    ]


class DeviceAnalysisServiceContractTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.device_service_mock = AsyncMock()
        # service 模块以 `from ..services.device_service import device_service`
        # 导入单例，直接替换模块属性即可整体打桩
        self.device_patch = patch.object(
            damodule, "device_service", self.device_service_mock)
        self.device_patch.start()

    def tearDown(self):
        self.device_patch.stop()

    async def test_predict_advanced_success_with_sufficient_data(self):
        # 回归锁定：聚合项无 "value" 键，此前必然 KeyError → 500
        self.device_service_mock.get_device_data = AsyncMock(
            return_value=make_device_data(12))
        result = await device_analysis_service.predict_data_advanced(
            device_id=DEVICE_ID, data_type="heart_rate",
            days=30, prediction_days=7, method="linear",
            confidence_interval=True)
        self.assertEqual(result["status"], "success", result)
        self.assertEqual(len(result["prediction"]["values"]), 7)
        self.assertEqual(len(result["prediction"]["confidence_interval"]), 7)
        for interval in result["prediction"]["confidence_interval"]:
            self.assertLessEqual(interval["lower"], interval["upper"])
        self.device_service_mock.get_device_data.assert_awaited_once()

    async def test_predict_advanced_success_for_each_method(self):
        # 各预测方法在足够数据上均不抛错（linear/arima/prophet/ensemble）
        self.device_service_mock.get_device_data = AsyncMock(
            return_value=make_device_data(14))
        for method in ("linear", "arima", "prophet", "ensemble"):
            result = await device_analysis_service.predict_data_advanced(
                device_id=DEVICE_ID, data_type="heart_rate",
                method=method, prediction_days=5)
            self.assertEqual(result["status"], "success", f"method={method}: {result}")
            self.assertEqual(len(result["prediction"]["values"]), 5)

    async def test_predict_advanced_fails_when_aggregation_too_sparse(self):
        # 10 个原始点全部落在同一小时 → 聚合后仅 1 个点，
        # 应返回明确失败而非除零/伪装预测成功
        self.device_service_mock.get_device_data = AsyncMock(
            return_value=make_device_data(10, spacing_hours=0))
        result = await device_analysis_service.predict_data_advanced(
            device_id=DEVICE_ID, data_type="heart_rate",
            method="linear", confidence_interval=True)
        self.assertEqual(result["status"], "error", result)
        self.assertIn("数据点不足", result["message"])
        self.assertNotIn("prediction", result)

    async def test_predict_advanced_fails_when_raw_points_under_five(self):
        # 原始点不足 5 个：返回 error（而非缺失预测字段的 warning，
        # 否则路由层 AdvancedPredictionResponse 校验失败 → 500）
        self.device_service_mock.get_device_data = AsyncMock(
            return_value=make_device_data(3))
        result = await device_analysis_service.predict_data_advanced(
            device_id=DEVICE_ID, data_type="heart_rate", method="linear")
        self.assertEqual(result["status"], "error", result)
        self.assertIn("数据点过少", result["message"])

    async def test_linear_prediction_no_division_by_zero_with_few_points(self):
        # 残差标准差除以 (n-2)：n=2 除零、n=1 负数开方，均应跳过置信区间
        for values in ([1.0, 2.0], [5.0]):
            predictions, confidence = device_analysis_service._linear_prediction(
                values, prediction_days=3, with_confidence=True)
            self.assertEqual(len(predictions), 3)
            self.assertIsNone(confidence)

    async def test_monitor_device_status_malformed_id_returns_empty(self):
        # 回归锁定：畸形 device_id 视为设备不存在（空列表），不再抛 InvalidId
        db = MagicMock()
        db.devices.find.return_value.to_list = AsyncMock(return_value=[])
        with patch.object(damodule, "get_db", new=AsyncMock(return_value=db)):
            result = await device_analysis_service.monitor_device_status(
                device_id=MALFORMED_DEVICE_ID)
        self.assertEqual(result, [])
        db.devices.find.assert_not_called()

    async def test_monitor_device_status_with_valid_device(self):
        # 合法 ObjectId：正常查询并返回状态结果，_id 已字符串化
        db = MagicMock()
        db.devices.find.return_value.to_list = AsyncMock(return_value=[{
            "_id": ObjectId(DEVICE_ID),
            "patient_id": OPERATOR_ID,
            "name": "合成设备",
            "status": "active",
        }])
        # get_device_status 返回空 dict：电量/信号未上报（None，去模拟化后
        # 不再按 0 误判扣分，如实不计分）+ 从未同步(+40) → 得分 40 > 20，进入结果
        self.device_service_mock.get_device_status = AsyncMock(return_value={})
        with patch.object(damodule, "get_db", new=AsyncMock(return_value=db)):
            result = await device_analysis_service.monitor_device_status(
                device_id=DEVICE_ID)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["device"]["_id"], DEVICE_ID)
        self.assertEqual(result[0]["status_score"], 40)


if __name__ == "__main__":
    unittest.main()

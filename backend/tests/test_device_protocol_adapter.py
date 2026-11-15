"""T74 设备协议适配器测试：JMD-540 骨架适配器 + 模拟回放器。

覆盖：合法帧解析、畸形载荷（缺字段/坏类型/空帧）、心跳帧、
协议假设清单完整性、注册表型号匹配、模拟回放器确定性（REM02：
无随机源）与 simulated 强制标记。
"""
import unittest
from datetime import datetime, timedelta

from app.services.device_protocol import (
    JMD540Adapter,
    JMD540_PROTOCOL_ASSUMPTIONS,
    JMD540SimulatedReplayer,
    get_protocol_adapter,
    register_protocol_adapter,
    DeviceProtocolAdapter,
    ProtocolParseError,
)

VALID_FRAME = {
    "device_sn": "JMD-540-A001",
    "measured_at": "2026-11-15T08:00:00Z",
    "metrics": [
        {"metric": "heart_rate", "value": 72, "unit": "bpm"},
        {"metric": "spo2", "value": 97},
    ],
}


class JMD540AdapterParseTests(unittest.TestCase):
    def setUp(self):
        self.adapter = JMD540Adapter()

    def test_valid_frame_parses_to_standard_readings(self):
        result = self.adapter.parse(VALID_FRAME)
        self.assertTrue(result.ok, result.errors)
        self.assertEqual(result.device_sn, "JMD-540-A001")
        self.assertEqual(len(result.readings), 2)
        hr = result.readings[0]
        self.assertEqual(hr.data_type, "heart_rate")
        self.assertEqual(hr.value, 72.0)
        self.assertEqual(hr.unit, "bpm")
        # 假设：Z 后缀 = UTC；入库统一 naive UTC
        self.assertEqual(hr.timestamp, datetime(2026, 11, 15, 8, 0, 0))
        self.assertEqual(hr.metadata["adapter_id"], "jmd540")
        # 假设：unit 缺省按指标表补齐
        self.assertEqual(result.readings[1].unit, "%")

    def test_missing_device_sn_is_error(self):
        frame = {**VALID_FRAME, "device_sn": ""}
        result = self.adapter.parse(frame)
        self.assertFalse(result.ok)
        self.assertTrue(any("device_sn" in e for e in result.errors))

    def test_missing_measured_at_rejects_all_readings(self):
        frame = {**VALID_FRAME}
        frame.pop("measured_at")
        result = self.adapter.parse(frame)
        self.assertFalse(result.ok)
        self.assertEqual(result.readings, [])  # 时间戳是读数必填项

    def test_unparseable_measured_at_rejected(self):
        result = self.adapter.parse(
            {**VALID_FRAME, "measured_at": "昨天下午"})
        self.assertFalse(result.ok)
        self.assertEqual(result.readings, [])

    def test_missing_metrics_is_error(self):
        result = self.adapter.parse({"device_sn": "S", "measured_at": "2026-11-15T08:00:00Z"})
        self.assertFalse(result.ok)
        self.assertTrue(any("metrics" in e for e in result.errors))

    def test_empty_metrics_is_heartbeat_frame(self):
        result = self.adapter.parse({
            "device_sn": "S", "measured_at": "2026-11-15T08:00:00Z",
            "metrics": []})
        self.assertTrue(result.is_heartbeat)
        self.assertEqual(result.readings, [])

    def test_malformed_metric_entries_do_not_abort_frame(self):
        frame = {
            "device_sn": "S", "measured_at": "2026-11-15T08:00:00Z",
            "metrics": [
                {"metric": "heart_rate", "value": "七十二"},  # 非数值
                {"value": 1},                                 # 缺 metric
                "not-a-dict",                                  # 非对象
                {"metric": "spo2", "value": 97},               # 合法
            ],
        }
        result = self.adapter.parse(frame)
        self.assertEqual(len(result.readings), 1)
        self.assertEqual(result.readings[0].data_type, "spo2")
        self.assertEqual(len(result.errors), 3)

    def test_battery_level_optional_and_typed(self):
        ok = self.adapter.parse({**VALID_FRAME, "battery_level": 85})
        self.assertEqual(ok.battery_level, 85.0)
        bad = self.adapter.parse({**VALID_FRAME, "battery_level": "85%"})
        self.assertIsNone(bad.battery_level)
        self.assertTrue(any("battery_level" in e for e in bad.errors))
        # 布尔不是合法电量
        booly = self.adapter.parse({**VALID_FRAME, "battery_level": True})
        self.assertIsNone(booly.battery_level)

    def test_non_dict_payload_is_error(self):
        result = self.adapter.parse("raw-bytes")
        self.assertFalse(result.ok)

    def test_protocol_assumptions_complete_and_actionable(self):
        # T74 验收：假设逐条含核实方式，集中可替换
        self.assertGreaterEqual(len(JMD540_PROTOCOL_ASSUMPTIONS), 6)
        self.assertEqual(
            self.adapter.describe_assumptions(),
            [a.to_dict() for a in self.adapter.protocol_assumptions])
        for assumption in JMD540_PROTOCOL_ASSUMPTIONS:
            self.assertTrue(assumption.claim)
            self.assertTrue(assumption.verify)


class ProtocolRegistryTests(unittest.TestCase):
    def test_jmd540_resolved_with_normalization(self):
        self.assertIsInstance(get_protocol_adapter("JMD-540"), JMD540Adapter)
        self.assertIsInstance(get_protocol_adapter("jmd 540"), JMD540Adapter)

    def test_unknown_model_returns_none(self):
        self.assertIsNone(get_protocol_adapter("未知型号"))
        self.assertIsNone(get_protocol_adapter(None))

    def test_register_and_resolve_custom_adapter(self):
        class DemoAdapter(DeviceProtocolAdapter):
            adapter_id = "demo"

            def parse(self, raw):
                from app.services.device_protocol.base import AdapterParseResult
                return AdapterParseResult()

        register_protocol_adapter("DEMO-X", DemoAdapter())
        self.assertIsInstance(get_protocol_adapter("demo-x"), DemoAdapter)


class JMD540SimulatedReplayerTests(unittest.TestCase):
    def setUp(self):
        self.replayer = JMD540SimulatedReplayer()
        self.base = datetime(2026, 11, 15, 8, 0, 0)

    def test_replay_is_deterministic_no_randomness(self):
        # REM02：回放输出完全确定（同参数 → 同结果），无随机源
        a = self.replayer.replay(frame_count=4, base_time=self.base)
        b = self.replayer.replay(frame_count=4, base_time=self.base)
        self.assertEqual(
            [(r.data_type, r.value, r.timestamp) for f in a for r in f.readings],
            [(r.data_type, r.value, r.timestamp) for f in b for r in f.readings])

    def test_frames_advance_by_interval(self):
        frames = self.replayer.replay(frame_count=3, base_time=self.base)
        times = [f.readings[0].timestamp for f in frames]
        self.assertEqual(times[1] - times[0], timedelta(seconds=60))
        self.assertEqual(times[2] - times[1], timedelta(seconds=60))

    def test_every_reading_forcefully_marked_simulated(self):
        frames = self.replayer.replay(frame_count=4, base_time=self.base)
        for frame in frames:
            for reading in frame.readings:
                self.assertTrue(reading.metadata.get("simulated"))
                self.assertEqual(
                    reading.metadata.get("simulated_replay"),
                    "SIMULATED_REPLAY")

    def test_replayed_frames_parse_cleanly(self):
        for frame in self.replayer.replay(frame_count=4, base_time=self.base):
            self.assertTrue(frame.ok, frame.errors)

    def test_device_sn_override(self):
        frames = self.replayer.replay(frame_count=1, base_time=self.base,
                                      device_sn="SN-REAL-1")
        self.assertEqual(frames[0].device_sn, "SN-REAL-1")

    def test_frame_count_bounds(self):
        with self.assertRaises(ValueError):
            self.replayer.replay(frame_count=0)
        with self.assertRaises(ValueError):
            self.replayer.replay(frame_count=501)


if __name__ == "__main__":
    unittest.main()

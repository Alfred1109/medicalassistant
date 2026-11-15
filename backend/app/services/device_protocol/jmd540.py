"""JMD-540 协议适配器骨架 + 确定性模拟数据回放器（T74）

═══════════════════════════════════════════════════════════════════
⚠ 协议假设集中声明（待厂商文档核实后单点替换 parse 实现）
═══════════════════════════════════════════════════════════════════

核实背景（docs/device-sdk-assessment-2026-11-07.md）：
- 仓库根目录 `Joeme Fit SDK 260611.rar` 为 Veepoo（Joeme Fit）Android BLE
  SDK（vpprotocol-2.3.68.15.aar / vpbluetooth-1.20.aar）+ iOS framework，
  未找到 JMD-540 明确型号映射、专用密码或能力配置；无浏览器/Python 可用
  SDK 或厂商云 REST API。
- 因此本适配器按「通用康复评估设备、周期性测量数据」假设设计，真实链路
  预期为：JMD-540 → Android BLE 采集端（Veepoo SDK）→ 本系统 HTTP 网关。
- 实机到位后需核实：扫描名称、设备/固件信息、密码验证流程、能力回调
  （评估文档 §已发现的SDK和实际边界）。届时替换本文件 parse/_FRAME
  即可，网关、质量管道、分析链零改动。

全部协议字段假设见 JMD540_PROTOCOL_ASSUMPTIONS（逐条含核实方式）。

模拟回放器说明（REM02 红线）：
- JMD540SimulatedReplayer 输出完全确定性（无 random），帧值来自固定
  常量表 JMD540_SIMULATED_FRAMES，仅用于测试与演示链路；
- 每帧强制携带 {"simulated": true}，入库 metadata.source 为
  "automated_simulated_replay"，任何展示/分析侧都可识别，绝不冒充
  真实设备采集。
"""
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from .base import (
    AdapterParseResult,
    DeviceProtocolAdapter,
    ProtocolAssumption,
    StandardReading,
)

#: JMD-540 支持的指标假设集合（通用康复评估指标；实际以设备能力回调/厂商
#: 文档核实为准，SDK 归档中部分 HRV/呼吸率/ECG 能力需商务授权）。
JMD540_METRICS: Dict[str, str] = {
    "heart_rate": "bpm",
    "spo2": "%",
    "systolic_pressure": "mmHg",
    "diastolic_pressure": "mmHg",
    "body_temperature": "℃",
    "respiration_rate": "次/分",
}

JMD540_PROTOCOL_ASSUMPTIONS: List[ProtocolAssumption] = [
    ProtocolAssumption(
        claim="上报通道假设：设备数据经 Android BLE 采集端（Veepoo SDK）以 "
              "HTTP JSON POST 推送到本系统网关，而非设备直连或厂商云推送",
        verify="向厂商确认 JMD-540 是否具备 Wi-Fi/蜂窝直连能力；实机验证 "
               "Android 采集端上报链路",
        impact="网关端点形态（HTTP JSON）；若为云推送需增加回调验签",
    ),
    ProtocolAssumption(
        claim="帧结构假设：{\"device_sn\": str, \"measured_at\": ISO8601, "
              "\"metrics\": [{\"metric\": str, \"value\": number, "
              "\"unit\": str(可选)}], \"battery_level\": number(可选)}",
        verify="厂商协议文档；或实机在采集端记录原始载荷",
        impact="parse 实现整体替换；标准化读数三字段（metric/value/unit）"
               "映射关系重排",
    ),
    ProtocolAssumption(
        claim="时间戳假设：measured_at 为设备测量的 UTC ISO8601 时间"
              "（含时区标记）；无时区标记按 UTC 处理",
        verify="实机核对设备时区与时钟偏差（评估文档要求覆盖原始时间与时区）",
        impact="时间戳合理性校验阈值与会话窗口归属",
    ),
    ProtocolAssumption(
        claim="指标名假设：metric ∈ JMD540_METRICS（心率/血氧/血压/体温/"
              "呼吸率），未登记指标入库时标记 unregistered_metric 不丢弃",
        verify="实机记录能力回调 + 厂商指标字典；确认哪些指标需商务授权",
        impact="质量管道指标范围表与前端展示标签",
    ),
    ProtocolAssumption(
        claim="单位假设：指标单位随帧上报（unit 可选），缺省时以 "
              "JMD540_METRICS 默认单位补齐",
        verify="厂商文档单位表；实机比对设备原始读数（评估文档验收项）",
        impact="unit 归一化逻辑",
    ),
    ProtocolAssumption(
        claim="设备标识假设：device_sn 对应系统 devices.device_id 字段"
              "（设备登记时的序列号），battery_level 可随帧上报",
        verify="实机读取设备序列号并与登记流程核对",
        impact="网关设备寻址与鉴权绑定方式",
    ),
    ProtocolAssumption(
        claim="凭证机制假设：过渡期采用静态 device_key（网关侧生成、设备"
              "侧保存的共享密钥）；厂商若有正式鉴权方案（如 token/证书）"
              "则替换",
        verify="厂商安全方案文档；商务确认",
        impact="gateway 鉴权依赖与凭证轮换端点",
    ),
]

#: 时间戳解析容错格式（ISO8601 主格式；Z 后缀归一化为 +00:00）


class JMD540Adapter(DeviceProtocolAdapter):
    """JMD-540 适配器骨架。

    parse 实现按上述假设的 JSON 帧结构解析；结构损坏逐条进 errors，
    不抛中断。协议文档到位后仅需重写本类。
    """

    adapter_id = "jmd540"
    protocol_assumptions = JMD540_PROTOCOL_ASSUMPTIONS
    metrics = JMD540_METRICS

    def parse(self, raw: Dict[str, Any]) -> AdapterParseResult:
        result = AdapterParseResult()
        if not isinstance(raw, dict):
            result.errors.append("帧载荷不是 JSON 对象")
            return result

        result.device_sn = raw.get("device_sn") if isinstance(
            raw.get("device_sn"), str) else None
        if not result.device_sn:
            result.errors.append("缺少 device_sn（设备序列号）字段")

        battery = raw.get("battery_level")
        if isinstance(battery, (int, float)) and not isinstance(battery, bool):
            result.battery_level = float(battery)
        elif battery is not None:
            result.errors.append("battery_level 非数值，忽略")

        measured_at = raw.get("measured_at")
        frame_time = self._parse_timestamp(measured_at)
        if frame_time is None:
            result.errors.append(
                f"measured_at 缺失或不是可解析时间（值={measured_at!r}）")
            # 时间不可解析时不产出读数（timestamp 是标准化读数必填项）
            return result

        metrics = raw.get("metrics")
        if not isinstance(metrics, list):
            result.errors.append("metrics 缺失或不是数组")
            return result
        if not metrics:
            # 无读数的帧视为心跳帧（握手/心跳可选接口的默认语义）
            result.is_heartbeat = True
            return result

        for i, entry in enumerate(metrics):
            error = self._parse_metric_entry(i, entry, frame_time, result)
            if error:
                result.errors.append(error)
        return result

    def _parse_metric_entry(
        self, index: int, entry: Any, frame_time: datetime,
        result: AdapterParseResult) -> Optional[str]:
        """解析单条指标；失败返回错误描述，成功产出 StandardReading。"""
        if not isinstance(entry, dict):
            return f"metrics[{index}] 不是对象"
        metric = entry.get("metric")
        if not isinstance(metric, str) or not metric:
            return f"metrics[{index}] 缺少 metric 名称"
        value = entry.get("value")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return f"metrics[{index}]({metric}) value 非数值"
        unit = entry.get("unit")
        if not isinstance(unit, str) or not unit:
            unit = self.metrics.get(metric, "")  # 假设：缺省单位按指标表补齐
        timestamp = frame_time
        # 假设：允许条目级 measured_at 覆盖帧级时间（多指标不同步测量）
        entry_time = self._parse_timestamp(entry.get("measured_at"))
        if entry_time is not None:
            timestamp = entry_time
        result.readings.append(StandardReading(
            data_type=metric,
            value=float(value),
            unit=unit,
            timestamp=timestamp,
            metadata={"adapter_id": self.adapter_id},
        ))
        return None

    @staticmethod
    def _parse_timestamp(value: Any) -> Optional[datetime]:
        if isinstance(value, datetime):
            parsed = value
        elif isinstance(value, str) and value:
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return None
        else:
            return None
        # 假设：上报时间戳含时区标记按 UTC 处理；适配器统一输出 naive UTC，
        # 网关/质量管道/入库口径一致（协议假设条目 3）
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(
                __import__("datetime").timezone.utc).replace(tzinfo=None)
        return parsed


# ── 确定性模拟回放器（仅测试/演示）─────────────────────────────────────
# 固定帧常量：无任何随机源（REM02），数值为合理生理范围内的固定序列。
JMD540_SIMULATED_FRAMES: List[Dict[str, Any]] = [
    {
        "device_sn": "JMD-540-SIMULATED",
        "metrics": [
            {"metric": "heart_rate", "value": 72, "unit": "bpm"},
            {"metric": "spo2", "value": 97, "unit": "%"},
        ],
    },
    {
        "device_sn": "JMD-540-SIMULATED",
        "metrics": [
            {"metric": "heart_rate", "value": 76, "unit": "bpm"},
            {"metric": "spo2", "value": 96, "unit": "%"},
        ],
    },
    {
        "device_sn": "JMD-540-SIMULATED",
        "metrics": [
            {"metric": "heart_rate", "value": 74, "unit": "bpm"},
            {"metric": "spo2", "value": 98, "unit": "%"},
        ],
    },
    {
        "device_sn": "JMD-540-SIMULATED",
        "metrics": [
            {"metric": "systolic_pressure", "value": 118, "unit": "mmHg"},
            {"metric": "diastolic_pressure", "value": 76, "unit": "mmHg"},
        ],
    },
]


class JMD540SimulatedReplayer:
    """JMD-540 模拟数据回放器：把固定帧序列经适配器产出标准化读数。

    用途：硬件未到位期间的测试与端到端演示。回放帧强制注入
    {"simulated": true} 标记，网关入库时 metadata.source 记为
    "automated_simulated_replay"，前端与分析侧均可识别。

    回放帧的 measured_at 以 base_time 为基准逐帧递进（frame_interval
    秒/帧），保证会话窗口归属合理；base_time 可注入以便测试确定性。
    """

    adapter_id = "jmd540-simulated"
    simulated_marker = "SIMULATED_REPLAY"

    def __init__(self, adapter: Optional[JMD540Adapter] = None,
                 frame_interval_seconds: int = 60):
        self.adapter = adapter or JMD540Adapter()
        self.frame_interval_seconds = frame_interval_seconds

    def replay(
        self, frame_count: int = 4, base_time: Optional[datetime] = None,
        device_sn: Optional[str] = None,
    ) -> List[AdapterParseResult]:
        """回放 frame_count 帧（循环取固定帧表），返回逐帧解析结果。

        帧时间 = base_time + i * frame_interval（最早帧最旧，符合
        时序上报习惯）；base_time 缺省为当前 UTC 时间回退整个窗口。
        """
        if frame_count < 1 or frame_count > 500:
            raise ValueError("frame_count 必须在 1..500 之间")
        if base_time is None:
            base_time = datetime.utcnow() - timedelta(
                seconds=self.frame_interval_seconds * (frame_count - 1))
        frames: List[AdapterParseResult] = []
        for i in range(frame_count):
            template = JMD540_SIMULATED_FRAMES[i % len(JMD540_SIMULATED_FRAMES)]
            frame: Dict[str, Any] = {
                "device_sn": device_sn or template["device_sn"],
                "measured_at": (
                    base_time + timedelta(
                        seconds=self.frame_interval_seconds * i)
                ).isoformat() + "Z",
                "metrics": [dict(m) for m in template["metrics"]],
                "simulated": True,  # 强制模拟标记，随帧入库留痕
            }
            parsed = self.adapter.parse(frame)
            for reading in parsed.readings:
                reading.metadata["simulated"] = True
                reading.metadata["simulated_replay"] = self.simulated_marker
            frames.append(parsed)
        return frames

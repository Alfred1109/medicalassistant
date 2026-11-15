"""设备协议适配器包（T74 真实设备接入软件侧框架）

设计目标：厂商协议文档未到位期间，以「可替换适配器 + 模拟数据回放」
策略搭好软件侧链路，不空等硬件：

    设备(采集端) → 接入网关(device_router /device_ingestion_service)
        → DeviceProtocolAdapter.parse → 标准化读数
        → 质量校验管道(device_ingestion_service) → device_data
        → 既有分析/预警链(device_analysis_service，不重造)

子模块：
- base    适配器抽象接口 + 标准化读数/解析结果结构
- jmd540  JMD-540 适配器骨架（协议字段假设清单集中于此）+
          确定性模拟数据回放器（仅测试/演示，标记 simulated，绝不冒充真实采集）

与 device_adapters.py 的关系：device_adapters 是旧的服务端主动"拉取同步"
抽象（sync_data，真实源未接入时如实拒绝，保留不动）；本包是设备侧主动
"推送上报"的协议解析抽象（parse 收到的即设备发来的原始载荷），两者职责
不同、互不替代。
"""
from .base import (
    DeviceProtocolAdapter,
    AdapterParseResult,
    ProtocolParseError,
    StandardReading,
)
from .jmd540 import (
    JMD540Adapter,
    JMD540_PROTOCOL_ASSUMPTIONS,
    JMD540SimulatedReplayer,
    JMD540_SIMULATED_FRAMES,
)
from .registry import get_protocol_adapter, register_protocol_adapter

__all__ = [
    "DeviceProtocolAdapter",
    "AdapterParseResult",
    "ProtocolParseError",
    "StandardReading",
    "JMD540Adapter",
    "JMD540_PROTOCOL_ASSUMPTIONS",
    "JMD540SimulatedReplayer",
    "JMD540_SIMULATED_FRAMES",
    "get_protocol_adapter",
    "register_protocol_adapter",
]

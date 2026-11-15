"""设备协议适配器抽象接口（T74）

适配器职责：把某型号设备采集端发来的「原始上报载荷」解析为标准化读数
（时间戳 + 指标名 + 数值 + 单位），不负责质量校验（质量校验在
device_ingestion_service 的统一管道做，与厂商无关）。

协议假设管理约定（T74 验收要求）：所有未经厂商文档核实的字段假设，
必须以 ProtocolAssumption 条目集中在各适配器的 protocol_assumptions
类属性中，逐条注明「假设内容 / 核实方式」；拿到厂商文档后单点替换
对应适配器的 parse 实现，网关与质量管道不动。
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


class ProtocolParseError(Exception):
    """适配器解析原始载荷失败（畸形报文）。"""


@dataclass
class ProtocolAssumption:
    """一条待核实的协议字段假设。

    - claim: 假设内容（协议字段/格式/语义）；
    - verify: 核实方式（厂商文档 / 实机抓包 / 商务确认）；
    - impact: 假设不成立时的影响面（便于评估替换成本）。
    """
    claim: str
    verify: str
    impact: str = ""

    def to_dict(self) -> Dict[str, str]:
        return {
            "claim": self.claim,
            "verify": self.verify,
            "impact": self.impact,
        }


@dataclass
class StandardReading:
    """标准化读数：设备无关的统一形态，对齐 device_data 文档字段。

    metadata 携带来源与回放标记（source=automated / simulated=True 等），
    由网关在入库时合并补充（adapter_id、raw payload 留存等）。
    """
    data_type: str
    value: float
    unit: str
    timestamp: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "data_type": self.data_type,
            "value": self.value,
            "unit": self.unit,
            "timestamp": self.timestamp,
            "metadata": dict(self.metadata),
        }


@dataclass
class AdapterParseResult:
    """一帧原始载荷的解析结果。

    - readings: 解析成功的标准化读数；
    - errors: 本帧内解析失败的条目描述（字段级，不抛中断整帧）；
    - device_sn: 报文声明的设备序列号（与 devices.device_id 比对）；
    - battery_level: 报文自带的电量（可选；无真实上报路径时保持 None，
      不虚构——与 device_adapters 去模拟化口径一致）；
    - is_heartbeat: 纯心跳帧（无读数）。
    """
    readings: List[StandardReading] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    device_sn: Optional[str] = None
    battery_level: Optional[float] = None
    is_heartbeat: bool = False

    @property
    def ok(self) -> bool:
        return not self.errors


class DeviceProtocolAdapter(ABC):
    """设备协议适配器抽象。

    一个适配器对应一种设备型号/协议族。网关按设备型号选择适配器
    （见 registry.get_protocol_adapter），未登记型号走通用 JSON 适配器。
    """

    #: 适配器标识（入库 metadata.adapter_id，便于追溯解析实现版本）
    adapter_id: str = "base"

    #: 协议假设清单（待厂商文档核实；逐条注明核实方式）
    protocol_assumptions: List[ProtocolAssumption] = []

    def describe_assumptions(self) -> List[Dict[str, str]]:
        """协议假设清单（前端/核实清单透出用）。"""
        return [a.to_dict() for a in self.protocol_assumptions]

    @abstractmethod
    def parse(self, raw: Dict[str, Any]) -> AdapterParseResult:
        """解析一帧原始上报载荷为标准化读数。

        契约：畸形载荷不抛 ProtocolParseError 到网关——把逐条错误放进
        result.errors（网关对整帧结构损坏才需要短路时自行判断）；
        数值范围/时间戳合理性不在本层判断（统一质量管道负责）。
        """
        raise NotImplementedError

    def validate(self, raw: Dict[str, Any]) -> List[str]:
        """轻量结构校验（不入库前的网关预检），返回错误列表。"""
        return self.parse(raw).errors

    async def handshake(self, raw: Dict[str, Any]) -> AdapterParseResult:
        """可选的设备握手（首连鉴别）。默认按普通上报帧解析。"""
        return self.parse(raw)

    async def heartbeat(self, raw: Dict[str, Any]) -> AdapterParseResult:
        """可选的设备心跳处理。默认按普通上报帧解析。"""
        return self.parse(raw)

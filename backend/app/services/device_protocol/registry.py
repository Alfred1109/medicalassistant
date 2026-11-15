"""适配器注册表：按设备型号/制造商选择协议适配器（T74）

当前仅登记 JMD-540 骨架适配器；其余型号未登记时返回通用
DeviceProtocolAdapter 基类——但基类 parse 未实现，网关会把
未登记型号的上报按"无可用协议适配器"拒绝，不猜格式。
"""
from typing import Dict, Optional

from .base import DeviceProtocolAdapter, ProtocolParseError
from .jmd540 import JMD540Adapter

#: 型号 → 适配器（型号匹配大小写不敏感、忽略连字符/空格差异）
_PROTOCOL_ADAPTERS: Dict[str, DeviceProtocolAdapter] = {}


def _normalize_model(model: str) -> str:
    return (model or "").strip().lower().replace("-", "").replace(" ", "")


def register_protocol_adapter(model: str, adapter: DeviceProtocolAdapter) -> None:
    """登记型号适配器（新型号接入时调用/注册）。"""
    _PROTOCOL_ADAPTERS[_normalize_model(model)] = adapter


register_protocol_adapter("jmd540", JMD540Adapter())


def get_protocol_adapter(model: Optional[str]) -> Optional[DeviceProtocolAdapter]:
    """按设备型号取适配器；未登记型号返回 None（网关如实拒绝）。"""
    if not model:
        return None
    return _PROTOCOL_ADAPTERS.get(_normalize_model(model))


__all__ = ["get_protocol_adapter", "register_protocol_adapter",
           "DeviceProtocolAdapter", "ProtocolParseError"]

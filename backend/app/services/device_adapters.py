"""
设备适配器模块

去模拟化说明（2026-11-09，REM02 红线：无随机数据冒充采集）：
- 原实现的各设备适配器（可穿戴/连续血糖监测/肺活量计/康复训练设备/TENS 等）
  以 random.randint/uniform/choice 随机生成心率、步数、睡眠、血氧、血糖曲线、
  肺功能（FVC/FEV1/PEF）、关节活动度、肌力、电刺激参数与训练执行数据，
  并写入 device_data 集合冒充真实设备采集，已整体移除；
- 设备厂商数据源（设备 SDK / 蓝牙同步 / 厂商云 API）尚未接入
  （评估见 docs/device-sdk-assessment-2026-11-07.md），
  sync_data 一律如实抛出 DeviceDataSourceNotConnected，
  由 device_service.sync_device_data 转为明确的拒绝结果，
  路由层转 503"设备数据源未接入"，不生成任何数据、不更新 last_connected；
- get_status 仅依据设备文档真实存在的 last_connected 字段推导连接状态；
  电量与信号强度在全库无真实写入路径（bind_device 不采集、无任何设备上报），
  如实返回 None（"未上报"），不再随机生成 30-100 电量与 1-5 信号格。
"""
from typing import Dict
from datetime import datetime


class DeviceDataSourceNotConnected(Exception):
    """设备真实数据源未接入（无 SDK / 厂商云 API 对接），无法执行同步。"""

    def __init__(self, device_type: str = ""):
        self.device_type = device_type
        super().__init__("设备数据源未接入，无法同步真实采集数据")


class DeviceAdapter:
    """设备适配器基类

    当前所有设备类型的真实数据源均未接入，基类即唯一诚实实现；
    接入具体设备 SDK 后，再按类型派生并实现真实同步逻辑。
    """

    async def sync_data(self, device: Dict) -> Dict:
        """同步设备数据

        真实设备数据源未接入：如实报错，绝不生成/返回模拟采集数据。
        """
        raise DeviceDataSourceNotConnected(device.get("device_type", ""))

    async def get_status(self, device: Dict) -> Dict:
        """获取设备状态（仅由设备文档真实字段推导）"""
        return self._status_from_document(device)

    @staticmethod
    def _status_from_document(device: Dict) -> Dict:
        """由 last_connected 推导连接状态；电量/信号未上报如实返回 None。

        - 1 小时内有连接记录 → online，24 小时内 → idle，否则 offline；
        - battery_level 仅在库中真实存在时透出（当前无任何写入路径，
          通常为 None）；signal_strength 全库从未存储，恒为 None。
        """
        last_connected = device.get("last_connected")
        status = "offline"

        if last_connected:
            time_diff = (datetime.utcnow() - last_connected).total_seconds()
            if time_diff < 3600:  # 1小时内
                status = "online"
            elif time_diff < 86400:  # 24小时内
                status = "idle"

        return {
            "status": status,
            "battery_level": device.get("battery_level"),
            "signal_strength": None,
            "last_sync_time": last_connected,
        }


# 适配器工厂
def get_device_adapter(device_type: str) -> DeviceAdapter:
    """根据设备类型获取适配器

    各设备类型的真实数据源均未接入，当前统一返回同一诚实适配器；
    保留按类型扩展的工厂形态，接入真实 SDK 后在此登记具体适配器。
    """
    return DeviceAdapter()

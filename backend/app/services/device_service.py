"""
设备服务模块
负责设备管理、数据处理和适配器系统
"""
from datetime import datetime
from typing import Dict, List, Optional, Any, Union
from bson import ObjectId

from ..models.device import Device, DeviceData
from ..models.device_data_standard import DeviceType, DeviceStatus, ConnectionType
from .device_adapters import get_device_adapter
from .device_data_validator_service import device_data_validator_service
from ..db.mongodb import get_db


# ── 设备域角色语义统一（缺陷 B 盘点后收敛）─────────────────────────────────
# 只读路径（查看设备详情/数据/状态/分析/预警/维修记录）：医疗 staff
# doctor / health_manager / admin；健康管理师可查看其负责患者的设备数据。
DEVICE_READ_ROLES = ("doctor", "health_manager", "admin")
# 变更路径（配置/维修等）：设备属主本人或 doctor / admin；
# 健康管理师不可执行变更操作，患者仅可操作自己名下设备。
DEVICE_MUTATE_ROLES = ("doctor", "admin")


class DeviceService:
    """设备服务类，处理设备管理和数据相关功能"""
    
    async def get_user_devices(self, user_id: str) -> List[Dict]:
        """获取用户关联的设备列表"""
        db = await get_db()
        devices = await db.devices.find(
            {"patient_id": user_id, "status": {"$ne": "deleted"}}
        ).to_list(None)
        
        return [{**device, "_id": str(device["_id"])} for device in devices]

    async def list_registered_devices(self) -> List[Dict]:
        """管理员查看已登记设备。没有上报记录时不补造读数。"""
        db = await get_db()
        devices = await db.devices.find({"status": {"$ne": "deleted"}}).to_list(500)
        return [{**device, "_id": str(device["_id"])} for device in devices]
    
    async def get_device(self, device_id: str) -> Optional[Dict]:
        """获取设备详情；畸形 ID 与不存在的设备语义一致，返回 None"""
        if not ObjectId.is_valid(device_id):
            return None
        db = await get_db()
        device = await db.devices.find_one({"_id": ObjectId(device_id)})
        if device:
            device["_id"] = str(device["_id"])
        return device
    
    async def bind_device(self, user_id: str, device_data: Dict) -> Dict:
        """绑定新设备到用户"""
        db = await get_db()
        
        # 验证设备类型和固件版本
        if "device_type" in device_data and device_data["device_type"] not in [d.value for d in DeviceType]:
            return {"error": "不支持的设备类型"}
            
        # 注意：路由层传入 device.dict()，未填的可选字段以 None 出现，
        # 不能用 `"firmware_version" in device_data` 判断是否填写
        firmware_version = device_data.get("firmware_version")
        if firmware_version:
            if not device_data_validator_service.validate_device_firmware(firmware_version):
                return {"error": "固件版本格式不正确，应为x.y.z格式"}
                
        device = {
            "device_id": device_data.get("device_id", str(ObjectId())),
            "device_type": device_data["device_type"],
            "name": device_data["name"],
            "manufacturer": device_data.get("manufacturer"),
            "model": device_data.get("model"),
            "patient_id": user_id,
            "status": "active",
            "connection_type": device_data.get("connection_type"),
            "firmware_version": device_data.get("firmware_version"),
            "settings": device_data.get("settings", {}),
            "last_connected": datetime.utcnow(),
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }
        
        result = await db.devices.insert_one(device)
        device["_id"] = str(result.inserted_id)
        return device
    
    async def unbind_device(self, user_id: str, device_id: str) -> bool:
        """解绑用户设备；畸形 ID 视为设备不存在，返回 False"""
        if not ObjectId.is_valid(device_id):
            return False
        db = await get_db()
        result = await db.devices.update_one(
            {"_id": ObjectId(device_id), "patient_id": user_id},
            {"$set": {"status": "deleted", "updated_at": datetime.utcnow()}}
        )
        return result.modified_count > 0
    
    async def get_device_data(
        self, 
        device_id: str, 
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        data_type: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict]:
        """获取设备数据"""
        db = await get_db()
        query = {"device_id": device_id}
        
        if start_date:
            query["timestamp"] = {"$gte": start_date}
        if end_date:
            if "timestamp" in query:
                query["timestamp"]["$lte"] = end_date
            else:
                query["timestamp"] = {"$lte": end_date}
        if data_type:
            query["data_type"] = data_type
            
        device_data = await db.device_data.find(query).sort(
            "timestamp", -1
        ).limit(limit).to_list(None)
        
        return [{**data, "_id": str(data["_id"])} for data in device_data]
    
    async def sync_device_data(self, device_id: str) -> Dict:
        """同步设备数据

        去模拟化（REM02）：原实现按设备类型选择适配器，随机生成心率/睡眠/
        血糖/肺功能等"采集数据"写入 device_data 集合，并更新 last_connected
        伪装连接成功。设备真实数据源（SDK/厂商云）尚未接入，此处如实拒绝，
        不生成任何数据、不更新 last_connected（未发生真实连接）。
        """
        device = await self.get_device(device_id)
        if not device:
            return {"success": False, "message": "设备不存在"}

        return {"success": False, "message": "设备数据源未接入，无法同步真实采集数据"}

    async def record_manual_reading(self, device_id: str, data_type: str, value: str, unit: str, measured_at: datetime) -> Dict:
        """Store a reading a person typed. It is not a device upload and does not change battery or connection time."""
        db = await get_db()
        document = {
            "_id": ObjectId(),
            "device_id": device_id,
            "timestamp": measured_at,
            "data_type": data_type,
            "value": value,
            "unit": unit,
            "metadata": {"source": "手工登记"},
            "created_at": datetime.utcnow(),
        }
        await db.device_data.insert_one(document)
        document["id"] = str(document.pop("_id"))
        return document
    
    async def get_device_status(self, device_id: str) -> Dict:
        """获取设备状态

        去模拟化：状态仅由设备文档真实字段（last_connected）推导，
        电量/信号强度全库无真实上报，如实透出 None（未上报），
        不再随机生成电量与信号格数。
        """
        device = await self.get_device(device_id)
        if not device:
            return {
                "status": "error",
                "message": "设备不存在",
                "battery_level": None,
                "signal_strength": None,
                "last_sync_time": None
            }

        # 根据设备类型选择适配器
        adapter = get_device_adapter(device["device_type"])

        # 使用适配器获取状态
        try:
            status = await adapter.get_status(device)
            return status
        except Exception as e:
            return {
                "status": "error",
                "message": f"获取状态失败: {str(e)}",
                "battery_level": None,
                "signal_strength": None,
                "last_sync_time": device.get("last_connected")
            }
    
    async def configure_device(self, device_id: str, config: Dict) -> Dict:
        """配置设备"""
        device = await self.get_device(device_id)
        if not device:
            return {"success": False, "message": "设备不存在"}
        
        # 更新设备配置
        db = await get_db()
        update_data = {
            "settings": {**device.get("settings", {}), **config},
            "updated_at": datetime.utcnow()
        }
        
        result = await db.devices.update_one(
            {"_id": ObjectId(device_id)},
            {"$set": update_data}
        )
        
        if result.modified_count > 0:
            return {"success": True, "message": "设备配置已更新"}
        else:
            return {"success": False, "message": "设备配置更新失败"}
    
    async def get_supported_data_types(self, device_type: Optional[str] = None) -> Dict:
        """
        获取支持的数据类型
        
        参数:
        - device_type: 可选的设备类型
        
        返回:
        - 数据类型列表
        """
        if device_type:
            return device_data_validator_service.get_supported_data_types_for_device(device_type)
        else:
            # 返回所有设备类型
            all_types = []
            for device_enum in DeviceType:
                device_data_types = device_data_validator_service.get_supported_data_types_for_device(device_enum.value)
                all_types.append({
                    "device_type": device_enum.value,
                    "data_types": device_data_types
                })
            return all_types
    
    async def get_device_repair_history(
        self, 
        device_id: Optional[str] = None, 
        limit: int = 20
    ) -> List[Dict]:
        """
        获取设备修复历史
        
        参数:
        - device_id: 可选的设备ID，如果提供则只返回特定设备的修复历史
        - limit: 返回的记录数量限制
        
        返回:
        - 修复历史记录列表
        """
        db = await get_db()
        query = {}
        if device_id:
            query["device_id"] = device_id
            
        repair_logs = await db.device_repair_logs.find(query).sort(
            "repair_time", -1
        ).limit(limit).to_list(None)
        
        # 转换ObjectId为字符串
        for log in repair_logs:
            if "_id" in log:
                log["_id"] = str(log["_id"])
                
        return repair_logs
    
    async def get_devices_by_type(self, device_type: str) -> List[Dict]:
        """
        获取特定类型的所有设备
        
        参数:
        - device_type: 设备类型
        
        返回:
        - 设备列表
        """
        db = await get_db()
        devices = await db.devices.find(
            {"device_type": device_type, "status": {"$ne": "deleted"}}
        ).to_list(None)
        
        return [{**device, "_id": str(device["_id"])} for device in devices]
    
    async def update_device_firmware(
        self, 
        device_id: str, 
        new_firmware_version: str
    ) -> Dict:
        """
        更新设备固件版本
        
        参数:
        - device_id: 设备ID
        - new_firmware_version: 新固件版本
        
        返回:
        - 更新结果
        """
        # 验证固件版本格式
        if not device_data_validator_service.validate_device_firmware(new_firmware_version):
            return {"success": False, "message": "固件版本格式不正确，应为x.y.z格式"}
            
        device = await self.get_device(device_id)
        if not device:
            return {"success": False, "message": "设备不存在"}
            
        # 更新固件版本
        db = await get_db()
        result = await db.devices.update_one(
            {"_id": ObjectId(device_id)},
            {"$set": {
                "firmware_version": new_firmware_version,
                "firmware_update_available": False,
                "updated_at": datetime.utcnow()
            }}
        )
        
        if result.modified_count > 0:
            return {"success": True, "message": "设备固件版本已更新"}
        else:
            return {"success": False, "message": "设备固件更新失败"}


device_service = DeviceService() 
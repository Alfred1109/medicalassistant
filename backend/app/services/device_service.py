"""
设备服务模块
负责设备管理、数据处理和适配器系统
"""
from datetime import datetime
from typing import Dict, List, Optional, Any, Union
from bson import ObjectId

from ..models.device import Device, DeviceData
from ..models.device_data_standard import DeviceType, DeviceStatus, ConnectionType
from ..models.device_repair_log import DeviceRepairLog
from .device_adapters import get_device_adapter
from .device_data_validator_service import device_data_validator_service
from ..db.mongodb import get_db


class DeviceService:
    """设备服务类，处理设备管理和数据相关功能"""
    
    async def get_user_devices(self, user_id: str) -> List[Dict]:
        """获取用户关联的设备列表"""
        db = await get_db()
        devices = await db.devices.find(
            {"patient_id": user_id, "status": {"$ne": "deleted"}}
        ).to_list(None)
        
        return [{**device, "_id": str(device["_id"])} for device in devices]
    
    async def get_device(self, device_id: str) -> Dict:
        """获取设备详情"""
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
            
        if "firmware_version" in device_data:
            if not device_data_validator_service.validate_device_firmware(device_data["firmware_version"]):
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
        """解绑用户设备"""
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
        """同步设备数据"""
        # 先获取设备信息
        device = await self.get_device(device_id)
        if not device:
            return {"success": False, "message": "设备不存在"}
        
        # 根据设备类型选择适配器
        adapter = get_device_adapter(device["device_type"])
        
        # 使用适配器同步数据
        try:
            sync_result = await adapter.sync_data(device)
            
            # 更新设备最后连接时间
            db = await get_db()
            await db.devices.update_one(
                {"_id": ObjectId(device_id)},
                {"$set": {
                    "last_connected": datetime.utcnow(),
                    "updated_at": datetime.utcnow()
                }}
            )
            
            return sync_result
        except Exception as e:
            return {"success": False, "message": f"同步失败: {str(e)}"}
    
    async def get_device_status(self, device_id: str) -> Dict:
        """获取设备状态"""
        device = await self.get_device(device_id)
        if not device:
            return {
                "status": "error", 
                "message": "设备不存在",
                "battery_level": 0,
                "signal_strength": 0,
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
                "battery_level": 0,
                "signal_strength": 0,
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
    
    async def auto_repair_device(self, device_id: str) -> Dict:
        """
        尝试自动修复设备状态异常
        
        参数:
        - device_id: 设备ID
        
        返回:
        - 修复结果，包含成功状态和消息
        """
        # 获取设备信息
        device = await self.get_device(device_id)
        if not device:
            return {"success": False, "message": "设备不存在"}
        
        # 获取当前设备状态
        current_status = await self.get_device_status(device_id)
        
        # 根据状态类型进行不同的修复操作
        repair_actions = []
        repair_results = []
        
        # 检查设备状态
        if current_status.get("status") in ["error", "offline", "unknown"]:
            repair_actions.append("重置设备连接")
            
            # 模拟重置设备连接
            try:
                # 获取设备适配器
                adapter = get_device_adapter(device["device_type"])
                # 执行重置操作（实际环境中调用设备SDK的重置方法）
                repair_results.append({"action": "重置设备连接", "success": True})
                
                # 更新设备状态
                db = await get_db()
                await db.devices.update_one(
                    {"_id": ObjectId(device_id)},
                    {"$set": {
                        "status": "active",
                        "last_connected": datetime.utcnow(),
                        "updated_at": datetime.utcnow()
                    }}
                )
            except Exception as e:
                repair_results.append({"action": "重置设备连接", "success": False, "reason": str(e)})
        
        # 检查是否需要固件更新
        if device.get("firmware_update_available"):
            repair_actions.append("固件更新")
            
            # 模拟固件更新（实际环境中调用设备SDK的固件更新方法）
            try:
                # 更新固件状态
                db = await get_db()
                await db.devices.update_one(
                    {"_id": ObjectId(device_id)},
                    {"$set": {
                        "firmware_update_available": False,
                        "firmware_version": f"{device.get('firmware_version', '1.0')}.1",  # 模拟版本增加
                        "updated_at": datetime.utcnow()
                    }}
                )
                repair_results.append({"action": "固件更新", "success": True})
            except Exception as e:
                repair_results.append({"action": "固件更新", "success": False, "reason": str(e)})
        
        # 检查电池状态（如果电池过低）
        if current_status.get("battery_level", 0) < 20:
            repair_actions.append("电池状态检查")
            repair_results.append({
                "action": "电池状态检查", 
                "success": True, 
                "message": "已提醒用户充电"
            })
            
            # 在实际应用中，这里可以发送提醒消息给用户
        
        # 检查信号强度（如果信号弱）
        if current_status.get("signal_strength", 0) < 2:
            repair_actions.append("信号强度检查")
            repair_results.append({
                "action": "信号强度检查", 
            "success": True,
                "message": "已建议用户调整设备位置"
            })
        
        # 如果没有执行任何修复操作
        if not repair_actions:
            return {"success": True, "message": "设备状态正常，无需修复"}
        
        # 生成修复报告
        success_count = sum(1 for result in repair_results if result.get("success"))
        
        if success_count == len(repair_actions):
            overall_success = True
            message = "设备修复成功"
        elif success_count > 0:
            overall_success = True
            message = "设备部分修复成功"
        else:
            overall_success = False
            message = "设备修复失败"
        
        # 记录修复操作日志
        repair_log = DeviceRepairLog(
            device_id=device_id,
            device_type=device["device_type"],
            repair_time=datetime.utcnow(),
            initial_status=current_status,
            repair_actions=repair_actions,
            repair_results=repair_results,
            overall_success=overall_success
        )
        
        # 存储修复日志
        try:
            db = await get_db()
            await db.device_repair_logs.insert_one(repair_log.to_mongo())
        except Exception as e:
            print(f"保存修复日志失败: {e}")
        
        # 返回修复结果
        return {
            "success": overall_success,
            "message": message,
            "device_id": device_id,
            "device_type": device["device_type"],
            "repair_actions": repair_actions,
            "repair_results": repair_results,
            "new_status": await self.get_device_status(device_id)
        }
    
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
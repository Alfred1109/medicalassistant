"""
设备服务模块
负责设备管理、数据处理和适配器系统
"""
from datetime import datetime
from typing import Dict, List, Optional, Any, Union
from bson import ObjectId

from ..models.device import Device, DeviceData
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
        adapter = self.get_device_adapter(device["device_type"])
        if not adapter:
            return {"success": False, "message": "不支持的设备类型"}
        
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
        adapter = self.get_device_adapter(device["device_type"])
        if not adapter:
            return {
                "status": "error", 
                "message": "不支持的设备类型",
                "battery_level": 0,
                "signal_strength": 0,
                "last_sync_time": device.get("last_connected")
            }
        
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
    
    def get_device_adapter(self, device_type: str) -> Optional["DeviceAdapter"]:
        """根据设备类型获取适配器"""
        adapter_map = {
            "血压计": BloodPressureAdapter(),
            "血糖仪": GlucoseMeterAdapter(),
            "体温计": ThermometerAdapter(),
            "心电图": ECGAdapter(),
            "体重秤": ScaleAdapter(),
            "手环": WearableAdapter(),
        }
        
        return adapter_map.get(device_type, GenericAdapter())


class DeviceAdapter:
    """设备适配器基类"""
    
    async def sync_data(self, device: Dict) -> Dict:
        """同步设备数据"""
        raise NotImplementedError("子类必须实现此方法")
    
    async def get_status(self, device: Dict) -> Dict:
        """获取设备状态"""
        raise NotImplementedError("子类必须实现此方法")
    
    async def save_device_data(self, device_id: str, data_list: List[Dict]) -> List[str]:
        """保存设备数据到数据库"""
        if not data_list:
            return []
            
        db = await get_db()
        
        # 准备数据
        device_data = []
        for data in data_list:
            if "timestamp" not in data:
                data["timestamp"] = datetime.utcnow()
                
            device_data.append({
                "device_id": device_id,
                "timestamp": data["timestamp"],
                "data_type": data["data_type"],
                "value": data["value"],
                "unit": data.get("unit", ""),
                "metadata": data.get("metadata", {}),
                "created_at": datetime.utcnow()
            })
        
        # 批量插入
        result = await db.device_data.insert_many(device_data)
        return [str(id) for id in result.inserted_ids]


class GenericAdapter(DeviceAdapter):
    """通用设备适配器，用于不支持的设备类型"""
    
    async def sync_data(self, device: Dict) -> Dict:
        """同步设备数据"""
        return {
            "success": False,
            "message": "此设备类型暂不支持自动同步",
            "new_data": []
        }
    
    async def get_status(self, device: Dict) -> Dict:
        """获取设备状态"""
        return {
            "status": "unknown",
            "battery_level": 0,
            "signal_strength": 0,
            "last_sync_time": device.get("last_connected")
        }


class BloodPressureAdapter(DeviceAdapter):
    """血压计适配器"""
    
    async def sync_data(self, device: Dict) -> Dict:
        """同步血压计数据"""
        # 实际项目中，这里应该调用设备SDK或API获取数据
        # 这里使用模拟数据作为示例
        
        # 模拟数据
        import random
        from datetime import timedelta
        
        new_data = []
        timestamp = datetime.utcnow()
        
        # 生成一条血压记录
        systolic = random.randint(110, 140)
        diastolic = random.randint(70, 90)
        pulse = random.randint(60, 100)
        
        # 收缩压
        new_data.append({
            "timestamp": timestamp,
            "data_type": "blood_pressure_systolic",
            "value": systolic,
            "unit": "mmHg",
            "metadata": {"measurement_position": "left_arm"}
        })
        
        # 舒张压
        new_data.append({
            "timestamp": timestamp,
            "data_type": "blood_pressure_diastolic",
            "value": diastolic,
            "unit": "mmHg",
            "metadata": {"measurement_position": "left_arm"}
        })
        
        # 脉搏
        new_data.append({
            "timestamp": timestamp,
            "data_type": "pulse",
            "value": pulse,
            "unit": "bpm",
            "metadata": {}
        })
        
        # 保存到数据库
        saved_ids = await self.save_device_data(str(device["_id"]), new_data)
        
        return {
            "success": True,
            "message": f"成功同步{len(saved_ids)}条血压计数据",
            "new_data": new_data
        }
    
    async def get_status(self, device: Dict) -> Dict:
        """获取血压计状态"""
        # 实际项目中应该通过设备API获取状态
        import random
        
        # 模拟电池电量和信号强度
        battery_level = random.randint(30, 100)
        signal_strength = random.randint(1, 5)
        
        # 根据最后连接时间判断状态
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
            "battery_level": battery_level,
            "signal_strength": signal_strength,
            "last_sync_time": last_connected
        }


# 这里可以继续添加其他设备类型的适配器
class GlucoseMeterAdapter(DeviceAdapter):
    """血糖仪适配器"""
    
    async def sync_data(self, device: Dict) -> Dict:
        """同步血糖仪数据"""
        # 实际项目中，这里应该调用设备SDK或API获取数据
        # 这里使用模拟数据作为示例
        
        # 模拟数据
        import random
        
        new_data = []
        timestamp = datetime.utcnow()
        
        # 生成一条血糖记录
        glucose_value = round(random.uniform(4.0, 10.0), 1)
        
        new_data.append({
            "timestamp": timestamp,
            "data_type": "blood_glucose",
            "value": glucose_value,
            "unit": "mmol/L",
            "metadata": {
                "measurement_time": "fasting" if 4 <= datetime.now().hour <= 9 else "postprandial"
            }
        })
        
        # 保存到数据库
        saved_ids = await self.save_device_data(str(device["_id"]), new_data)
        
        return {
            "success": True,
            "message": f"成功同步{len(saved_ids)}条血糖仪数据",
            "new_data": new_data
        }
    
    async def get_status(self, device: Dict) -> Dict:
        """获取血糖仪状态"""
        # 实际项目中应该通过设备API获取状态
        import random
        
        # 模拟电池电量和信号强度
        battery_level = random.randint(30, 100)
        signal_strength = random.randint(1, 5)
        
        # 根据最后连接时间判断状态
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
            "battery_level": battery_level,
            "signal_strength": signal_strength,
            "last_sync_time": last_connected
        }


class ThermometerAdapter(DeviceAdapter):
    """体温计适配器"""
    
    async def sync_data(self, device: Dict) -> Dict:
        """同步体温计数据"""
        # 实际项目中，这里应该调用设备SDK或API获取数据
        # 这里使用模拟数据作为示例
        
        # 模拟数据
        import random
        
        new_data = []
        timestamp = datetime.utcnow()
        
        # 生成一条体温记录
        temperature = round(36.0 + random.uniform(0.1, 1.5), 1)
        
        new_data.append({
            "timestamp": timestamp,
            "data_type": "body_temperature",
            "value": temperature,
            "unit": "°C",
            "metadata": {
                "measurement_method": random.choice(["oral", "ear", "forehead", "armpit"])
            }
        })
        
        # 保存到数据库
        saved_ids = await self.save_device_data(str(device["_id"]), new_data)
        
        return {
            "success": True,
            "message": f"成功同步{len(saved_ids)}条体温计数据",
            "new_data": new_data
        }
    
    async def get_status(self, device: Dict) -> Dict:
        """获取体温计状态"""
        # 实际项目中应该通过设备API获取状态
        import random
        
        # 模拟电池电量和信号强度
        battery_level = random.randint(30, 100)
        signal_strength = random.randint(1, 5)
        
        # 根据最后连接时间判断状态
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
            "battery_level": battery_level,
            "signal_strength": signal_strength,
            "last_sync_time": last_connected
        }


class ECGAdapter(DeviceAdapter):
    """心电图适配器"""
    
    async def sync_data(self, device: Dict) -> Dict:
        """同步心电图数据"""
        # 实际项目中，这里应该调用设备SDK或API获取数据
        # 心电图数据通常是一段时间内的波形数据
        
        # 模拟数据
        import random
        import numpy as np
        
        new_data = []
        timestamp = datetime.utcnow()
        
        # 模拟一段简单的ECG波形数据（简化版）
        # 实际心电数据要复杂得多
        duration_seconds = 30  # 30秒的心电记录
        sampling_rate = 100  # 100Hz采样率
        num_samples = duration_seconds * sampling_rate
        
        # 生成基础波形（简化的正弦波模拟）
        # 实际心电图数据应使用更复杂的模型
        t = np.linspace(0, duration_seconds, num_samples)
        heart_rate = random.randint(60, 100)  # 每分钟心跳次数
        frequency = heart_rate / 60.0  # 转换为每秒频率
        
        # 创建基础心跳波形
        base_signal = np.sin(2 * np.pi * frequency * t)
        
        # 添加一些变异和噪声
        noise = np.random.normal(0, 0.05, num_samples)
        ecg_signal = base_signal + noise
        
        # 限制数据点数量（实际情况会保存全部数据）
        # 这里为了简化，只保存前10个点
        ecg_sample = ecg_signal[:10].tolist()
        
        new_data.append({
            "timestamp": timestamp,
            "data_type": "ecg_waveform",
            "value": {
                "waveform_sample": ecg_sample,  # 实际应存储完整波形
                "heart_rate": heart_rate,
                "sampling_rate": sampling_rate,
                "duration": duration_seconds
            },
            "unit": "mV",
            "metadata": {
                "device_mode": "continuous",
                "lead_type": "single_lead",
                "filtering": "bandpass"
            }
        })
        
        # 同时记录计算出的心率
        new_data.append({
            "timestamp": timestamp,
            "data_type": "heart_rate",
            "value": heart_rate,
            "unit": "bpm",
            "metadata": {
                "measurement_method": "ecg_derived"
            }
        })
        
        # 保存到数据库
        saved_ids = await self.save_device_data(str(device["_id"]), new_data)
        
        return {
            "success": True,
            "message": f"成功同步{len(saved_ids)}条心电图数据",
            "new_data": new_data
        }
    
    async def get_status(self, device: Dict) -> Dict:
        """获取心电图设备状态"""
        import random
        
        # 模拟电池电量和信号强度
        battery_level = random.randint(30, 100)
        signal_strength = random.randint(1, 5)
        
        # 根据最后连接时间判断状态
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
            "battery_level": battery_level,
            "signal_strength": signal_strength,
            "last_sync_time": last_connected
        }


class ScaleAdapter(DeviceAdapter):
    """体重秤适配器"""
    
    async def sync_data(self, device: Dict) -> Dict:
        """同步体重秤数据"""
        # 实际项目中，这里应该调用设备SDK或API获取数据
        
        # 模拟数据
        import random
        
        new_data = []
        timestamp = datetime.utcnow()
        
        # 生成体重数据
        weight = round(50.0 + random.uniform(0, 40.0), 1)
        
        new_data.append({
            "timestamp": timestamp,
            "data_type": "weight",
            "value": weight,
            "unit": "kg",
            "metadata": {}
        })
        
        # 如果是智能体重秤，还可能提供体脂率等数据
        if random.random() > 0.3:  # 模拟70%的概率提供额外数据
            body_fat = round(15.0 + random.uniform(0, 20.0), 1)
            new_data.append({
                "timestamp": timestamp,
                "data_type": "body_fat_percentage",
                "value": body_fat,
                "unit": "%",
                "metadata": {}
            })
            
            muscle_mass = round(25.0 + random.uniform(0, 30.0), 1)
            new_data.append({
                "timestamp": timestamp,
                "data_type": "muscle_mass",
                "value": muscle_mass,
                "unit": "kg",
                "metadata": {}
            })
            
            water_percentage = round(50.0 + random.uniform(0, 15.0), 1)
            new_data.append({
                "timestamp": timestamp,
                "data_type": "water_percentage",
                "value": water_percentage,
                "unit": "%",
                "metadata": {}
            })
        
        # 保存到数据库
        saved_ids = await self.save_device_data(str(device["_id"]), new_data)
        
        return {
            "success": True,
            "message": f"成功同步{len(saved_ids)}条体重秤数据",
            "new_data": new_data
        }
    
    async def get_status(self, device: Dict) -> Dict:
        """获取体重秤状态"""
        import random
        
        # 模拟电池电量和信号强度
        battery_level = random.randint(30, 100)
        signal_strength = random.randint(1, 5)
        
        # 根据最后连接时间判断状态
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
            "battery_level": battery_level,
            "signal_strength": signal_strength,
            "last_sync_time": last_connected
        }


class WearableAdapter(DeviceAdapter):
    """可穿戴设备适配器（如智能手环、手表）"""
    
    async def sync_data(self, device: Dict) -> Dict:
        """同步可穿戴设备数据"""
        # 实际项目中，这里应该调用设备SDK或API获取数据
        
        # 模拟数据
        import random
        from datetime import timedelta
        
        new_data = []
        timestamp = datetime.utcnow()
        
        # 生成心率数据
        heart_rate = random.randint(60, 110)
        new_data.append({
            "timestamp": timestamp,
            "data_type": "heart_rate",
            "value": heart_rate,
            "unit": "bpm",
            "metadata": {
                "measurement_method": "optical"
            }
        })
        
        # 生成步数数据
        steps = random.randint(1000, 15000)
        new_data.append({
            "timestamp": timestamp,
            "data_type": "steps",
            "value": steps,
            "unit": "steps",
            "metadata": {
                "duration": "daily"
            }
        })
        
        # 生成睡眠数据（过去8小时）
        sleep_start = datetime.utcnow() - timedelta(hours=8)
        deep_sleep = random.randint(90, 240)  # 深度睡眠分钟数
        light_sleep = random.randint(180, 300)  # 浅度睡眠分钟数
        rem_sleep = random.randint(60, 120)  # REM睡眠分钟数
        awake = random.randint(10, 30)  # 清醒分钟数
        
        total_sleep = deep_sleep + light_sleep + rem_sleep
        
        new_data.append({
            "timestamp": sleep_start,
            "data_type": "sleep",
            "value": {
                "total_minutes": total_sleep,
                "deep_sleep_minutes": deep_sleep,
                "light_sleep_minutes": light_sleep,
                "rem_sleep_minutes": rem_sleep,
                "awake_minutes": awake
            },
            "unit": "minutes",
            "metadata": {
                "sleep_start": sleep_start.isoformat(),
                "sleep_end": (sleep_start + timedelta(minutes=total_sleep + awake)).isoformat()
            }
        })
        
        # 生成血氧数据
        if random.random() > 0.3:  # 模拟70%的可能性有血氧数据
            oxygen_saturation = random.randint(95, 100)
            new_data.append({
                "timestamp": timestamp,
                "data_type": "oxygen_saturation",
                "value": oxygen_saturation,
                "unit": "%",
                "metadata": {
                    "measurement_method": "optical"
                }
            })
        
        # 保存到数据库
        saved_ids = await self.save_device_data(str(device["_id"]), new_data)
        
        return {
            "success": True,
            "message": f"成功同步{len(saved_ids)}条可穿戴设备数据",
            "new_data": new_data
        }
    
    async def get_status(self, device: Dict) -> Dict:
        """获取可穿戴设备状态"""
        import random
        
        # 模拟电池电量和信号强度
        battery_level = random.randint(30, 100)
        signal_strength = random.randint(1, 5)
        
        # 根据最后连接时间判断状态
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
            "battery_level": battery_level,
            "signal_strength": signal_strength,
            "last_sync_time": last_connected
        }


device_service = DeviceService() 
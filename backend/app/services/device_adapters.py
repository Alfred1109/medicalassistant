"""
设备适配器模块
实现各种医疗设备的适配器，用于统一设备数据接口
"""
from typing import Dict, List, Optional, Any, Union
from datetime import datetime, timedelta
import random
import numpy as np
from bson import ObjectId

from ..models.device_data_standard import DeviceType
from .device_data_validator_service import device_data_validator_service

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
            
        from ..db.mongodb import get_db
        db = await get_db()
        
        # 使用验证服务验证数据
        device_type = device_id.get("device_type", "其他")
        validation_result = device_data_validator_service.batch_validate_device_data(data_list, device_type)
        
        # 只保存有效数据
        valid_data = validation_result["valid"]
        
        # 准备数据
        device_data = []
        for data in valid_data:
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
        
        if not device_data:
            return []
            
        # 批量插入
        result = await db.device_data.insert_many(device_data)
        return [str(id) for id in result.inserted_ids]
    
    def _get_random_status(self, device: Dict) -> Dict:
        """生成随机设备状态（供模拟使用）"""
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


class WearableAdapter(DeviceAdapter):
    """可穿戴设备适配器（如智能手环、手表）"""
    
    async def sync_data(self, device: Dict) -> Dict:
        """同步可穿戴设备数据"""
        # 实际项目中，这里应该调用设备SDK或API获取数据
        
        # 模拟数据
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
        return self._get_random_status(device)


class ContinuousGlucoseMonitorAdapter(DeviceAdapter):
    """连续血糖监测仪适配器"""
    
    async def sync_data(self, device: Dict) -> Dict:
        """同步连续血糖监测仪数据"""
        # 模拟数据
        new_data = []
        base_timestamp = datetime.utcnow()
        
        # 生成过去24小时的血糖数据，每5分钟一个点
        for i in range(288):  # 24小时 * 12个点/小时
            timestamp = base_timestamp - timedelta(minutes=5 * (288 - i))
            
            # 模拟一个真实的血糖波动曲线
            hour_of_day = timestamp.hour
            # 早餐、午餐、晚餐后血糖升高
            meal_effect = 0
            if 7 <= hour_of_day < 9:  # 早餐后
                meal_effect = 3.0
            elif 12 <= hour_of_day < 14:  # 午餐后
                meal_effect = 2.5
            elif 18 <= hour_of_day < 20:  # 晚餐后
                meal_effect = 2.0
                
            # 基础血糖水平(4.5-6.0)加上餐后效应和随机波动
            base_glucose = 5.0
            random_variation = random.uniform(-0.5, 0.5)
            glucose_value = round(base_glucose + meal_effect * max(0, 1 - (timestamp.minute / 60)) + random_variation, 1)
            
            new_data.append({
                "timestamp": timestamp,
                "data_type": "blood_glucose",
                "value": glucose_value,
                "unit": "mmol/L",
                "metadata": {
                    "measurement_time": self._get_meal_relation(hour_of_day)
                }
            })
        
        # 保存到数据库
        saved_ids = await self.save_device_data(str(device["_id"]), new_data)
        
        return {
            "success": True,
            "message": f"成功同步{len(saved_ids)}条连续血糖数据",
            "new_data": new_data[-10:]  # 只返回最近10条数据
        }
    
    async def get_status(self, device: Dict) -> Dict:
        """获取连续血糖监测仪状态"""
        status = self._get_random_status(device)
        # 连续血糖监测设备通常预计有额外的传感器使用寿命信息
        status["sensor_life_remaining"] = random.randint(1, 14)  # 剩余天数
        status["calibration_needed"] = random.random() < 0.2  # 20%概率需要校准
        return status
    
    def _get_meal_relation(self, hour: int) -> str:
        """根据一天中的时间确定与餐食的关系"""
        if 6 <= hour < 7:
            return "fasting"  # 空腹
        elif 7 <= hour < 9:
            return "after_breakfast"  # 早餐后
        elif 11 <= hour < 12:
            return "before_lunch"  # 午餐前
        elif 12 <= hour < 14:
            return "after_lunch"  # 午餐后
        elif 17 <= hour < 18:
            return "before_dinner"  # 晚餐前
        elif 18 <= hour < 20:
            return "after_dinner"  # 晚餐后
        elif 21 <= hour < 23:
            return "before_sleep"  # 睡前
        else:
            return "between_meals"  # 餐间


class SpirometerAdapter(DeviceAdapter):
    """肺活量计适配器"""
    
    async def sync_data(self, device: Dict) -> Dict:
        """同步肺活量计数据"""
        # 模拟数据
        new_data = []
        timestamp = datetime.utcnow()
        
        # 生成肺功能数据
        fvc = round(random.uniform(3.0, 5.0), 2)  # 用力肺活量
        fev1 = round(random.uniform(2.0, fvc * 0.9), 2)  # 一秒用力呼气量
        pef = round(random.uniform(7.0, 10.0), 2)  # 峰值呼气流量
        
        # 用力肺活量(FVC)
        new_data.append({
            "timestamp": timestamp,
            "data_type": "fvc",
            "value": fvc,
            "unit": "L",
            "metadata": {
                "measurement_method": "spirometry",
                "posture": "sitting"
            }
        })
        
        # 一秒用力呼气量(FEV1)
        new_data.append({
            "timestamp": timestamp,
            "data_type": "fev1",
            "value": fev1,
            "unit": "L",
            "metadata": {
                "measurement_method": "spirometry",
                "posture": "sitting"
            }
        })
        
        # FEV1/FVC比值
        new_data.append({
            "timestamp": timestamp,
            "data_type": "fev1_fvc_ratio",
            "value": round(fev1 / fvc, 2),
            "unit": "",
            "metadata": {
                "measurement_method": "spirometry",
                "posture": "sitting"
            }
        })
        
        # 峰值呼气流量(PEF)
        new_data.append({
            "timestamp": timestamp,
            "data_type": "pef",
            "value": pef,
            "unit": "L/s",
            "metadata": {
                "measurement_method": "spirometry",
                "posture": "sitting"
            }
        })
        
        # 保存到数据库
        saved_ids = await self.save_device_data(str(device["_id"]), new_data)
        
        return {
            "success": True,
            "message": f"成功同步{len(saved_ids)}条肺活量计数据",
            "new_data": new_data
        }
    
    async def get_status(self, device: Dict) -> Dict:
        """获取肺活量计状态"""
        return self._get_random_status(device)


class RehabEquipmentAdapter(DeviceAdapter):
    """康复训练设备适配器"""
    
    async def sync_data(self, device: Dict) -> Dict:
        """同步康复训练设备数据"""
        # 模拟数据
        new_data = []
        timestamp = datetime.utcnow()
        
        # 设备可能包含的训练模式及参数
        settings = device.get("settings", {})
        train_mode = settings.get("train_mode", "passive")
        
        # 训练时长(分钟)
        duration = random.randint(15, 45)
        
        # 基于训练模式生成不同的数据
        if train_mode == "passive":  # 被动训练
            # 关节活动度数据
            range_of_motion = random.randint(70, 120)
            new_data.append({
                "timestamp": timestamp,
                "data_type": "joint_range_of_motion",
                "value": range_of_motion,
                "unit": "degrees",
                "metadata": {
                    "joint": settings.get("target_joint", "knee"),
                    "movement_type": "passive"
                }
            })
            
            # 训练次数
            repetitions = random.randint(20, 50)
            new_data.append({
                "timestamp": timestamp,
                "data_type": "exercise_repetitions",
                "value": repetitions,
                "unit": "count",
                "metadata": {
                    "exercise_type": "passive_mobilization",
                    "joint": settings.get("target_joint", "knee")
                }
            })
            
        elif train_mode == "active":  # 主动训练
            # 肌力数据
            muscle_strength = random.randint(3, 5)  # 肌力分级
            new_data.append({
                "timestamp": timestamp,
                "data_type": "muscle_strength",
                "value": muscle_strength,
                "unit": "grade",
                "metadata": {
                    "muscle_group": settings.get("target_muscle", "quadriceps"),
                    "evaluation_method": "manual"
                }
            })
            
            # 训练负荷
            load = random.randint(5, 30)
            new_data.append({
                "timestamp": timestamp,
                "data_type": "exercise_load",
                "value": load,
                "unit": "kg",
                "metadata": {
                    "exercise_type": "resistance_training",
                    "muscle_group": settings.get("target_muscle", "quadriceps")
                }
            })
            
            # 训练次数和组数
            sets = random.randint(3, 5)
            reps_per_set = random.randint(8, 15)
            new_data.append({
                "timestamp": timestamp,
                "data_type": "exercise_sets_reps",
                "value": {
                    "sets": sets,
                    "reps_per_set": reps_per_set,
                    "total_reps": sets * reps_per_set
                },
                "unit": "count",
                "metadata": {
                    "exercise_type": "resistance_training",
                    "muscle_group": settings.get("target_muscle", "quadriceps")
                }
            })
            
        # 训练总时长
        new_data.append({
            "timestamp": timestamp,
            "data_type": "exercise_duration",
            "value": duration,
            "unit": "minutes",
            "metadata": {
                "training_mode": train_mode,
                "device_model": device.get("model", "unknown")
            }
        })
        
        # 保存到数据库
        saved_ids = await self.save_device_data(str(device["_id"]), new_data)
        
        return {
            "success": True,
            "message": f"成功同步{len(saved_ids)}条康复训练设备数据",
            "new_data": new_data
        }
    
    async def get_status(self, device: Dict) -> Dict:
        """获取康复训练设备状态"""
        status = self._get_random_status(device)
        
        # 康复设备特有的状态信息
        settings = device.get("settings", {})
        status["current_mode"] = settings.get("train_mode", "passive")
        status["calibration_status"] = random.choice(["calibrated", "needs_calibration"])
        status["maintenance_due"] = random.random() < 0.1  # 10%概率需要维护
        
        return status


class TENSUnitAdapter(DeviceAdapter):
    """经皮神经电刺激(TENS)设备适配器"""
    
    async def sync_data(self, device: Dict) -> Dict:
        """同步TENS设备数据"""
        # 模拟数据
        new_data = []
        timestamp = datetime.utcnow()
        
        # 设备可能包含的参数
        settings = device.get("settings", {})
        
        # 刺激强度
        intensity = settings.get("intensity", random.randint(1, 10))
        new_data.append({
            "timestamp": timestamp,
            "data_type": "tens_intensity",
            "value": intensity,
            "unit": "level",
            "metadata": {
                "mode": settings.get("stimulation_mode", "continuous"),
                "channel": settings.get("active_channel", "all")
            }
        })
        
        # 刺激频率
        frequency = settings.get("frequency", random.randint(2, 150))
        new_data.append({
            "timestamp": timestamp,
            "data_type": "tens_frequency",
            "value": frequency,
            "unit": "Hz",
            "metadata": {
                "mode": settings.get("stimulation_mode", "continuous"),
                "channel": settings.get("active_channel", "all")
            }
        })
        
        # 脉冲宽度
        pulse_width = settings.get("pulse_width", random.randint(50, 300))
        new_data.append({
            "timestamp": timestamp,
            "data_type": "tens_pulse_width",
            "value": pulse_width,
            "unit": "μs",
            "metadata": {
                "mode": settings.get("stimulation_mode", "continuous"),
                "channel": settings.get("active_channel", "all")
            }
        })
        
        # 治疗时长
        duration = settings.get("duration", random.randint(15, 45))
        new_data.append({
            "timestamp": timestamp,
            "data_type": "tens_treatment_duration",
            "value": duration,
            "unit": "minutes",
            "metadata": {
                "treatment_area": settings.get("treatment_area", "lower_back"),
                "treatment_purpose": settings.get("purpose", "pain_relief")
            }
        })
        
        # 保存到数据库
        saved_ids = await self.save_device_data(str(device["_id"]), new_data)
        
        return {
            "success": True,
            "message": f"成功同步{len(saved_ids)}条TENS设备数据",
            "new_data": new_data
        }
    
    async def get_status(self, device: Dict) -> Dict:
        """获取TENS设备状态"""
        status = self._get_random_status(device)
        
        # TENS设备特有的状态信息
        settings = device.get("settings", {})
        status["active_mode"] = settings.get("stimulation_mode", "off")
        status["electrode_status"] = random.choice(["connected", "disconnected", "poor_contact"])
        
        return status


# 适配器工厂
def get_device_adapter(device_type: str) -> DeviceAdapter:
    """根据设备类型获取适配器"""
    adapter_map = {
        "血压计": BloodPressureAdapter(),
        "血糖仪": GlucoseMeterAdapter(),
        "体温计": ThermometerAdapter(),
        "心电图": ECGAdapter(),
        "体重秤": ScaleAdapter(),
        "手环": WearableAdapter(),
        "连续血糖监测仪": ContinuousGlucoseMonitorAdapter(),
        "肺活量计": SpirometerAdapter(),
        "康复训练设备": RehabEquipmentAdapter(),
        "TENS设备": TENSUnitAdapter()
    }
    
    return adapter_map.get(device_type, GenericAdapter())


# 这里应该引入所有已经在别处实现的适配器类
# 为了保持文件的连贯性，这里假设它们都已存在
class BloodPressureAdapter(DeviceAdapter):
    pass

class GlucoseMeterAdapter(DeviceAdapter):
    pass

class ThermometerAdapter(DeviceAdapter):
    pass

class ECGAdapter(DeviceAdapter):
    pass

class ScaleAdapter(DeviceAdapter):
    pass 
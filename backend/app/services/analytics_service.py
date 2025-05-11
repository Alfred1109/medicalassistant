from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
import random
from pymongo.database import Database
from bson import ObjectId

class AnalyticsService:
    """数据分析和可视化服务"""
    
    def __init__(self, db: Database):
        """初始化数据分析服务
        
        Args:
            db: MongoDB数据库连接
        """
        self.db = db
        self.patients_collection = db.patients
        self.doctors_collection = db.doctors
        self.devices_collection = db.devices
        self.rehabilitation_collection = db.rehabilitation_records
    
    async def get_stats_overview(self) -> Dict[str, Any]:
        """获取系统统计数据概览
        
        Returns:
            包含各种统计数据的字典
        """
        try:
            # 计算患者数量
            patient_count = await self.patients_collection.count_documents({})
            
            # 计算医生数量
            doctor_count = await self.doctors_collection.count_documents({})
            
            # 计算设备数量
            device_count = await self.devices_collection.count_documents({})
            
            # 计算活跃设备比例
            active_devices = await self.devices_collection.count_documents({"status": "active"})
            active_device_rate = (active_devices / device_count * 100) if device_count > 0 else 0
            
            # 计算一周内的患者增长率
            one_week_ago = datetime.utcnow() - timedelta(days=7)
            previous_patient_count = await self.patients_collection.count_documents(
                {"created_at": {"$lt": one_week_ago}}
            )
            week_patient_change = ((patient_count - previous_patient_count) / previous_patient_count * 100) if previous_patient_count > 0 else 0
            
            # 计算平均训练时间（分钟）
            rehab_records = self.rehabilitation_collection.find({})
            total_duration = 0
            record_count = 0
            
            async for record in rehab_records:
                if "duration" in record:
                    total_duration += record.get("duration", 0)
                    record_count += 1
            
            avg_training_time = total_duration / record_count if record_count > 0 else 0
            
            # 由于缺少实际数据，以下数据为模拟值
            rehabilitation_rate = 68  # 康复率
            patient_satisfaction = 92  # 患者满意度
            
            return {
                "patientCount": patient_count,
                "weekPatientChange": round(week_patient_change, 1),
                "doctorCount": doctor_count,
                "totalDevices": device_count,
                "activeDeviceRate": round(active_device_rate, 1),
                "avgTrainingTime": round(avg_training_time, 1),
                "rehabilitationRate": rehabilitation_rate,
                "patientSatisfaction": patient_satisfaction
            }
        except Exception as e:
            print(f"获取统计数据概览失败: {str(e)}")
            # 返回模拟数据
            return {
                "patientCount": 1248,
                "weekPatientChange": 4.2,
                "doctorCount": 86, 
                "totalDevices": 152,
                "activeDeviceRate": 82,
                "avgTrainingTime": 45,
                "rehabilitationRate": 68,
                "patientSatisfaction": 92
            }

    async def get_trend_data(self, data_type: str, time_range: str) -> List[Dict[str, Any]]:
        """获取趋势数据
        
        Args:
            data_type: 数据类型 (patient, doctor, device, rehabilitation)
            time_range: 时间范围 (day, week, month, quarter, year)
            
        Returns:
            趋势数据列表
        """
        try:
            # 实现实际的数据查询逻辑
            # 这里为了演示，返回模拟数据
            days_count = {
                "day": 24,  # 一天24小时
                "week": 7,  # 一周7天
                "month": 30,  # 一个月约30天
                "quarter": 90,  # 一个季度约90天
                "year": 12  # 一年12个月
            }.get(time_range, 30)
            
            result = []
            now = datetime.utcnow()
            is_monthly = time_range == "year"  # 年度数据按月展示
            
            for i in range(days_count):
                date = datetime.utcnow()
                
                if is_monthly:
                    # 设置为前N个月
                    date = datetime(now.year, now.month - (days_count - 1) + i, 1) if now.month > (days_count - 1) - i else datetime(now.year - 1, 12 - ((days_count - 1) - i - now.month), 1)
                elif time_range == "day":
                    # 按小时设置
                    date = now - timedelta(hours=(days_count - 1) - i)
                else:
                    # 按天设置
                    date = now - timedelta(days=(days_count - 1) - i)
                
                # 生成随机数据
                if data_type == "patient":
                    value = random.randint(10, 50)
                elif data_type == "doctor":
                    value = random.randint(1, 10)
                elif data_type == "device":
                    value = random.randint(5, 30)
                else:
                    value = random.randint(20, 100)
                
                result.append({
                    "timestamp": date.isoformat(),
                    "value": value
                })
            
            return result
        except Exception as e:
            print(f"获取趋势数据失败: {str(e)}")
            # 返回空列表
            return []
    
    async def get_distribution_data(self, data_type: str, time_range: str) -> List[Dict[str, Any]]:
        """获取分布数据
        
        Args:
            data_type: 数据类型 (patient, doctor, device, rehabilitation)
            time_range: 时间范围 (day, week, month, quarter, year)
            
        Returns:
            分布数据列表
        """
        try:
            # 实现实际的数据查询逻辑
            # 这里为了演示，返回模拟数据
            result = []
            
            if data_type == "patient":
                categories = ["老年患者", "中年患者", "青年患者", "儿童患者"]
            elif data_type == "doctor":
                categories = ["康复科", "骨科", "神经科", "内科", "外科"]
            elif data_type == "device":
                categories = ["上肢康复", "下肢康复", "平衡训练", "认知训练", "日常生活训练"]
            else:
                categories = ["完全康复", "明显改善", "轻微改善", "无变化", "恶化"]
            
            total_value = 100
            remaining = total_value
            
            for i, category in enumerate(categories):
                # 最后一个类别获取剩余值，确保总和为100
                if i == len(categories) - 1:
                    value = remaining
                else:
                    value = random.randint(5, remaining - (len(categories) - i - 1) * 5)
                    remaining -= value
                
                result.append({
                    "category": category,
                    "value": value
                })
            
            return result
        except Exception as e:
            print(f"获取分布数据失败: {str(e)}")
            # 返回空列表
            return []
    
    async def get_comparison_data(self, data_type: str, time_range: str, compare_with: str) -> List[Dict[str, Any]]:
        """获取对比数据
        
        Args:
            data_type: 数据类型 (patient, doctor, device, rehabilitation)
            time_range: 时间范围 (day, week, month, quarter, year)
            compare_with: 对比对象 (lastPeriod, lastYear, target)
            
        Returns:
            对比数据列表
        """
        try:
            # 实现实际的数据查询逻辑
            # 这里为了演示，返回模拟数据
            categories = ["接诊量", "康复率", "满意度", "随访率", "治疗时长"]
            result = []
            
            for category in categories:
                current_value = random.randint(50, 100)
                
                if compare_with == "lastPeriod":
                    compare_value = current_value * random.uniform(0.8, 1.2)
                elif compare_with == "lastYear":
                    compare_value = current_value * random.uniform(0.7, 1.3)
                else:  # target
                    compare_value = 100  # 目标值
                
                result.append({
                    "category": category,
                    "currentValue": round(current_value, 1),
                    "compareValue": round(compare_value, 1)
                })
            
            return result
        except Exception as e:
            print(f"获取对比数据失败: {str(e)}")
            # 返回空列表
            return [] 
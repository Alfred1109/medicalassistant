"""
设备数据分析服务
用于检测设备数据异常、分析趋势并提供预警
"""
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Union, Tuple, Any
import statistics
import math
from bson import ObjectId

from ..db.mongodb import get_db
from ..services.device_service import device_service


class DeviceAnalysisService:
    """设备数据分析服务"""
    
    # 异常检测阈值配置
    # 可以根据不同设备类型和数据类型进行调整
    DEFAULT_THRESHOLDS = {
        # 血压计
        "blood_pressure_systolic": {"min": 70, "max": 180, "z_score": 3.0},
        "blood_pressure_diastolic": {"min": 40, "max": 120, "z_score": 3.0},
        "pulse": {"min": 40, "max": 160, "z_score": 3.0},
        
        # 血糖仪
        "blood_glucose": {"min": 2.0, "max": 30.0, "z_score": 3.0},
        
        # 体温计
        "body_temperature": {"min": 35.0, "max": 42.0, "z_score": 3.0},
        
        # 心电图
        "heart_rate": {"min": 30, "max": 200, "z_score": 3.0},
        
        # 体重秤
        "weight": {"min": 10.0, "max": 300.0, "z_score": 3.0},
        "body_fat_percentage": {"min": 3.0, "max": 50.0, "z_score": 3.0},
        
        # 可穿戴设备
        "steps": {"min": 0, "max": 100000, "z_score": 3.0},
        "oxygen_saturation": {"min": 70, "max": 100, "z_score": 3.0},
    }
    
    async def detect_data_anomalies(
        self, 
        device_id: str, 
        data_type: Optional[str] = None,
        days: int = 30,
        method: str = "z_score"
    ) -> List[Dict]:
        """
        检测设备数据异常
        
        参数:
        - device_id: 设备ID
        - data_type: 数据类型，如不指定则检测所有类型
        - days: 检测最近多少天的数据
        - method: 异常检测方法，支持'z_score', 'range', 'iqr'
        
        返回:
        - 异常数据列表
        """
        # 获取设备数据
        start_date = datetime.utcnow() - timedelta(days=days)
        data = await device_service.get_device_data(
            device_id,
            start_date=start_date,
            data_type=data_type,
            limit=10000  # 设置足够大的限制以获取所有数据
        )
        
        if not data:
            return []
        
        # 按数据类型分组
        data_by_type = {}
        for item in data:
            item_type = item.get("data_type")
            if item_type not in data_by_type:
                data_by_type[item_type] = []
            data_by_type[item_type].append(item)
        
        # 检测每种类型的异常
        anomalies = []
        for current_type, type_data in data_by_type.items():
            # 获取阈值配置
            threshold = self.DEFAULT_THRESHOLDS.get(current_type, {"min": None, "max": None, "z_score": 3.0})
            
            # 提取数值
            values = []
            for item in type_data:
                value = item.get("value")
                # 处理复合值（如睡眠数据、ECG波形）
                if isinstance(value, dict):
                    continue
                values.append(float(value))
            
            # 检测异常
            if method == "z_score" and len(values) >= 5:
                anomaly_indices = self._z_score_detection(values, threshold["z_score"])
            elif method == "iqr" and len(values) >= 5:
                anomaly_indices = self._iqr_detection(values)
            else:
                # 范围检测作为默认方法
                anomaly_indices = self._range_detection(values, threshold["min"], threshold["max"])
            
            # 收集异常数据
            for idx in anomaly_indices:
                anomalies.append({
                    **type_data[idx],
                    "anomaly_score": self._calculate_anomaly_score(values[idx], values, threshold),
                    "detection_method": method
                })
        
        # 按异常分数排序
        anomalies.sort(key=lambda x: x.get("anomaly_score", 0), reverse=True)
        return anomalies
    
    def _z_score_detection(self, values: List[float], threshold: float = 3.0) -> List[int]:
        """
        使用Z分数检测异常
        Z分数 = (x - 平均值) / 标准差
        """
        if len(values) < 2:
            return []
            
        mean = statistics.mean(values)
        std = statistics.stdev(values)
        
        if std == 0:  # 防止除以零
            return []
            
        anomalies = []
        for i, value in enumerate(values):
            z_score = abs((value - mean) / std)
            if z_score > threshold:
                anomalies.append(i)
                
        return anomalies
    
    def _iqr_detection(self, values: List[float], factor: float = 1.5) -> List[int]:
        """
        使用四分位距(IQR)检测异常
        IQR = Q3 - Q1
        异常值 = x < Q1 - factor * IQR 或 x > Q3 + factor * IQR
        """
        if len(values) < 4:  # 需要足够的数据来计算四分位数
            return []
            
        sorted_values = sorted(values)
        q1_idx = int(len(sorted_values) * 0.25)
        q3_idx = int(len(sorted_values) * 0.75)
        
        q1 = sorted_values[q1_idx]
        q3 = sorted_values[q3_idx]
        iqr = q3 - q1
        
        lower_bound = q1 - factor * iqr
        upper_bound = q3 + factor * iqr
        
        anomalies = []
        for i, value in enumerate(values):
            if value < lower_bound or value > upper_bound:
                anomalies.append(i)
                
        return anomalies
    
    def _range_detection(
        self, 
        values: List[float], 
        min_val: Optional[float] = None, 
        max_val: Optional[float] = None
    ) -> List[int]:
        """
        使用范围检测异常
        如果值超出指定范围，则视为异常
        """
        anomalies = []
        for i, value in enumerate(values):
            if (min_val is not None and value < min_val) or (max_val is not None and value > max_val):
                anomalies.append(i)
                
        return anomalies
    
    def _calculate_anomaly_score(
        self, 
        value: float, 
        values: List[float], 
        threshold: Dict
    ) -> float:
        """
        计算异常分数
        分数越高表示异常程度越高
        """
        # 基于Z分数的异常分数
        if len(values) >= 2:
            mean = statistics.mean(values)
            std = statistics.stdev(values)
            
            if std == 0:  # 防止除以零
                z_score = 0
            else:
                z_score = abs((value - mean) / std)
                
            # 归一化到0-100范围
            score = min(100, (z_score / threshold.get("z_score", 3.0)) * 50)
            
            # 如果超出绝对范围，增加分数
            min_val = threshold.get("min")
            max_val = threshold.get("max")
            if (min_val is not None and value < min_val) or (max_val is not None and value > max_val):
                score += 50
                
            return min(100, score)
        else:
            # 仅基于范围的异常分数
            min_val = threshold.get("min")
            max_val = threshold.get("max")
            
            if min_val is not None and value < min_val:
                return 80 + min(20, 20 * (min_val - value) / (min_val if min_val != 0 else 1))
            elif max_val is not None and value > max_val:
                return 80 + min(20, 20 * (value - max_val) / max_val)
            else:
                return 0

    async def analyze_data_trend(
        self,
        device_id: str,
        data_type: str,
        days: int = 30,
        interval: str = "day"
    ) -> Dict:
        """
        分析设备数据趋势
        
        参数:
        - device_id: 设备ID
        - data_type: 数据类型
        - days: 分析最近多少天的数据
        - interval: 数据聚合间隔，支持'hour', 'day', 'week', 'month'
        
        返回:
        - 趋势分析结果，包含均值、最大值、最小值、变化率等
        """
        # 获取设备数据
        start_date = datetime.utcnow() - timedelta(days=days)
        data = await device_service.get_device_data(
            device_id,
            start_date=start_date,
            data_type=data_type,
            limit=10000
        )
        
        if not data:
            return {
                "status": "error",
                "message": "无数据可分析",
                "data_type": data_type,
                "device_id": device_id
            }
        
        # 提取值
        values = []
        timestamps = []
        for item in data:
            value = item.get("value")
            # 处理复合值
            if isinstance(value, dict):
                continue
            values.append(float(value))
            timestamps.append(item.get("timestamp"))
        
        if not values:
            return {
                "status": "error",
                "message": "无有效数据可分析",
                "data_type": data_type,
                "device_id": device_id
            }
            
        # 基本统计分析
        stats = {
            "count": len(values),
            "mean": statistics.mean(values),
            "median": statistics.median(values),
            "max": max(values),
            "min": min(values),
            "std": statistics.stdev(values) if len(values) > 1 else 0,
            "unit": data[0].get("unit", ""),
            "first_timestamp": min(timestamps),
            "last_timestamp": max(timestamps)
        }
        
        # 检查数据是否足够做趋势分析
        if len(values) < 3:
            return {
                "status": "warning",
                "message": "数据点过少，无法进行有效的趋势分析",
                "statistics": stats,
                "data_type": data_type,
                "device_id": device_id
            }
            
        # 计算时间段内的变化率
        first_value = values[0]
        last_value = values[-1]
        change_rate = ((last_value - first_value) / first_value) * 100 if first_value != 0 else 0
        
        # 按时间聚合数据
        aggregated_data = self._aggregate_data_by_interval(values, timestamps, interval)
        
        # 进行线性回归分析
        slope, intercept, r_squared = self._linear_regression(range(len(values)), values)
        
        # 判断趋势方向
        if slope > 0.01:
            trend_direction = "上升"
        elif slope < -0.01:
            trend_direction = "下降"
        else:
            trend_direction = "稳定"
            
        # 计算预测值
        prediction_days = 7  # 预测未来7天
        future_days = list(range(len(values), len(values) + prediction_days))
        predictions = [slope * x + intercept for x in future_days]
        
        # 返回分析结果
        result = {
            "status": "success",
            "data_type": data_type,
            "device_id": device_id,
            "statistics": stats,
            "trend": {
                "direction": trend_direction,
                "slope": slope,
                "change_rate": change_rate,
                "r_squared": r_squared
            },
            "aggregated_data": aggregated_data,
            "prediction": {
                "days": prediction_days,
                "values": predictions
            }
        }
        
        return result
        
    def _aggregate_data_by_interval(
        self,
        values: List[float],
        timestamps: List[datetime],
        interval: str = "day"
    ) -> List[Dict]:
        """
        按时间间隔聚合数据
        
        参数:
        - values: 数值列表
        - timestamps: 时间戳列表
        - interval: 聚合间隔
        
        返回:
        - 聚合后的数据列表
        """
        if not values or not timestamps or len(values) != len(timestamps):
            return []
            
        # 创建时间索引字典
        time_dict = {}
        
        for i, timestamp in enumerate(timestamps):
            # 根据间隔生成键
            if interval == "hour":
                key = timestamp.strftime("%Y-%m-%d %H:00:00")
            elif interval == "day":
                key = timestamp.strftime("%Y-%m-%d")
            elif interval == "week":
                # 计算一周的开始日期
                week_start = timestamp - timedelta(days=timestamp.weekday())
                key = week_start.strftime("%Y-%m-%d")
            elif interval == "month":
                key = timestamp.strftime("%Y-%m-01")
            else:
                key = timestamp.strftime("%Y-%m-%d")  # 默认使用日
                
            if key not in time_dict:
                time_dict[key] = []
                
            time_dict[key].append(values[i])
            
        # 计算每个时间间隔的统计数据
        result = []
        for time_key, time_values in sorted(time_dict.items()):
            result.append({
                "timestamp": time_key,
                "count": len(time_values),
                "mean": statistics.mean(time_values),
                "median": statistics.median(time_values),
                "max": max(time_values),
                "min": min(time_values),
                "std": statistics.stdev(time_values) if len(time_values) > 1 else 0
            })
            
        return result
        
    def _linear_regression(
        self,
        x: List[int],
        y: List[float]
    ) -> Tuple[float, float, float]:
        """
        进行线性回归分析
        
        参数:
        - x: 自变量列表 (通常是时间索引)
        - y: 因变量列表 (通常是测量值)
        
        返回:
        - 斜率、截距、R平方值
        """
        if len(x) != len(y) or len(x) < 2:
            return 0, 0, 0
            
        n = len(x)
        sum_x = sum(x)
        sum_y = sum(y)
        sum_xy = sum(x_i * y_i for x_i, y_i in zip(x, y))
        sum_xx = sum(x_i ** 2 for x_i in x)
        
        # 计算斜率
        slope = (n * sum_xy - sum_x * sum_y) / (n * sum_xx - sum_x ** 2) if (n * sum_xx - sum_x ** 2) != 0 else 0
        
        # 计算截距
        intercept = (sum_y - slope * sum_x) / n
        
        # 计算拟合优度 R²
        y_mean = sum_y / n
        ss_total = sum((y_i - y_mean) ** 2 for y_i in y)
        ss_residual = sum((y_i - (slope * x_i + intercept)) ** 2 for x_i, y_i in zip(x, y))
        r_squared = 1 - (ss_residual / ss_total) if ss_total != 0 else 0
        
        return slope, intercept, r_squared

    async def monitor_device_status(
        self,
        device_id: Optional[str] = None,
        patient_id: Optional[str] = None,
        hours: int = 24
    ) -> List[Dict]:
        """
        监测设备状态
        
        参数:
        - device_id: 设备ID，如不指定则检查patient_id名下所有设备
        - patient_id: 患者ID，如指定则检查该患者名下所有设备
        - hours: 监测最近多少小时的设备状态
        
        返回:
        - 设备状态列表，包含状态异常的设备信息
        """
        db = await get_db()
        
        # 构建查询条件
        query = {}
        if device_id:
            query["_id"] = ObjectId(device_id)
        if patient_id:
            query["patient_id"] = patient_id
        
        # 获取设备列表
        devices = await db.devices.find(query).to_list(None)
        if not devices:
            return []
            
        # 检查每个设备的状态
        status_results = []
        for device in devices:
            device["_id"] = str(device["_id"])
            
            # 获取设备状态
            status = await device_service.get_device_status(device["_id"])
            
            # 计算设备状态得分
            status_score = self._calculate_device_status_score(device, status)
            
            # 只返回状态异常的设备
            if status_score > 20:  # 得分大于20认为有异常
                status_results.append({
                    "device": device,
                    "status": status,
                    "status_score": status_score,
                    "issues": self._identify_device_issues(device, status, hours),
                    "recommendations": self._get_device_recommendations(device, status, status_score)
                })
                
        # 按状态得分排序
        status_results.sort(key=lambda x: x.get("status_score", 0), reverse=True)
        return status_results
    
    def _calculate_device_status_score(self, device: Dict, status: Dict) -> float:
        """
        计算设备状态得分
        得分越高表示异常程度越高
        """
        score = 0
        
        # 检查设备状态
        if status.get("status") == "error":
            score += 80
        elif status.get("status") == "offline":
            score += 50
        elif status.get("status") == "idle":
            score += 20
        
        # 检查电池电量
        battery_level = status.get("battery_level", 0)
        if battery_level < 10:
            score += 50
        elif battery_level < 20:
            score += 30
        elif battery_level < 30:
            score += 10
            
        # 检查信号强度
        signal_strength = status.get("signal_strength", 0)
        if signal_strength <= 1:
            score += 30
        elif signal_strength == 2:
            score += 10
            
        # 检查最后同步时间
        last_sync_time = status.get("last_sync_time")
        if last_sync_time:
            time_diff = (datetime.utcnow() - last_sync_time).total_seconds()
            if time_diff > 86400 * 7:  # 7天未同步
                score += 50
            elif time_diff > 86400 * 3:  # 3天未同步
                score += 30
            elif time_diff > 86400:  # 1天未同步
                score += 10
        else:
            score += 40  # 从未同步
            
        # 检查固件更新
        if device.get("firmware_update_available"):
            score += 10
            
        return min(100, score)  # 最高100分
    
    def _identify_device_issues(self, device: Dict, status: Dict, hours: int) -> List[Dict]:
        """
        识别设备存在的问题
        """
        issues = []
        
        # 检查设备状态
        device_status = status.get("status")
        if device_status == "error":
            issues.append({
                "type": "error",
                "message": f"设备发生错误: {status.get('message', '未知错误')}",
                "severity": "high"
            })
        elif device_status == "offline":
            issues.append({
                "type": "offline",
                "message": "设备离线",
                "severity": "medium"
            })
            
        # 检查电池电量
        battery_level = status.get("battery_level", 0)
        if battery_level < 10:
            issues.append({
                "type": "battery",
                "message": f"设备电量严重不足 ({battery_level}%)",
                "severity": "high"
            })
        elif battery_level < 20:
            issues.append({
                "type": "battery",
                "message": f"设备电量不足 ({battery_level}%)",
                "severity": "medium"
            })
            
        # 检查信号强度
        signal_strength = status.get("signal_strength", 0)
        if signal_strength <= 1:
            issues.append({
                "type": "signal",
                "message": "设备信号极弱",
                "severity": "medium"
            })
            
        # 检查最后同步时间
        last_sync_time = status.get("last_sync_time")
        if last_sync_time:
            time_diff = (datetime.utcnow() - last_sync_time).total_seconds() / 3600  # 转换为小时
            if time_diff > 24 * 7:  # 7天未同步
                issues.append({
                    "type": "sync",
                    "message": f"设备已超过{int(time_diff / 24)}天未同步数据",
                    "severity": "high"
                })
            elif time_diff > hours:  # 超过指定小时未同步
                issues.append({
                    "type": "sync",
                    "message": f"设备已超过{int(time_diff)}小时未同步数据",
                    "severity": "medium"
                })
        else:
            issues.append({
                "type": "sync",
                "message": "设备从未同步数据",
                "severity": "high"
            })
            
        # 检查固件更新
        if device.get("firmware_update_available"):
            issues.append({
                "type": "firmware",
                "message": "设备有新固件可更新",
                "severity": "low"
            })
            
        return issues
    
    def _get_device_recommendations(self, device: Dict, status: Dict, status_score: float) -> List[str]:
        """
        获取设备问题解决建议
        """
        recommendations = []
        
        # 根据状态得分提供建议
        if status_score >= 80:
            recommendations.append("建议立即联系技术支持检查设备")
            
        # 根据设备状态提供建议
        device_status = status.get("status")
        if device_status == "error":
            recommendations.append("尝试重启设备，如问题持续存在请联系技术支持")
        elif device_status == "offline":
            recommendations.append("检查设备是否开启、电池是否充足，并确保设备在信号范围内")
            
        # 根据电池电量提供建议
        battery_level = status.get("battery_level", 0)
        if battery_level < 20:
            recommendations.append("请尽快为设备充电")
            
        # 根据信号强度提供建议
        signal_strength = status.get("signal_strength", 0)
        if signal_strength <= 2:
            recommendations.append("将设备移至信号更强的区域，减少干扰物")
            
        # 根据同步时间提供建议
        last_sync_time = status.get("last_sync_time")
        if last_sync_time:
            time_diff = (datetime.utcnow() - last_sync_time).total_seconds() / 3600
            if time_diff > 24:
                recommendations.append("手动触发数据同步，检查设备同步功能是否正常")
                
        # 根据固件更新提供建议
        if device.get("firmware_update_available"):
            recommendations.append("建议升级设备固件以获得最新功能和修复")
            
        # 如果没有具体建议，提供通用建议
        if not recommendations:
            recommendations.append("定期检查设备状态，确保数据收集正常")
            
        return recommendations
    
    async def generate_device_alerts(
        self, 
        device_id: Optional[str] = None,
        patient_id: Optional[str] = None, 
        severity_threshold: str = "medium"
    ) -> List[Dict]:
        """
        生成设备预警信息
        
        参数:
        - device_id: 设备ID，如不指定则检查patient_id名下所有设备
        - patient_id: 患者ID，如指定则检查该患者名下所有设备
        - severity_threshold: 预警级别阈值，只返回大于等于该级别的预警
        
        返回:
        - 设备预警列表
        """
        # 监测设备状态
        device_statuses = await self.monitor_device_status(
            device_id=device_id,
            patient_id=patient_id
        )
        
        # 检查设备数据异常
        data_alerts = []
        if device_id:
            # 检查特定设备的所有数据类型
            anomalies = await self.detect_data_anomalies(device_id)
            if anomalies:
                # 转换为预警格式
                for anomaly in anomalies:
                    # 计算异常严重程度
                    severity = "low"
                    if anomaly.get("anomaly_score", 0) > 80:
                        severity = "high"
                    elif anomaly.get("anomaly_score", 0) > 50:
                        severity = "medium"
                        
                    data_alerts.append({
                        "type": "data_anomaly",
                        "device_id": device_id,
                        "device_name": next((d["device"]["name"] for d in device_statuses if d["device"]["_id"] == device_id), "未知设备"),
                        "data_type": anomaly.get("data_type"),
                        "value": anomaly.get("value"),
                        "unit": anomaly.get("unit", ""),
                        "timestamp": anomaly.get("timestamp"),
                        "anomaly_score": anomaly.get("anomaly_score", 0),
                        "message": f"检测到{anomaly.get('data_type')}数据异常值: {anomaly.get('value')}{anomaly.get('unit', '')}",
                        "severity": severity
                    })
        elif patient_id:
            # 获取患者所有设备
            db = await get_db()
            devices = await db.devices.find({"patient_id": patient_id, "status": {"$ne": "deleted"}}).to_list(None)
            
            # 检查每个设备的数据异常
            for device in devices:
                anomalies = await self.detect_data_anomalies(str(device["_id"]))
                if anomalies:
                    # 转换为预警格式
                    for anomaly in anomalies:
                        # 计算异常严重程度
                        severity = "low"
                        if anomaly.get("anomaly_score", 0) > 80:
                            severity = "high"
                        elif anomaly.get("anomaly_score", 0) > 50:
                            severity = "medium"
                            
                        data_alerts.append({
                            "type": "data_anomaly",
                            "device_id": str(device["_id"]),
                            "device_name": device.get("name", "未知设备"),
                            "data_type": anomaly.get("data_type"),
                            "value": anomaly.get("value"),
                            "unit": anomaly.get("unit", ""),
                            "timestamp": anomaly.get("timestamp"),
                            "anomaly_score": anomaly.get("anomaly_score", 0),
                            "message": f"检测到{device.get('name')}的{anomaly.get('data_type')}数据异常值: {anomaly.get('value')}{anomaly.get('unit', '')}",
                            "severity": severity
                        })
                        
        # 合并设备状态预警和数据异常预警
        alerts = []
        
        # 处理设备状态预警
        severity_map = {"high": 3, "medium": 2, "low": 1}
        min_severity = severity_map.get(severity_threshold, 1)
        
        for status in device_statuses:
            for issue in status.get("issues", []):
                issue_severity = severity_map.get(issue.get("severity", "low"), 1)
                if issue_severity >= min_severity:
                    alerts.append({
                        "type": "device_status",
                        "device_id": status["device"]["_id"],
                        "device_name": status["device"]["name"],
                        "issue_type": issue.get("type"),
                        "message": issue.get("message"),
                        "severity": issue.get("severity"),
                        "status_score": status.get("status_score"),
                        "recommendations": status.get("recommendations", [])
                    })
                    
        # 添加数据异常预警
        for alert in data_alerts:
            alert_severity = severity_map.get(alert.get("severity", "low"), 1)
            if alert_severity >= min_severity:
                alerts.append(alert)
                
        # 按严重程度和分数排序
        alerts.sort(key=lambda x: (
            severity_map.get(x.get("severity"), 1),
            x.get("status_score", 0) if x.get("type") == "device_status" else x.get("anomaly_score", 0)
        ), reverse=True)
        
        return alerts

    async def predict_data_advanced(
        self,
        device_id: str,
        data_type: str,
        days: int = 30,
        prediction_days: int = 7,
        method: str = "linear",
        confidence_interval: bool = True,
        interval: str = "day"
    ) -> Dict:
        """
        高级数据预测分析
        
        参数:
        - device_id: 设备ID
        - data_type: 数据类型
        - days: 分析最近多少天的数据
        - prediction_days: 预测未来多少天的数据
        - method: 预测方法，支持'linear'(线性回归), 'arima'(时间序列), 'prophet'(Facebook Prophet), 'ensemble'(集成方法)
        - confidence_interval: 是否计算置信区间
        - interval: 数据聚合间隔，支持'hour', 'day', 'week', 'month'
        
        返回:
        - 预测分析结果，包含预测值，置信区间等
        """
        # 获取设备数据
        start_date = datetime.utcnow() - timedelta(days=days)
        data = await device_service.get_device_data(
            device_id,
            start_date=start_date,
            data_type=data_type,
            limit=10000
        )
        
        if not data:
            return {
                "status": "error",
                "message": "无数据可分析",
                "data_type": data_type,
                "device_id": device_id
            }
        
        # 提取值
        values = []
        timestamps = []
        for item in data:
            value = item.get("value")
            # 处理复合值
            if isinstance(value, dict):
                continue
            values.append(float(value))
            timestamps.append(item.get("timestamp"))
        
        if not values:
            return {
                "status": "error",
                "message": "无有效数据可分析",
                "data_type": data_type,
                "device_id": device_id
            }
            
        # 检查数据是否足够做预测分析
        if len(values) < 5:
            return {
                "status": "warning",
                "message": "数据点过少，无法进行有效的预测分析",
                "data_type": data_type,
                "device_id": device_id
            }
            
        # 按时间聚合数据
        aggregated_data = self._aggregate_data_by_interval(values, timestamps, interval)
        aggregated_values = [item["value"] for item in aggregated_data]
        
        # 选择合适的预测方法
        result = {}
        if method == "linear" or method == "ensemble":
            # 线性回归预测
            linear_prediction, linear_conf = self._linear_prediction(
                aggregated_values, 
                prediction_days, 
                confidence_interval
            )
            result["linear"] = {
                "values": linear_prediction,
                "confidence_interval": linear_conf
            }
            
        if method == "arima" or method == "ensemble":
            # ARIMA时间序列预测
            arima_prediction, arima_conf = self._arima_prediction(
                aggregated_values, 
                prediction_days, 
                confidence_interval
            )
            result["arima"] = {
                "values": arima_prediction,
                "confidence_interval": arima_conf
            }
            
        if method == "prophet" or method == "ensemble":
            # Prophet预测
            prophet_prediction, prophet_conf = self._prophet_prediction(
                aggregated_values, 
                aggregated_data,
                prediction_days, 
                confidence_interval
            )
            result["prophet"] = {
                "values": prophet_prediction,
                "confidence_interval": prophet_conf
            }
            
        if method == "ensemble":
            # 集成方法 - 将多种方法的结果加权平均
            ensemble_prediction, ensemble_conf = self._ensemble_prediction(
                result["linear"]["values"],
                result["arima"]["values"],
                result["prophet"]["values"],
                prediction_days,
                confidence_interval,
                result["linear"]["confidence_interval"],
                result["arima"]["confidence_interval"],
                result["prophet"]["confidence_interval"]
            )
            result["ensemble"] = {
                "values": ensemble_prediction,
                "confidence_interval": ensemble_conf
            }
            
        # 准备预测结果
        prediction_result = {
            "status": "success",
            "data_type": data_type,
            "device_id": device_id,
            "days_analyzed": days,
            "prediction_days": prediction_days,
            "method": method,
            "data_points": len(values),
            "prediction": result[method if method != "ensemble" else "ensemble"],
            "all_predictions": result if method == "ensemble" else None,
            "history": {
                "original": values[-min(30, len(values)):],  # 最近30个原始数据点
                "aggregated": aggregated_data[-min(30, len(aggregated_data)):]  # 最近30个聚合数据点
            }
        }
        
        return prediction_result
        
    def _linear_prediction(
        self, 
        values: List[float], 
        prediction_days: int,
        with_confidence: bool = True
    ) -> Tuple[List[float], Optional[List[Dict[str, float]]]]:
        """
        使用线性回归进行预测
        
        参数:
        - values: 历史数据值
        - prediction_days: 预测天数
        - with_confidence: 是否计算置信区间
        
        返回:
        - 预测值列表和置信区间（可选）
        """
        n = len(values)
        x = list(range(n))
        
        # 计算线性回归
        slope, intercept, r_squared = self._linear_regression(x, values)
        
        # 生成预测值
        future_x = list(range(n, n + prediction_days))
        predictions = [slope * x_i + intercept for x_i in future_x]
        
        # 计算置信区间
        confidence_intervals = None
        if with_confidence:
            # 计算残差标准差
            y_pred = [slope * x_i + intercept for x_i in x]
            residuals = [values[i] - y_pred[i] for i in range(n)]
            residual_std = (sum([r**2 for r in residuals]) / (n - 2)) ** 0.5
            
            # 计算预测的标准误差
            x_mean = sum(x) / n
            x_squared_sum = sum([x_i**2 for x_i in x])
            t_value = 1.96  # 95%置信区间的t值（正态分布近似）
            
            confidence_intervals = []
            for x_i in future_x:
                # 预测的标准误差
                se = residual_std * ((1/n) + ((x_i - x_mean)**2 / (x_squared_sum - n * x_mean**2))) ** 0.5
                # 置信区间
                confidence_intervals.append({
                    "lower": predictions[x_i - n] - t_value * se,
                    "upper": predictions[x_i - n] + t_value * se
                })
                
        return predictions, confidence_intervals
        
    def _arima_prediction(
        self, 
        values: List[float], 
        prediction_days: int,
        with_confidence: bool = True
    ) -> Tuple[List[float], Optional[List[Dict[str, float]]]]:
        """
        使用ARIMA（自回归积分滑动平均模型）进行预测
        
        参数:
        - values: 历史数据值
        - prediction_days: 预测天数
        - with_confidence: 是否计算置信区间
        
        返回:
        - 预测值列表和置信区间（可选）
        """
        # 简化实现：使用指数加权移动平均作为ARIMA的近似
        # 实际项目中应使用专门的时间序列库如statsmodels
        
        # 使用简单指数平滑作为基础预测
        alpha = 0.3  # 平滑因子
        smoothed = [values[0]]
        
        for i in range(1, len(values)):
            smoothed.append(alpha * values[i] + (1 - alpha) * smoothed[i-1])
        
        # 计算最近K个值的趋势
        k = min(10, len(values))
        recent_trend = (smoothed[-1] - smoothed[-k]) / k
        
        # 基于趋势生成预测
        last_value = smoothed[-1]
        predictions = []
        for i in range(prediction_days):
            next_val = last_value + recent_trend
            predictions.append(next_val)
            last_value = next_val
            
        # 计算置信区间
        confidence_intervals = None
        if with_confidence:
            # 计算历史预测的误差
            errors = []
            for i in range(1, len(values)):
                pred = smoothed[i-1] + recent_trend
                actual = values[i]
                errors.append(abs(pred - actual))
                
            # 使用平均绝对误差的1.96倍作为置信区间（近似95%置信度）
            mae = sum(errors) / len(errors) if errors else 0
            interval_width = 1.96 * mae
            
            confidence_intervals = []
            for pred in predictions:
                confidence_intervals.append({
                    "lower": pred - interval_width,
                    "upper": pred + interval_width
                })
                
        return predictions, confidence_intervals
        
    def _prophet_prediction(
        self, 
        values: List[float], 
        time_data: List[Dict],
        prediction_days: int,
        with_confidence: bool = True
    ) -> Tuple[List[float], Optional[List[Dict[str, float]]]]:
        """
        使用Prophet（Facebook开发的时间序列库）的简化版进行预测
        注意：实际使用需要安装fbprophet库
        
        参数:
        - values: 历史数据值
        - time_data: 包含时间信息的数据
        - prediction_days: 预测天数
        - with_confidence: 是否计算置信区间
        
        返回:
        - 预测值列表和置信区间（可选）
        """
        # 这是一个简化的Prophet预测模拟
        # 实际项目中应使用fbprophet库
        
        # 使用周期分解 + 趋势的简化版
        n = len(values)
        
        # 提取趋势组件（使用线性回归）
        x = list(range(n))
        slope, intercept, _ = self._linear_regression(x, values)
        trend = [slope * i + intercept for i in range(n)]
        
        # 计算残差（可能包含季节性和噪声）
        residuals = [values[i] - trend[i] for i in range(n)]
        
        # 计算7天移动平均作为"季节性"模式的近似
        seasonal_period = min(7, n // 2)
        if n > seasonal_period * 2:
            # 通过平均同一周期日的残差来计算季节性模式
            seasonal = [0] * seasonal_period
            counts = [0] * seasonal_period
            
            for i in range(n):
                idx = i % seasonal_period
                seasonal[idx] += residuals[i]
                counts[idx] += 1
                
            seasonal = [s / c if c > 0 else 0 for s, c in zip(seasonal, counts)]
        else:
            seasonal = [0] * seasonal_period
            
        # 生成预测
        predictions = []
        for i in range(prediction_days):
            day = n + i
            # 趋势组件
            trend_comp = slope * day + intercept
            # 季节性组件
            season_comp = seasonal[day % seasonal_period]
            # 预测值 = 趋势 + 季节性
            predictions.append(trend_comp + season_comp)
            
        # 计算置信区间
        confidence_intervals = None
        if with_confidence:
            # 计算模型残差的标准差
            model_residuals = []
            for i in range(n):
                pred = trend[i] + seasonal[i % seasonal_period]
                model_residuals.append(values[i] - pred)
                
            residual_std = (sum([r**2 for r in model_residuals]) / n) ** 0.5
            t_value = 1.96  # 95%置信区间
            
            # 假设误差随时间增加
            confidence_intervals = []
            for i in range(prediction_days):
                # 随时间增加不确定性
                uncertainty = residual_std * (1 + i * 0.1)
                confidence_intervals.append({
                    "lower": predictions[i] - t_value * uncertainty,
                    "upper": predictions[i] + t_value * uncertainty
                })
                
        return predictions, confidence_intervals
        
    def _ensemble_prediction(
        self,
        linear_predictions: List[float],
        arima_predictions: List[float],
        prophet_predictions: List[float],
        prediction_days: int,
        with_confidence: bool = True,
        linear_conf: Optional[List[Dict[str, float]]] = None,
        arima_conf: Optional[List[Dict[str, float]]] = None,
        prophet_conf: Optional[List[Dict[str, float]]] = None
    ) -> Tuple[List[float], Optional[List[Dict[str, float]]]]:
        """
        使用集成方法综合多种预测结果
        
        参数:
        - linear_predictions: 线性回归预测结果
        - arima_predictions: ARIMA预测结果
        - prophet_predictions: Prophet预测结果
        - prediction_days: 预测天数
        - with_confidence: 是否计算置信区间
        - linear_conf: 线性回归置信区间
        - arima_conf: ARIMA置信区间
        - prophet_conf: Prophet置信区间
        
        返回:
        - 集成预测值列表和置信区间（可选）
        """
        # 模型权重（可以根据历史表现动态调整）
        weights = {
            "linear": 0.3,
            "arima": 0.3,
            "prophet": 0.4
        }
        
        # 计算加权平均预测值
        ensemble_predictions = []
        for i in range(prediction_days):
            weighted_sum = (
                weights["linear"] * linear_predictions[i] +
                weights["arima"] * arima_predictions[i] +
                weights["prophet"] * prophet_predictions[i]
            )
            ensemble_predictions.append(weighted_sum)
            
        # 计算集成模型的置信区间
        confidence_intervals = None
        if with_confidence and linear_conf and arima_conf and prophet_conf:
            confidence_intervals = []
            for i in range(prediction_days):
                # 计算加权平均的置信下限
                lower = (
                    weights["linear"] * linear_conf[i]["lower"] +
                    weights["arima"] * arima_conf[i]["lower"] +
                    weights["prophet"] * prophet_conf[i]["lower"]
                )
                
                # 计算加权平均的置信上限
                upper = (
                    weights["linear"] * linear_conf[i]["upper"] +
                    weights["arima"] * arima_conf[i]["upper"] +
                    weights["prophet"] * prophet_conf[i]["upper"]
                )
                
                confidence_intervals.append({"lower": lower, "upper": upper})
                
        return ensemble_predictions, confidence_intervals


# 创建服务实例
device_analysis_service = DeviceAnalysisService() 
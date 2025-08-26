"""
健康数据预警服务
提供健康数据阈值管理和健康数据异常检测功能
"""
from datetime import datetime
from typing import Dict, Any, List, Optional, Union
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase, AsyncIOMotorCollection

from app.models.health_data_threshold import HealthDataThreshold, HealthDataAlert
from app.schemas.health_data_threshold import (
    ThresholdCreate, ThresholdUpdate, ThresholdResponse,
    AlertCreate, AlertUpdate, AlertResponse, AlertStatistics,
    BloodPressureThresholdCreate, SingleValueThresholdCreate
)


class HealthAlertService:
    """
    健康数据预警服务
    用于管理健康数据阈值配置和处理健康数据异常检测
    """
    
    def __init__(self, db: AsyncIOMotorDatabase):
        """初始化服务
        
        Args:
            db: MongoDB数据库连接
        """
        self.db = db
        # 阈值配置集合
        self.thresholds: AsyncIOMotorCollection = db[HealthDataThreshold.collection_name]
        # 健康数据预警集合
        self.alerts: AsyncIOMotorCollection = db[HealthDataAlert.collection_name]
        
    async def initialize(self):
        """初始化服务，创建索引等"""
        # 为阈值配置创建索引
        await self.thresholds.create_index([("data_type", 1)])
        await self.thresholds.create_index([("vital_type", 1)])
        await self.thresholds.create_index([("test_name", 1)])
        await self.thresholds.create_index([("is_default", 1)])
        await self.thresholds.create_index([("is_active", 1)])
        
        # 为健康数据预警创建索引
        await self.alerts.create_index([("patient_id", 1)])
        await self.alerts.create_index([("alert_level", 1)])
        await self.alerts.create_index([("status", 1)])
        await self.alerts.create_index([("data_type", 1)])
        await self.alerts.create_index([("vital_type", 1)])
        await self.alerts.create_index([("recorded_at", -1)])
    
    # -------- 阈值管理相关方法 --------
    
    async def create_threshold(self, data: ThresholdCreate) -> ThresholdResponse:
        """创建通用阈值配置
        
        Args:
            data: 阈值创建请求数据
            
        Returns:
            ThresholdResponse: 创建成功的阈值响应
        """
        # 创建阈值对象
        threshold = HealthDataThreshold(
            name=data.name,
            data_type=data.data_type,
            vital_type=data.vital_type,
            test_name=data.test_name,
            normal_range=data.normal_range,
            warning_range=data.warning_range,
            critical_range=data.critical_range,
            unit=data.unit,
            description=data.description,
            applies_to=data.applies_to,
            created_by=data.created_by,
            is_active=data.is_active,
            is_default=data.is_default,
            metadata=data.metadata
        )
        
        # 插入数据库
        result = await self.thresholds.insert_one(threshold.to_mongo())
        
        # 更新ID
        threshold._id = str(result.inserted_id)
        
        # 返回响应
        return self._map_threshold_to_response(threshold)
    
    async def create_blood_pressure_threshold(self, data: BloodPressureThresholdCreate) -> ThresholdResponse:
        """创建血压阈值配置
        
        Args:
            data: 血压阈值创建请求数据
            
        Returns:
            ThresholdResponse: 创建成功的阈值响应
        """
        # 使用HealthDataThreshold提供的工厂方法创建血压阈值
        threshold = HealthDataThreshold.create_blood_pressure_threshold(
            name=data.name,
            normal_systolic=data.normal_systolic,
            normal_diastolic=data.normal_diastolic,
            warning_systolic=data.warning_systolic,
            warning_diastolic=data.warning_diastolic,
            critical_systolic=data.critical_systolic,
            critical_diastolic=data.critical_diastolic,
            applies_to=data.applies_to,
            description=data.description,
            created_by=data.created_by,
            is_default=data.is_default
        )
        
        # 插入数据库
        result = await self.thresholds.insert_one(threshold.to_mongo())
        
        # 更新ID
        threshold._id = str(result.inserted_id)
        
        # 返回响应
        return self._map_threshold_to_response(threshold)
    
    async def create_single_value_threshold(self, data: SingleValueThresholdCreate) -> ThresholdResponse:
        """创建单值阈值配置（如心率、血糖等）
        
        Args:
            data: 单值阈值创建请求数据
            
        Returns:
            ThresholdResponse: 创建成功的阈值响应
        """
        # 根据不同的vital_type选择合适的工厂方法
        if data.vital_type == "heart_rate":
            threshold = HealthDataThreshold.create_heart_rate_threshold(
                name=data.name,
                normal_range=data.normal_range,
                warning_range=data.warning_range,
                critical_range=data.critical_range,
                applies_to=data.applies_to,
                description=data.description,
                created_by=data.created_by,
                is_default=data.is_default
            )
        elif data.vital_type == "blood_glucose":
            threshold = HealthDataThreshold.create_blood_glucose_threshold(
                name=data.name,
                normal_range=data.normal_range,
                warning_range=data.warning_range,
                critical_range=data.critical_range,
                timing="fasting",  # 默认为空腹
                applies_to=data.applies_to,
                description=data.description,
                created_by=data.created_by,
                is_default=data.is_default
            )
        elif data.vital_type == "body_temperature":
            threshold = HealthDataThreshold.create_body_temperature_threshold(
                name=data.name,
                normal_range=data.normal_range,
                warning_range=data.warning_range,
                critical_range=data.critical_range,
                applies_to=data.applies_to,
                description=data.description,
                created_by=data.created_by,
                is_default=data.is_default
            )
        elif data.vital_type == "respiratory_rate":
            threshold = HealthDataThreshold.create_respiratory_rate_threshold(
                name=data.name,
                normal_range=data.normal_range,
                warning_range=data.warning_range,
                critical_range=data.critical_range,
                applies_to=data.applies_to,
                description=data.description,
                created_by=data.created_by,
                is_default=data.is_default
            )
        elif data.vital_type == "oxygen_saturation":
            threshold = HealthDataThreshold.create_oxygen_saturation_threshold(
                name=data.name,
                normal_range=data.normal_range,
                warning_range=data.warning_range,
                critical_range=data.critical_range,
                applies_to=data.applies_to,
                description=data.description,
                created_by=data.created_by,
                is_default=data.is_default
            )
        else:
            # 对于其他类型，创建通用阈值
            threshold = HealthDataThreshold(
                name=data.name,
                data_type="vital_sign",
                vital_type=data.vital_type,
                normal_range=data.normal_range,
                warning_range=data.warning_range,
                critical_range=data.critical_range,
                unit=data.unit,
                description=data.description,
                applies_to=data.applies_to,
                created_by=data.created_by,
                is_default=data.is_default
            )
        
        # 插入数据库
        result = await self.thresholds.insert_one(threshold.to_mongo())
        
        # 更新ID
        threshold._id = str(result.inserted_id)
        
        # 返回响应
        return self._map_threshold_to_response(threshold)
    
    async def get_threshold(self, threshold_id: str) -> Optional[ThresholdResponse]:
        """获取阈值配置
        
        Args:
            threshold_id: 阈值配置ID
            
        Returns:
            Optional[ThresholdResponse]: 阈值响应，不存在则返回None
        """
        # 查询数据库
        threshold_doc = await self.thresholds.find_one({"_id": ObjectId(threshold_id)})
        if not threshold_doc:
            return None
        
        # 创建对象并返回响应
        threshold = HealthDataThreshold.from_mongo(threshold_doc)
        return self._map_threshold_to_response(threshold)
    
    async def update_threshold(self, threshold_id: str, data: ThresholdUpdate) -> Optional[ThresholdResponse]:
        """更新阈值配置
        
        Args:
            threshold_id: 阈值配置ID
            data: 更新请求数据
            
        Returns:
            Optional[ThresholdResponse]: 更新后的阈值响应，不存在则返回None
        """
        # 查询阈值配置
        threshold_doc = await self.thresholds.find_one({"_id": ObjectId(threshold_id)})
        if not threshold_doc:
            return None
        
        # 创建对象
        threshold = HealthDataThreshold.from_mongo(threshold_doc)
        
        # 更新字段
        update_data = {}
        if data.name is not None:
            update_data["name"] = data.name
            threshold.name = data.name
        if data.normal_range is not None:
            update_data["normal_range"] = data.normal_range
            threshold.normal_range = data.normal_range
        if data.warning_range is not None:
            update_data["warning_range"] = data.warning_range
            threshold.warning_range = data.warning_range
        if data.critical_range is not None:
            update_data["critical_range"] = data.critical_range
            threshold.critical_range = data.critical_range
        if data.description is not None:
            update_data["description"] = data.description
            threshold.description = data.description
        if data.applies_to is not None:
            update_data["applies_to"] = data.applies_to
            threshold.applies_to = data.applies_to
        if data.is_active is not None:
            update_data["is_active"] = data.is_active
            threshold.is_active = data.is_active
        if data.is_default is not None:
            update_data["is_default"] = data.is_default
            threshold.is_default = data.is_default
        if data.metadata is not None:
            update_data["metadata"] = data.metadata
            threshold.metadata = data.metadata
        if data.updated_by is not None:
            update_data["updated_by"] = data.updated_by
            threshold.updated_by = data.updated_by
        
        # 更新时间
        update_data["updated_at"] = datetime.utcnow()
        threshold.updated_at = update_data["updated_at"]
        
        # 更新数据库
        if update_data:
            await self.thresholds.update_one(
                {"_id": ObjectId(threshold_id)},
                {"$set": update_data}
            )
        
        # 返回响应
        return self._map_threshold_to_response(threshold)
    
    async def delete_threshold(self, threshold_id: str) -> bool:
        """删除阈值配置
        
        Args:
            threshold_id: 阈值配置ID
            
        Returns:
            bool: 删除成功返回True，不存在返回False
        """
        # 查询阈值配置
        threshold_doc = await self.thresholds.find_one({"_id": ObjectId(threshold_id)})
        if not threshold_doc:
            return False
        
        # 删除阈值配置
        await self.thresholds.delete_one({"_id": ObjectId(threshold_id)})
        
        return True
    
    async def list_thresholds(
        self,
        data_type: Optional[str] = None,
        vital_type: Optional[str] = None,
        test_name: Optional[str] = None,
        is_active: Optional[bool] = None,
        is_default: Optional[bool] = None,
        skip: int = 0,
        limit: int = 100
    ) -> List[ThresholdResponse]:
        """列出阈值配置
        
        Args:
            data_type: 数据类型过滤
            vital_type: 生命体征类型过滤
            test_name: 实验室检查名称过滤
            is_active: 是否启用过滤
            is_default: 是否默认配置过滤
            skip: 分页偏移量
            limit: 每页数量
            
        Returns:
            List[ThresholdResponse]: 阈值响应列表
        """
        # 构建查询条件
        query = {}
        if data_type:
            query["data_type"] = data_type
        if vital_type:
            query["vital_type"] = vital_type
        if test_name:
            query["test_name"] = test_name
        if is_active is not None:
            query["is_active"] = is_active
        if is_default is not None:
            query["is_default"] = is_default
        
        # 查询数据库
        cursor = self.thresholds.find(query).sort("name", 1).skip(skip).limit(limit)
        threshold_list = await cursor.to_list(length=limit)
        
        # 转换为响应对象
        return [self._map_threshold_to_response(HealthDataThreshold.from_mongo(doc)) for doc in threshold_list]
    
    async def find_applicable_threshold(
        self,
        data_type: str,
        vital_type: Optional[str] = None,
        test_name: Optional[str] = None,
        patient_data: Optional[Dict[str, Any]] = None
    ) -> Optional[HealthDataThreshold]:
        """查找适用的阈值配置
        
        Args:
            data_type: 数据类型
            vital_type: 生命体征类型
            test_name: 实验室检查名称
            patient_data: 患者数据（用于匹配applies_to条件）
            
        Returns:
            Optional[HealthDataThreshold]: 适用的阈值配置，不存在则返回None
        """
        # 构建基本查询条件
        query = {
            "data_type": data_type,
            "is_active": True
        }
        
        if vital_type:
            query["vital_type"] = vital_type
        if test_name:
            query["test_name"] = test_name
        
        # 首先尝试查找非默认配置
        non_default_query = {**query, "is_default": False}
        non_default_doc = await self.thresholds.find_one(non_default_query)
        
        if non_default_doc:
            threshold = HealthDataThreshold.from_mongo(non_default_doc)
            
            # 检查applies_to条件是否匹配
            if patient_data and threshold.applies_to:
                for key, condition in threshold.applies_to.items():
                    if key in patient_data:
                        patient_value = patient_data[key]
                        # 范围条件检查
                        if isinstance(condition, dict) and "min" in condition and "max" in condition:
                            if patient_value < condition.get("min", 0) or patient_value > condition.get("max", 999999):
                                continue
                        # 精确值检查
                        elif patient_value != condition:
                            continue
                    else:
                        continue
            
            return threshold
        
        # 如果没有找到非默认配置，尝试查找默认配置
        default_query = {**query, "is_default": True}
        default_doc = await self.thresholds.find_one(default_query)
        
        if default_doc:
            return HealthDataThreshold.from_mongo(default_doc)
        
        return None
    
    def _map_threshold_to_response(self, threshold: HealthDataThreshold) -> ThresholdResponse:
        """将阈值对象映射为响应对象
        
        Args:
            threshold: 阈值对象
            
        Returns:
            ThresholdResponse: 阈值响应对象
        """
        return ThresholdResponse(
            id=threshold._id,
            name=threshold.name,
            data_type=threshold.data_type,
            vital_type=threshold.vital_type,
            test_name=threshold.test_name,
            normal_range=threshold.normal_range,
            warning_range=threshold.warning_range,
            critical_range=threshold.critical_range,
            unit=threshold.unit,
            description=threshold.description,
            applies_to=threshold.applies_to,
            is_active=threshold.is_active,
            is_default=threshold.is_default,
            metadata=threshold.metadata,
            created_by=threshold.created_by,
            updated_by=threshold.updated_by,
            created_at=threshold.created_at,
            updated_at=threshold.updated_at
        )
        
    # -------- 健康数据异常检测相关方法 --------
    
    async def check_health_data(
        self,
        health_data_id: str,
        patient_id: str,
        data_type: str,
        vital_type: Optional[str] = None,
        test_name: Optional[str] = None,
        value: Union[float, Dict[str, float]] = None,
        recorded_at: Optional[datetime] = None,
        patient_data: Optional[Dict[str, Any]] = None,
        unit: Optional[str] = None
    ) -> Dict[str, Any]:
        """检查健康数据是否在正常范围内
        
        Args:
            health_data_id: 健康数据ID
            patient_id: 患者ID
            data_type: 数据类型
            vital_type: 生命体征类型
            test_name: 实验室检查名称
            value: 数据值
            recorded_at: 记录时间
            patient_data: 患者信息（用于匹配阈值条件）
            unit: 数据单位
            
        Returns:
            Dict[str, Any]: 检查结果，包含状态信息
        """
        # 查找适用的阈值配置
        threshold = await self.find_applicable_threshold(
            data_type=data_type,
            vital_type=vital_type,
            test_name=test_name,
            patient_data=patient_data
        )
        
        if not threshold:
            return {
                "status": "unknown",
                "message": "未找到适用的阈值配置",
                "value": value,
                "threshold_id": None
            }
        
        # 检查数值是否在阈值范围内
        check_result = threshold.check_value(value)
        check_result["threshold_id"] = threshold._id
        
        # 如果检测到异常，创建预警
        if check_result["status"] in ["warning", "critical"]:
            alert = HealthDataAlert.create_from_health_data(
                health_data_id=health_data_id,
                patient_id=patient_id,
                data_type=data_type,
                vital_type=vital_type,
                value=value,
                unit=unit or threshold.unit,
                check_result=check_result,
                threshold_id=threshold._id,
                recorded_at=recorded_at
            )
            # 保存预警到数据库
            await self.alerts.insert_one(alert.to_mongo())
            check_result["alert_id"] = alert._id
        
        return check_result
    
    async def create_alert(self, data: AlertCreate) -> AlertResponse:
        """手动创建预警
        
        Args:
            data: 预警创建请求数据
            
        Returns:
            AlertResponse: 创建成功的预警响应
        """
        # 创建预警对象
        alert = HealthDataAlert(
            health_data_id=data.health_data_id,
            patient_id=data.patient_id,
            data_type=data.data_type,
            vital_type=data.vital_type,
            test_name=data.test_name,
            value=data.value,
            unit=data.unit,
            threshold_id=data.threshold_id,
            alert_level=data.alert_level,
            status=data.status,
            recorded_at=data.recorded_at,
            metadata=data.metadata
        )
        
        # 插入数据库
        result = await self.alerts.insert_one(alert.to_mongo())
        
        # 更新ID
        alert._id = str(result.inserted_id)
        
        # 返回响应
        return self._map_alert_to_response(alert)
    
    async def get_alert(self, alert_id: str) -> Optional[AlertResponse]:
        """获取预警详情
        
        Args:
            alert_id: 预警ID
            
        Returns:
            Optional[AlertResponse]: 预警响应，不存在则返回None
        """
        # 查询数据库
        alert_doc = await self.alerts.find_one({"_id": ObjectId(alert_id)})
        if not alert_doc:
            return None
        
        # 创建对象并返回响应
        alert = HealthDataAlert.from_mongo(alert_doc)
        return self._map_alert_to_response(alert)
    
    async def update_alert(self, alert_id: str, data: AlertUpdate) -> Optional[AlertResponse]:
        """更新预警状态
        
        Args:
            alert_id: 预警ID
            data: 更新请求数据
            
        Returns:
            Optional[AlertResponse]: 更新后的预警响应，不存在则返回None
        """
        # 查询预警
        alert_doc = await self.alerts.find_one({"_id": ObjectId(alert_id)})
        if not alert_doc:
            return None
        
        # 创建对象
        alert = HealthDataAlert.from_mongo(alert_doc)
        
        # 更新字段
        update_data = {}
        if data.status is not None:
            update_data["status"] = data.status
            alert.status = data.status
        if data.resolved_at is not None:
            update_data["resolved_at"] = data.resolved_at
            alert.resolved_at = data.resolved_at
        if data.resolved_by is not None:
            update_data["resolved_by"] = data.resolved_by
            alert.resolved_by = data.resolved_by
        if data.resolution_notes is not None:
            update_data["resolution_notes"] = data.resolution_notes
            alert.resolution_notes = data.resolution_notes
        
        # 更新时间
        update_data["updated_at"] = datetime.utcnow()
        alert.updated_at = update_data["updated_at"]
        
        # 如果状态变为已解决，但未提供解决时间，则设置为当前时间
        if data.status == "resolved" and data.resolved_at is None:
            update_data["resolved_at"] = update_data["updated_at"]
            alert.resolved_at = update_data["resolved_at"]
        
        # 更新数据库
        if update_data:
            await self.alerts.update_one(
                {"_id": ObjectId(alert_id)},
                {"$set": update_data}
            )
        
        # 返回响应
        return self._map_alert_to_response(alert)
    
    async def list_alerts(
        self,
        patient_id: Optional[str] = None,
        data_type: Optional[str] = None,
        vital_type: Optional[str] = None,
        alert_level: Optional[str] = None,
        status: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        skip: int = 0,
        limit: int = 100
    ) -> List[AlertResponse]:
        """列出预警
        
        Args:
            patient_id: 患者ID过滤
            data_type: 数据类型过滤
            vital_type: 生命体征类型过滤
            alert_level: 预警级别过滤
            status: 状态过滤
            start_date: 开始日期过滤
            end_date: 结束日期过滤
            skip: 分页偏移量
            limit: 每页数量
            
        Returns:
            List[AlertResponse]: 预警响应列表
        """
        # 构建查询条件
        query = {}
        if patient_id:
            query["patient_id"] = patient_id
        if data_type:
            query["data_type"] = data_type
        if vital_type:
            query["vital_type"] = vital_type
        if alert_level:
            query["alert_level"] = alert_level
        if status:
            query["status"] = status
        
        # 日期范围查询
        date_query = {}
        if start_date:
            date_query["$gte"] = start_date
        if end_date:
            date_query["$lte"] = end_date
        if date_query:
            query["recorded_at"] = date_query
        
        # 查询数据库
        cursor = self.alerts.find(query).sort("recorded_at", -1).skip(skip).limit(limit)
        alert_list = await cursor.to_list(length=limit)
        
        # 转换为响应对象
        return [self._map_alert_to_response(HealthDataAlert.from_mongo(doc)) for doc in alert_list]
    
    async def resolve_alert(
        self,
        alert_id: str,
        resolved_by: str,
        resolution_notes: Optional[str] = None
    ) -> Optional[AlertResponse]:
        """解决预警
        
        Args:
            alert_id: 预警ID
            resolved_by: 解决人ID
            resolution_notes: 解决备注
            
        Returns:
            Optional[AlertResponse]: 更新后的预警响应，不存在则返回None
        """
        # 更新预警状态
        update_data = {
            "status": "resolved",
            "resolved_at": datetime.utcnow(),
            "resolved_by": resolved_by,
            "updated_at": datetime.utcnow()
        }
        
        if resolution_notes:
            update_data["resolution_notes"] = resolution_notes
        
        # 更新数据库
        result = await self.alerts.update_one(
            {"_id": ObjectId(alert_id)},
            {"$set": update_data}
        )
        
        if result.modified_count == 0:
            # 检查是否是因为记录不存在
            alert = await self.alerts.find_one({"_id": ObjectId(alert_id)})
            if not alert:
                return None
        
        # 获取更新后的预警
        return await self.get_alert(alert_id)
    
    async def ignore_alert(
        self,
        alert_id: str,
        resolved_by: str,
        resolution_notes: Optional[str] = None
    ) -> Optional[AlertResponse]:
        """忽略预警
        
        Args:
            alert_id: 预警ID
            resolved_by: 处理人ID
            resolution_notes: 处理备注
            
        Returns:
            Optional[AlertResponse]: 更新后的预警响应，不存在则返回None
        """
        # 更新预警状态
        update_data = {
            "status": "ignored",
            "resolved_at": datetime.utcnow(),
            "resolved_by": resolved_by,
            "updated_at": datetime.utcnow()
        }
        
        if resolution_notes:
            update_data["resolution_notes"] = resolution_notes
        
        # 更新数据库
        result = await self.alerts.update_one(
            {"_id": ObjectId(alert_id)},
            {"$set": update_data}
        )
        
        if result.modified_count == 0:
            # 检查是否是因为记录不存在
            alert = await self.alerts.find_one({"_id": ObjectId(alert_id)})
            if not alert:
                return None
        
        # 获取更新后的预警
        return await self.get_alert(alert_id)
    
    async def get_patient_alerts_stats(self, patient_id: str) -> AlertStatistics:
        """获取患者预警统计
        
        Args:
            patient_id: 患者ID
            
        Returns:
            AlertStatistics: 预警统计信息
        """
        # 基本查询条件
        base_query = {"patient_id": patient_id}
        
        # 总数
        total = await self.alerts.count_documents(base_query)
        
        # 按状态统计
        active_count = await self.alerts.count_documents({**base_query, "status": "active"})
        resolved_count = await self.alerts.count_documents({**base_query, "status": "resolved"})
        ignored_count = await self.alerts.count_documents({**base_query, "status": "ignored"})
        
        # 按级别统计
        critical_count = await self.alerts.count_documents({**base_query, "alert_level": "critical"})
        warning_count = await self.alerts.count_documents({**base_query, "alert_level": "warning"})
        
        # 按类型统计
        by_type = {}
        pipeline = [
            {"$match": base_query},
            {"$group": {"_id": "$data_type", "count": {"$sum": 1}}}
        ]
        async for group in self.alerts.aggregate(pipeline):
            by_type[group["_id"]] = group["count"]
        
        # 返回统计结果
        return AlertStatistics(
            total=total,
            active=active_count,
            resolved=resolved_count,
            ignored=ignored_count,
            critical=critical_count,
            warning=warning_count,
            by_type=by_type,
            by_patient={patient_id: total}
        )
    
    async def get_alerts_stats(self) -> AlertStatistics:
        """获取全局预警统计
        
        Args:
            无
            
        Returns:
            AlertStatistics: 预警统计信息
        """
        # 总数
        total = await self.alerts.count_documents({})
        
        # 按状态统计
        active_count = await self.alerts.count_documents({"status": "active"})
        resolved_count = await self.alerts.count_documents({"status": "resolved"})
        ignored_count = await self.alerts.count_documents({"status": "ignored"})
        
        # 按级别统计
        critical_count = await self.alerts.count_documents({"alert_level": "critical"})
        warning_count = await self.alerts.count_documents({"alert_level": "warning"})
        
        # 按类型统计
        by_type = {}
        type_pipeline = [
            {"$group": {"_id": "$data_type", "count": {"$sum": 1}}}
        ]
        async for group in self.alerts.aggregate(type_pipeline):
            by_type[group["_id"]] = group["count"]
        
        # 按患者统计
        by_patient = {}
        patient_pipeline = [
            {"$group": {"_id": "$patient_id", "count": {"$sum": 1}}}
        ]
        async for group in self.alerts.aggregate(patient_pipeline):
            by_patient[group["_id"]] = group["count"]
        
        # 返回统计结果
        return AlertStatistics(
            total=total,
            active=active_count,
            resolved=resolved_count,
            ignored=ignored_count,
            critical=critical_count,
            warning=warning_count,
            by_type=by_type,
            by_patient=by_patient
        )
    
    def _map_alert_to_response(self, alert: HealthDataAlert) -> AlertResponse:
        """将预警对象映射为响应对象
        
        Args:
            alert: 预警对象
            
        Returns:
            AlertResponse: 预警响应对象
        """
        return AlertResponse(
            id=alert._id,
            health_data_id=alert.health_data_id,
            patient_id=alert.patient_id,
            data_type=alert.data_type,
            vital_type=alert.vital_type,
            test_name=alert.test_name,
            value=alert.value,
            unit=alert.unit,
            threshold_id=alert.threshold_id,
            alert_level=alert.alert_level,
            status=alert.status,
            recorded_at=alert.recorded_at,
            created_at=alert.created_at,
            updated_at=alert.updated_at,
            resolved_at=alert.resolved_at,
            resolved_by=alert.resolved_by,
            resolution_notes=alert.resolution_notes,
            metadata=alert.metadata
        ) 
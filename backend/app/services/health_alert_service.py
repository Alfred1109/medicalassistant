"""
健康数据预警服务
提供健康数据阈值管理和健康数据异常检测功能
"""
import logging
import hashlib
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Union
from bson import ObjectId, json_util
from motor.motor_asyncio import AsyncIOMotorDatabase, AsyncIOMotorCollection
from fastapi import HTTPException

from app.core.patient_access import load_patient_doc, patient_assignment_field
from app.core.patient_identity import resolve_unique_account
from app.models.health_data_threshold import HealthDataThreshold, HealthDataAlert
from app.schemas.health_data_threshold import (
    ThresholdCreate, ThresholdUpdate, ThresholdResponse,
    AlertCreate, AlertUpdate, AlertResponse, AlertStatistics,
    BloodPressureThresholdCreate, SingleValueThresholdCreate
)
from app.services.notification_service import NotificationService
from app.services.review_state_machine import commit_versioned_change, review_conflict

logger = logging.getLogger(__name__)

# 预警级别 → 通知优先级（前端 priority 取值：low/normal/high/urgent）。
ALERT_PRIORITIES = {"critical": "urgent", "warning": "high"}
# 预警级别 → 文案标签。
ALERT_LEVEL_LABELS = {"critical": "危急", "warning": "警告"}
# 生命体征类型 → 文案标签（构造摘要时用；未登记的类型原样呈现）。
ALERT_TYPE_LABELS = {
    "blood_pressure": "血压",
    "heart_rate": "心率",
    "blood_glucose": "血糖",
    "body_temperature": "体温",
    "respiratory_rate": "呼吸频率",
    "oxygen_saturation": "血氧饱和度",
}
# 医护通知的固定身份（与提醒链路的 system:followup-reminders 同款约定）。
ALERT_SENDER_ID = "system:health-alerts"
ALERT_SENDER_NAME = "健康预警"


def _alert_level(alert: Dict[str, Any]) -> str:
    """预警级别取值（枚举或字符串统一为字符串）。"""
    level = alert.get("alert_level")
    return getattr(level, "value", level) or ""


def _format_occurred_at(value) -> str:
    """预警发生时间（统一按 UTC 呈现，避免时区歧义）。"""
    if not isinstance(value, datetime):
        return "未知时间"
    moment = value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return moment.strftime("%Y-%m-%d %H:%M UTC")


def _format_number(value) -> str:
    """数值文案（整数值的浮点表示不保留小数尾巴）。"""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


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
        # 患者读取盘点（T11 2026-11-14）：本服务不读 users/patients——patient_id
        # 是调用方传入的字面量，直存直查自有 alerts 集合（无患者资料/存在性/
        # 归属校验，授权由路由层承担）。canonical 波段若患者 ID 形态变化，
        # alerts 内的历史字面量迁移属该集合自身的数据改造，不在患者适配器范围。
        
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

    async def _responsible_staff(self, patient_id: str):
        """该患者的责任医护账号（doctor / health_manager）。

        归属判定复用内核 app.core.patient_access：患者文档按当前域读取
        （load_patient_doc，含可用性判定），角色对应的归属字段由
        patient_assignment_field 给出（与患者关联写入路径同源），账号身份
        解析走 core.patient_identity.resolve_unique_account（同键多文档
        fail-closed）。此处不新增任何归属规则。
        """
        patient = await load_patient_doc(self.db, patient_id)
        accounts = []
        for role in ("doctor", "health_manager"):
            field = patient_assignment_field(role)
            assignments = patient.get(field)
            if not isinstance(assignments, list):
                continue
            for identifier in assignments:
                account = await resolve_unique_account(self.db, identifier)
                if (account and account.get("is_active") is True
                        and account.get("role") == role):
                    accounts.append(account)
        return patient, accounts

    def _alert_summary(self, alert: Dict[str, Any]) -> str:
        """预警类型 + 关键数值（含单位）的一句话摘要。"""
        message = (alert.get("metadata") or {}).get("message")
        if message:
            return str(message)
        label = (alert.get("metadata") or {}).get("metric_name") or \
            ALERT_TYPE_LABELS.get(alert.get("vital_type")) or alert.get("vital_type") or \
            alert.get("test_name") or alert.get("data_type") or "健康数据"
        value = alert.get("value")
        if isinstance(value, dict):
            text = "/".join(_format_number(item) for item in value.values())
        else:
            text = _format_number(value)
        return f"{label} {text}{alert.get('unit') or ''}"

    def _alert_content(self, alert: Dict[str, Any], patient_name: Optional[str]) -> str:
        """预警通知文案：预警类型 + 关键数值（含单位）+ 发生时间 + 患者显示名。"""
        level = ALERT_LEVEL_LABELS.get(_alert_level(alert), "提醒")
        return (f"{patient_name or '该患者'}触发健康预警：{self._alert_summary(alert)}"
                f"（预警级别：{level}，发生时间：{_format_occurred_at(alert.get('recorded_at'))}）。"
                "请及时查看并处理。")

    async def _already_notified(self, alert: Dict[str, Any]) -> bool:
        """同一业务预警是否已通知过。

        幂等键 = 患者 + 数据类型 + 健康数据 ID + 预警级别（ICF 指标另计
        metric_key）。阈值对同一份健康数据的重复命中会生成多个预警文档，
        按文档去重会让医护被反复轰炸；按业务身份去重后，同一份数据同一
        级别只通知一次，已处理（resolved/ignored）后的再次越界会重新通知。
        """
        identity = {
            "patient_id": alert.get("patient_id"),
            "data_type": alert.get("data_type"),
            "health_data_id": alert.get("health_data_id"),
            "alert_level": _alert_level(alert),
        }
        if alert.get("vital_type"):
            identity["vital_type"] = alert["vital_type"]
        if alert.get("test_name"):
            identity["test_name"] = alert["test_name"]
        metric_key = (alert.get("metadata") or {}).get("metric_key")
        if metric_key:
            identity["metadata.metric_key"] = metric_key
        alert_id = str(alert["_id"])
        candidates = [alert_id]
        siblings = await self.alerts.find(
            {**identity, "status": "active"}).to_list(length=None)
        candidates.extend(str(doc["_id"]) for doc in siblings
                          if str(doc["_id"]) != alert_id)
        existing = await self.db.notifications.find_one({
            "related_entity_type": "health_alert",
            "related_entity_id": {"$in": candidates}})
        return existing is not None

    async def _notify_responsible_staff(self, alert: Dict[str, Any]) -> None:
        """预警产生后触达该患者的责任医护。

        best-effort：解析不到责任医护（未分配、患者不存在、域状态异常）或
        投递失败时只记日志，绝不抛错、绝不阻断预警本身的创建。
        """
        try:
            patient, accounts = await self._responsible_staff(alert.get("patient_id"))
        except Exception:
            logger.warning("预警责任医护解析失败，跳过医护通知：alert_id=%s patient_id=%s",
                           alert.get("_id"), alert.get("patient_id"), exc_info=True)
            return
        if not accounts:
            logger.info("预警无责任医护，跳过医护通知：alert_id=%s patient_id=%s",
                        alert.get("_id"), alert.get("patient_id"))
            return
        if await self._already_notified(alert):
            return
        content = self._alert_content(alert, patient.get("name"))
        for account in accounts:
            try:
                await NotificationService.create_notification(
                    self.db,
                    title="健康预警",
                    content=content,
                    sender_id=ALERT_SENDER_ID,
                    sender_name=ALERT_SENDER_NAME,
                    sender_role="system",
                    recipient_id=str(account["_id"]),
                    notification_type="health_alert",
                    priority=ALERT_PRIORITIES.get(_alert_level(alert), "normal"),
                    related_entity_id=str(alert["_id"]),
                    related_entity_type="health_alert",
                )
            except Exception:
                logger.warning("预警通知投递失败，预警本身不受影响：alert_id=%s recipient=%s",
                               alert.get("_id"), account.get("_id"), exc_info=True)

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
            document = alert.to_mongo()
            await self.alerts.insert_one(document)
            check_result["alert_id"] = alert._id
            # 触达责任医护（统一经 NotificationService；失败不影响预警本身）
            await self._notify_responsible_staff(document)

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
        document = alert.to_mongo()
        result = await self.alerts.insert_one(document)

        # 更新ID
        alert._id = str(result.inserted_id)

        # 触达责任医护（统一经 NotificationService；失败不影响预警本身）
        await self._notify_responsible_staff(document)

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
    
    async def update_alert(self, alert_id: str, data: AlertUpdate, *, actor_id=None) -> Optional[AlertResponse]:
        """All three-state edits use the same CAS and atomic disposition history."""
        changes = data.model_dump(exclude_none=True, exclude={"expected_version", "request_id"})
        return await self._change_alert(alert_id, changes, actor_id=actor_id,
            expected_version=data.expected_version, request_id=data.request_id)

    async def _change_alert(self, alert_id, changes, *, actor_id, expected_version=None, request_id=None):
        row = await self.alerts.find_one({"_id": ObjectId(alert_id)})
        if row is None:
            return None
        version = 0 if row.get("version") is None else row["version"]
        expected = version if expected_version is None else expected_version
        if (type(version) is not int or version < 0 or type(expected) is not int or expected < 0):
            raise review_conflict("ALERT_VERSION_CONFLICT", "预警版本无效，请核实存量记录")
        fingerprint = hashlib.sha256(json_util.dumps(
            [changes, expected_version], sort_keys=True).encode()).hexdigest()

        def replay(document):
            if request_id is None:
                return False
            for event in document.get("timeline", []):
                if event.get("request_id") == request_id and event.get("actor_id") == actor_id:
                    if event.get("fingerprint") != fingerprint:
                        raise review_conflict("ALERT_IDEMPOTENCY_CONFLICT", "相同请求标识不能用于不同内容")
                    return True
            return False
        
        if replay(row):
            # A receipt prevents reapplying an operation; the response is the current resource.
            return self._map_alert_to_response(HealthDataAlert.from_mongo(row))
        now = datetime.utcnow()
        values = {**changes, "updated_at": now}
        if changes.get("status") in {"resolved", "ignored"} and changes.get("resolved_at") is None:
            values["resolved_at"] = now
        event = {"actor_id": actor_id, "at": now, "from_status": row["status"],
                 "to_status": changes.get("status", row["status"]), "version": expected + 1,
                 "changes": changes}
        if request_id is not None:
            event.update(request_id=request_id, fingerprint=fingerprint)
        try:
            await commit_versioned_change(self.alerts, row, expected_version=expected,
                changes=values, version_field="version", history_field="timeline", event=event,
                allow_missing_version=True,
                conflict_error=lambda: review_conflict("ALERT_VERSION_CONFLICT", "预警已变化，请刷新后操作"))
        except HTTPException as exc:
            if not isinstance(exc.detail, dict) or exc.detail.get("code") != "ALERT_VERSION_CONFLICT":
                raise
            # A concurrent identical retry may have committed the same receipt.
            latest = await self.alerts.find_one({"_id": row["_id"]}) if request_id else None
            if latest and replay(latest):
                return self._map_alert_to_response(HealthDataAlert.from_mongo(latest))
            raise
        row.update(values, version=expected + 1)
        row["timeline"] = [*row.get("timeline", []), event]
        return self._map_alert_to_response(HealthDataAlert.from_mongo(row))
    
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
        limit: int = 100,
        patient_ids: Optional[List[str]] = None
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
            patient_ids: 患者ID集合过滤（T76 授权收口：医护未传 patient_id 时
                由路由层按 assigned_scope_ids 收敛范围后传入）

        Returns:
            List[AlertResponse]: 预警响应列表
        """
        # 构建查询条件
        query = {}
        if patient_id:
            query["patient_id"] = patient_id
        elif patient_ids is not None:
            query["patient_id"] = {"$in": list(patient_ids)}
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
    
    async def resolve_alert(self, alert_id: str, resolved_by: str,
                            resolution_notes: Optional[str] = None, *,
                            expected_version=None, request_id=None) -> Optional[AlertResponse]:
        return await self._change_alert(alert_id,
            {"status": "resolved", "resolved_by": resolved_by,
             **({"resolution_notes": resolution_notes} if resolution_notes else {})},
            actor_id=resolved_by, expected_version=expected_version, request_id=request_id)

    async def ignore_alert(self, alert_id: str, resolved_by: str,
                           resolution_notes: Optional[str] = None, *,
                           expected_version=None, request_id=None) -> Optional[AlertResponse]:
        return await self._change_alert(alert_id,
            {"status": "ignored", "resolved_by": resolved_by,
             **({"resolution_notes": resolution_notes} if resolution_notes else {})},
            actor_id=resolved_by, expected_version=expected_version, request_id=request_id)
    
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
            metadata=alert.metadata,
            version=alert.version
        )

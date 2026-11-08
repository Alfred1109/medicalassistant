"""
健康档案服务
提供健康档案和健康数据的业务逻辑实现

FU01 S2：随访方法组已拆出至 app/services/followup_service.py（唯一随访服务入口），
本服务保留健康档案域；健康档案统计中的随访计数经 FollowupService 转调。
"""
from typing import List, Dict, Any, Optional, Union
from datetime import datetime, timedelta
from motor.motor_asyncio import AsyncIOMotorDatabase
from bson import ObjectId

from app.models.health_record import HealthRecord, HealthData, MedicalTimeline
from app.schemas.health_record import (
    HealthRecordCreate, HealthRecordUpdate, HealthRecordResponse,
    HealthDataCreate, HealthDataResponse, HealthRecordStats, HealthTimelineItem,
    RecordType
)
from app.services.followup_service import FollowupService


class HealthRecordService:
    """健康档案服务类，提供健康档案和健康数据的业务逻辑实现"""

    def __init__(self, db: AsyncIOMotorDatabase):
        """初始化服务类

        Args:
            db: MongoDB数据库连接
        """
        self.db = db
        # 健康档案集合
        self.health_records = db[HealthRecord.collection_name]
        # 健康数据集合
        self.health_data = db[HealthData.collection_name]
        # 医疗时间线集合
        self.medical_timelines = db[MedicalTimeline.collection_name]
        # 随访域唯一入口（FU01 S2）：统计域随访计数转调，不在本服务直连随访集合
        self.followup_service = FollowupService(db)

    # -------- 健康档案相关方法 --------
    
    async def create_health_record(self, record_data: HealthRecordCreate) -> HealthRecordResponse:
        """创建健康档案
        
        Args:
            record_data: 健康档案创建请求数据
            
        Returns:
            HealthRecordResponse: 创建成功的健康档案响应
        """
        # 按生效 schema（HealthRecordCreate，schemas/health_record.py:371-375）修正：
        # organization_id / visibility 为第一代独有字段，生效模型上不存在，停止访问与写入（FU01 收敛决策），
        # 由存储模型默认值（organization_id=None、visibility="all"）兜底
        record = HealthRecord(
            patient_id=record_data.patient_id,
            record_type=record_data.record_type,
            title=record_data.title,
            content=record_data.content,
            created_by=record_data.created_by,
            # 按生效 schema 修正：附件为 pydantic 模型，须转 dict 才能落库（否则 bson InvalidDocument）
            attachments=[a.model_dump() for a in record_data.attachments],
            tags=record_data.tags,
            metadata=record_data.metadata
        )
        
        # 插入数据库
        result = await self.health_records.insert_one(record.to_mongo())
        
        # 更新ID
        record._id = str(result.inserted_id)
        
        # 创建关联的时间线项目
        timeline_item = MedicalTimeline.from_health_record(record)
        await self.medical_timelines.insert_one(timeline_item.to_mongo())
        
        # 返回响应
        return self._map_health_record_to_response(record)
    
    async def get_health_record(self, record_id: str) -> Optional[HealthRecordResponse]:
        """获取健康档案
        
        Args:
            record_id: 健康档案ID
            
        Returns:
            Optional[HealthRecordResponse]: 健康档案响应，不存在则返回None
        """
        # 查询数据库
        record_doc = await self.health_records.find_one({"_id": ObjectId(record_id)})
        if not record_doc:
            return None
        
        # 创建对象并返回响应
        record = HealthRecord.from_mongo(record_doc)
        return self._map_health_record_to_response(record)
    
    async def update_health_record(self, record_id: str, record_data: HealthRecordUpdate, updated_by: str) -> Optional[HealthRecordResponse]:
        """更新健康档案
        
        Args:
            record_id: 健康档案ID
            record_data: 健康档案更新请求数据
            updated_by: 更新者ID
            
        Returns:
            Optional[HealthRecordResponse]: 更新后的健康档案响应，不存在则返回None
        """
        # 查询数据库
        record_doc = await self.health_records.find_one({"_id": ObjectId(record_id)})
        if not record_doc:
            return None
        
        # 创建对象
        record = HealthRecord.from_mongo(record_doc)
        
        # 更新内容（如果提供）。按生效 schema 修正：HealthRecordUpdate.content 为 str，
        # 而存储模型的 update_content 仅支持 Dict content（内部调用 self.content.copy()/.update()），
        # 故在服务层直接赋值并沿用其版本记录语义
        if record_data.content:
            record.versions.append({
                "version_number": record.current_version,
                "content": record.content,
                "created_by": record.created_by if record.current_version == 1 else updated_by,
                "created_at": record.created_at if record.current_version == 1 else record.updated_at,
                "change_description": None if record.current_version == 1 else record_data.change_description
            })
            record.content = record_data.content
            record.current_version += 1
            record.updated_at = datetime.utcnow()

        # 更新其他字段
        update_data = {}
        if record_data.record_type:
            update_data["record_type"] = record_data.record_type  # 按生效 schema 修正：record_type 为生效字段
        if record_data.title:
            update_data["title"] = record_data.title
        if record_data.tags is not None:
            update_data["tags"] = record_data.tags
        if record_data.attachments is not None:
            # 按生效 schema 修正：附件为 pydantic 模型，须转 dict 才能落库
            update_data["attachments"] = [a.model_dump() for a in record_data.attachments]
        # 按生效 schema（HealthRecordUpdate:378-388）修正：visibility 为第一代独有字段，停止访问与写入
        if record_data.metadata:
            update_data["metadata"] = record_data.metadata
        
        # 如果有更新内容，应用更新
        if update_data:
            update_data["updated_at"] = datetime.utcnow()
            
            # 应用更新到对象
            for key, value in update_data.items():
                setattr(record, key, value)
        
        # 保存到数据库
        await self.health_records.replace_one({"_id": ObjectId(record_id)}, record.to_mongo())
        
        # 更新关联的时间线项目
        timeline_item = MedicalTimeline.from_health_record(record)
        await self.medical_timelines.update_one(
            {"item_type": "health_record", "related_ids": record_id},
            {"$set": {
                "title": record.title,
                "description": f"{record.record_type.capitalize()} 记录",
                "occurred_at": record.updated_at,
                "metadata.record_type": record.record_type
            }}
        )
        
        # 返回响应
        return self._map_health_record_to_response(record)
    
    async def delete_health_record(self, record_id: str) -> bool:
        """删除健康档案（软删除）
        
        Args:
            record_id: 健康档案ID
            
        Returns:
            bool: 删除成功返回True，不存在则返回False
        """
        # 查询数据库
        result = await self.health_records.update_one(
            {"_id": ObjectId(record_id)},
            {"$set": {"deleted": True, "deleted_at": datetime.utcnow()}}
        )
        
        return result.modified_count > 0
    
    async def list_health_records(
        self, 
        patient_id: str, 
        record_type: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        skip: int = 0, 
        limit: int = 100
    ) -> List[HealthRecordResponse]:
        """列出患者的健康档案
        
        Args:
            patient_id: 患者ID
            record_type: 记录类型过滤
            start_date: 开始日期过滤
            end_date: 结束日期过滤
            skip: 分页偏移量
            limit: 每页数量
            
        Returns:
            List[HealthRecordResponse]: 健康档案响应列表
        """
        # 构建查询条件
        query = {"patient_id": patient_id, "deleted": {"$ne": True}}
        
        if record_type:
            query["record_type"] = record_type
            
        date_query = {}
        if start_date:
            date_query["$gte"] = start_date
        if end_date:
            date_query["$lte"] = end_date
            
        if date_query:
            query["created_at"] = date_query
        
        # 查询数据库
        cursor = self.health_records.find(query).sort("created_at", -1).skip(skip).limit(limit)
        records = await cursor.to_list(length=limit)
        
        # 转换为响应对象
        return [self._map_health_record_to_response(HealthRecord.from_mongo(doc)) for doc in records]
    
    async def get_health_record_version(self, record_id: str, version_number: int) -> Optional[Dict[str, Any]]:
        """获取健康档案的特定版本
        
        Args:
            record_id: 健康档案ID
            version_number: 版本号
            
        Returns:
            Optional[Dict[str, Any]]: 版本信息，不存在则返回None
        """
        # 查询数据库
        record_doc = await self.health_records.find_one({"_id": ObjectId(record_id)})
        if not record_doc:
            return None
        
        # 创建对象
        record = HealthRecord.from_mongo(record_doc)
        
        # 获取版本信息
        version = record.get_version(version_number)
        if not version:
            return None
            
        # 将日期转换为字符串，便于JSON序列化
        version["created_at"] = version["created_at"].isoformat()
        
        return version
    
    async def get_health_record_stats(self, patient_id: str) -> HealthRecordStats:
        """获取患者健康档案统计信息
        
        Args:
            patient_id: 患者ID
            
        Returns:
            HealthRecordStats: 健康档案统计信息
        """
        # 计算总记录数
        total_records = await self.health_records.count_documents({
            "patient_id": patient_id,
            "deleted": {"$ne": True}
        })
        
        # 按记录类型分组统计
        pipeline = [
            {"$match": {"patient_id": patient_id, "deleted": {"$ne": True}}},
            {"$group": {"_id": "$record_type", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}}
        ]
        record_types_cursor = self.health_records.aggregate(pipeline)
        record_types = await record_types_cursor.to_list(length=100)
        record_type_counts = {doc["_id"]: doc["count"] for doc in record_types}
        
        # 获取最新记录
        latest_record_doc = await self.health_records.find_one(
            {"patient_id": patient_id, "deleted": {"$ne": True}},
            sort=[("created_at", -1)]
        )
        latest_record = None
        if latest_record_doc:
            latest_record = self._map_health_record_to_response(HealthRecord.from_mongo(latest_record_doc))
        
        # 获取即将到来的随访数量（FU01 S2：经 FollowupService 转调）
        upcoming_followups = await self.followup_service.count_upcoming(
            patient_id, since=datetime.utcnow()
        )
        
        # 获取最近的活动
        recent_timeline_cursor = self.medical_timelines.find(
            {"patient_id": patient_id}
        ).sort("occurred_at", -1).limit(5)
        recent_timeline = await recent_timeline_cursor.to_list(length=5)
        recent_activity = []
        for item in recent_timeline:
            timeline = MedicalTimeline.from_mongo(item)
            recent_activity.append({
                "id": timeline._id,
                "type": timeline.item_type,
                "title": timeline.title,
                "date": timeline.occurred_at.isoformat(),
                "description": timeline.description
            })
        
        # 计算完成度（简单示例）
        completion_percentage = 100.0  # 实际应用中可能需要更复杂的计算
        
        # 计算附件总数
        total_attachments_pipeline = [
            {"$match": {"patient_id": patient_id, "deleted": {"$ne": True}}},
            {"$project": {"attachment_count": {"$size": "$attachments"}}},
            {"$group": {"_id": None, "total": {"$sum": "$attachment_count"}}}
        ]
        attachments_result = await self.health_records.aggregate(total_attachments_pipeline).to_list(length=1)
        total_attachments = attachments_result[0]["total"] if attachments_result else 0
        
        # 返回统计信息
        return HealthRecordStats(
            total_records=total_records,
            record_type_counts=record_type_counts,
            latest_record=latest_record,
            upcoming_followups=upcoming_followups,
            recent_activity=recent_activity,
            completion_percentage=completion_percentage,
            total_attachments=total_attachments
        )
    
    # -------- 健康数据相关方法 --------
    
    async def create_health_data(self, data: HealthDataCreate) -> HealthDataResponse:
        """创建健康数据
        
        Args:
            data: 健康数据创建请求数据
            
        Returns:
            HealthDataResponse: 创建成功的健康数据响应
        """
        # 按生效 schema（HealthDataCreate:569-571）修正：
        # metadata 为第一代独有字段，生效模型上不存在，停止访问与写入，由存储模型默认值兜底；
        # 原句 device_id=data.source == "device" 系笔误（把布尔写进 device_id），且生效模型无 device_id
        # 字段，停止写入，设备来源语义由 source 字段承载
        health_data = HealthData(
            patient_id=data.patient_id,
            data_type=data.data_type,
            data=data.data_content,
            source=data.source,
            recorded_by=data.recorded_by,
            recorded_at=data.recorded_at or datetime.utcnow()
        )
        
        # 插入数据库
        result = await self.health_data.insert_one(health_data.to_mongo())
        
        # 更新ID
        health_data._id = str(result.inserted_id)
        
        # 创建关联的时间线项目
        timeline_item = MedicalTimeline.from_health_data(health_data)
        await self.medical_timelines.insert_one(timeline_item.to_mongo())
        
        # 返回响应
        return self._map_health_data_to_response(health_data)
    
    async def get_health_data(self, data_id: str) -> Optional[HealthDataResponse]:
        """获取健康数据
        
        Args:
            data_id: 健康数据ID
            
        Returns:
            Optional[HealthDataResponse]: 健康数据响应，不存在则返回None
        """
        # 查询数据库
        data_doc = await self.health_data.find_one({"_id": ObjectId(data_id)})
        if not data_doc:
            return None
        
        # 创建对象并返回响应
        health_data = HealthData.from_mongo(data_doc)
        return self._map_health_data_to_response(health_data)
    
    async def list_health_data(
        self, 
        patient_id: str, 
        data_type: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        skip: int = 0, 
        limit: int = 100
    ) -> List[HealthDataResponse]:
        """列出患者的健康数据
        
        Args:
            patient_id: 患者ID
            data_type: 数据类型过滤
            start_date: 开始日期过滤
            end_date: 结束日期过滤
            skip: 分页偏移量
            limit: 每页数量
            
        Returns:
            List[HealthDataResponse]: 健康数据响应列表
        """
        # 构建查询条件
        query = {"patient_id": patient_id, "deleted": {"$ne": True}}
        
        if data_type:
            query["data_type"] = data_type
            
        date_query = {}
        if start_date:
            date_query["$gte"] = start_date
        if end_date:
            date_query["$lte"] = end_date
            
        if date_query:
            query["recorded_at"] = date_query
        
        # 查询数据库
        cursor = self.health_data.find(query).sort("recorded_at", -1).skip(skip).limit(limit)
        data_list = await cursor.to_list(length=limit)
        
        # 转换为响应对象
        return [self._map_health_data_to_response(HealthData.from_mongo(doc)) for doc in data_list]
    
    async def create_vital_sign(
        self,
        patient_id: str,
        vital_type: str,
        value: Union[float, str, Dict[str, float]],
        unit: Optional[str] = None,
        measured_at: Optional[datetime] = None,
        measured_by: Optional[str] = None,
        device_id: Optional[str] = None,
        notes: Optional[str] = None
    ) -> HealthDataResponse:
        """创建生命体征记录
        
        Args:
            patient_id: 患者ID
            vital_type: 生命体征类型
            value: 测量值
            unit: 单位
            measured_at: 测量时间
            measured_by: 测量人
            device_id: 设备ID
            notes: 备注
            
        Returns:
            HealthDataResponse: 创建成功的健康数据响应
        """
        # 使用工厂方法创建生命体征记录
        health_data = HealthData.create_vital_sign(
            patient_id=patient_id,
            vital_type=vital_type,
            value=value,
            unit=unit,
            measured_at=measured_at,
            measured_by=measured_by,
            device_id=device_id,
            notes=notes
        )
        
        # 插入数据库
        result = await self.health_data.insert_one(health_data.to_mongo())
        
        # 更新ID
        health_data._id = str(result.inserted_id)
        
        # 创建关联的时间线项目
        timeline_item = MedicalTimeline.from_health_data(health_data)
        await self.medical_timelines.insert_one(timeline_item.to_mongo())
        
        # 返回响应
        return self._map_health_data_to_response(health_data)
    
    async def create_lab_result(
        self,
        patient_id: str,
        test_name: str,
        result_value: Union[float, str, Dict[str, Any]],
        reference_range: Optional[str] = None,
        unit: Optional[str] = None,
        test_date: Optional[datetime] = None,
        ordering_provider: Optional[str] = None,
        performing_lab: Optional[str] = None,
        interpretation: Optional[str] = None,
        notes: Optional[str] = None
    ) -> HealthDataResponse:
        """创建实验室检查结果记录
        
        Args:
            patient_id: 患者ID
            test_name: 检测名称
            result_value: 结果值
            reference_range: 参考范围
            unit: 单位
            test_date: 检测日期
            ordering_provider: 开单医生
            performing_lab: 执行实验室
            interpretation: 结果解释
            notes: 备注
            
        Returns:
            HealthDataResponse: 创建成功的健康数据响应
        """
        # 使用工厂方法创建实验室检查结果记录
        health_data = HealthData.create_lab_result(
            patient_id=patient_id,
            test_name=test_name,
            result_value=result_value,
            reference_range=reference_range,
            unit=unit,
            test_date=test_date,
            ordering_provider=ordering_provider,
            performing_lab=performing_lab,
            interpretation=interpretation,
            notes=notes
        )
        
        # 插入数据库
        result = await self.health_data.insert_one(health_data.to_mongo())
        
        # 更新ID
        health_data._id = str(result.inserted_id)
        
        # 创建关联的时间线项目
        timeline_item = MedicalTimeline.from_health_data(health_data)
        await self.medical_timelines.insert_one(timeline_item.to_mongo())
        
        # 返回响应
        return self._map_health_data_to_response(health_data)
    
    # -------- 时间线相关方法 --------
    
    async def get_medical_timeline(
        self,
        patient_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        item_types: Optional[List[str]] = None,
        skip: int = 0,
        limit: int = 100
    ) -> List[HealthTimelineItem]:
        """获取患者的医疗时间线
        
        Args:
            patient_id: 患者ID
            start_date: 开始日期过滤
            end_date: 结束日期过滤
            item_types: 项目类型列表过滤
            skip: 分页偏移量
            limit: 每页数量
            
        Returns:
            List[HealthTimelineItem]: 健康时间线项目列表
        """
        # 构建查询条件
        query = {"patient_id": patient_id}
        
        if item_types:
            query["item_type"] = {"$in": item_types}
            
        date_query = {}
        if start_date:
            date_query["$gte"] = start_date
        if end_date:
            date_query["$lte"] = end_date
            
        if date_query:
            query["occurred_at"] = date_query
        
        # 查询数据库
        cursor = self.medical_timelines.find(query).sort("occurred_at", -1).skip(skip).limit(limit)
        timeline_items = await cursor.to_list(length=limit)
        
        # 转换为响应对象
        return [self._map_timeline_to_response(MedicalTimeline.from_mongo(doc)) for doc in timeline_items]
    
    # -------- 对象映射方法 --------
    
    def _map_health_record_to_response(self, health_record: HealthRecord) -> HealthRecordResponse:
        """将健康档案对象映射为响应对象
        
        Args:
            health_record: 健康档案对象
            
        Returns:
            HealthRecordResponse: 健康档案响应对象
        """
        return HealthRecordResponse(
            id=health_record._id,
            patient_id=health_record.patient_id,
            record_type=health_record.record_type,
            title=health_record.title,
            content=health_record.content,
            created_by=health_record.created_by,
            attachments=health_record.attachments,
            tags=health_record.tags,
            # 按生效 schema 修正：organization_id / visibility 不在生效的 HealthRecordResponse（:404-414）上，停止透传
            created_at=health_record.created_at,
            updated_at=health_record.updated_at,
            current_version=health_record.current_version,
            related_items=health_record.related_items if hasattr(health_record, 'related_items') else [],
            related_follow_ups=health_record.related_follow_ups if hasattr(health_record, 'related_follow_ups') else [],
            updated_by=health_record.updated_by if hasattr(health_record, 'updated_by') else None,
            metadata=health_record.metadata
        )
    
    def _map_health_data_to_response(self, health_data: HealthData) -> HealthDataResponse:
        """将健康数据对象映射为响应对象
        
        Args:
            health_data: 健康数据对象
            
        Returns:
            HealthDataResponse: 健康数据响应对象
        """
        return HealthDataResponse(
            id=health_data._id,
            patient_id=health_data.patient_id,
            data_type=health_data.data_type,
            data_content=health_data.data,
            recorded_at=health_data.recorded_at,
            recorded_by=health_data.recorded_by,
            source=health_data.source,
            created_at=health_data.created_at,
            updated_at=health_data.updated_at,
            metadata=health_data.metadata
        )
    
    def _map_timeline_to_response(self, timeline: MedicalTimeline) -> HealthTimelineItem:
        """将医疗时间线对象映射为响应对象
        
        Args:
            timeline: 医疗时间线对象
            
        Returns:
            HealthTimelineItem: 健康时间线项目响应对象
        """
        return HealthTimelineItem(
            id=timeline._id,
            patient_id=timeline.patient_id,
            item_type=timeline.item_type,
            title=timeline.title,
            description=timeline.description,
            timestamp=timeline.occurred_at,
            data={
                "related_ids": timeline.related_ids,
                "metadata": timeline.metadata
            },
            icon=timeline.metadata.get("icon") if timeline.metadata else None,
            color=timeline.metadata.get("color") if timeline.metadata else None,
            importance=timeline.metadata.get("importance", 0) if timeline.metadata else 0
        ) 
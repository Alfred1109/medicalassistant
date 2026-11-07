"""
健康档案服务
提供健康档案、随访记录和健康数据的业务逻辑实现
"""
from typing import List, Dict, Any, Optional, Union
from datetime import datetime, timedelta
from motor.motor_asyncio import AsyncIOMotorDatabase
from bson import ObjectId

from app.models.health_record import HealthRecord, FollowUpRecord, HealthData, MedicalTimeline
from app.schemas.followup import (
    FollowUpRecordCreate, FollowUpRecordUpdate, FollowUpRecordResponse,
    CompleteFollowUpRequest, CancelFollowUpRequest, RescheduleFollowUpRequest,
    FollowUpStatus,
)
from app.schemas.health_record import (
    HealthRecordCreate, HealthRecordUpdate, HealthRecordResponse,
    HealthDataCreate, HealthDataResponse, HealthRecordStats, HealthTimelineItem,
    RecordType
)


# FollowUpRecordDB 存储模型的正式扩展字段（FU01 S1 起直接落顶层，全部 Optional）。
# 存量文档（e7e8706 缝合层约定）对应数据在 metadata.* 下，读取时兼容回退；
# models.FollowUpRecord.from_mongo 按显式关键字构造，顶层未知键会抛 TypeError，
# 故读取前先摘出（见 HealthRecordService._followup_from_mongo）。
_FOLLOWUP_FORMAL_FIELDS = (
    "provider_id", "template_id", "reminder_before",
    "completion_data", "cancellation_data", "next_follow_up_id",
    "follow_up_result",
    # FU01 S3 节点字段增强（schemas/followup.py FollowUpRecordDB）+ 迁移打标，
    # 同样只在读取侧摘出挂回，models.FollowUpRecord 构造器不认识这些顶层键
    "visit_code", "form_binding", "fill_task_ids", "effective_response",
    "review", "previous_visit_id", "next_visit_id",
    "legacy_source",
)


class HealthRecordService:
    """健康档案服务类，提供健康档案、随访记录和健康数据的业务逻辑实现"""
    
    def __init__(self, db: AsyncIOMotorDatabase):
        """初始化服务类
        
        Args:
            db: MongoDB数据库连接
        """
        self.db = db
        # 健康档案集合
        self.health_records = db[HealthRecord.collection_name]
        # 随访记录集合
        self.followup_records = db[FollowUpRecord.collection_name]
        # 健康数据集合
        self.health_data = db[HealthData.collection_name]
        # 医疗时间线集合
        self.medical_timelines = db[MedicalTimeline.collection_name]
    
    # -------- 随访读取兼容层（FU01 S1） --------

    def _followup_from_mongo(self, mongo_doc) -> Optional[FollowUpRecord]:
        """从 followup_records 集合文档构建 FollowUpRecord。

        models.FollowUpRecord.from_mongo 按显式关键字参数构造，文档出现存储模型
        未声明的顶层键会抛 TypeError；S1 起正式扩展字段（_FOLLOWUP_FORMAL_FIELDS）
        直接落顶层，读取时先摘出、再 setattr 挂回实例，供映射层按
        「正式字段优先、metadata.* 回退」取值（存量 demo 文档不迁移、不破坏）。
        """
        if not mongo_doc:
            return None
        doc = dict(mongo_doc)
        formal = {}
        for field in _FOLLOWUP_FORMAL_FIELDS:
            value = doc.pop(field, None)
            if value is not None:
                formal[field] = value
        record = FollowUpRecord.from_mongo(doc)
        for field, value in formal.items():
            setattr(record, field, value)
        return record

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
        
        # 获取即将到来的随访数量
        upcoming_followups = await self.followup_records.count_documents({
            "patient_id": patient_id,
            "status": "scheduled",
            "scheduled_date": {"$gte": datetime.utcnow()}
        })
        
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
    
    # -------- 随访记录相关方法 --------
    
    async def create_followup_record(self, followup_data: FollowUpRecordCreate) -> FollowUpRecordResponse:
        """创建随访记录
        
        Args:
            followup_data: 随访记录创建请求数据
            
        Returns:
            FollowUpRecordResponse: 创建成功的随访记录响应
        """
        # 按生效 schema（schemas/followup.py FollowUpRecordCreate）修正：
        # notes / health_record_ids 为第一代字段，生效模型上不存在，停止访问；
        # 生效字段映射：description -> 存储字段 notes，related_records -> 存储字段 health_record_ids，
        # created_by 缺省时回退到必填的 provider_id。
        # S1 起扩展数据停止写 metadata.*：provider_id / template_id / reminder_before
        # 直接落顶层正式字段（FollowUpRecordDB 已声明，全部 Optional）。
        followup_metadata = dict(followup_data.metadata or {})

        # 创建随访记录对象
        followup_record = FollowUpRecord(
            patient_id=followup_data.patient_id,
            created_by=followup_data.created_by or followup_data.provider_id,
            follow_up_type=followup_data.follow_up_type,
            scheduled_date=followup_data.scheduled_date,
            notes=followup_data.description,
            # 按生效 schema 修正：questions 为 pydantic 模型，须转 dict 才能落库
            questions=[q.model_dump() for q in followup_data.questions],
            health_record_ids=followup_data.related_records,
            metadata=followup_metadata
        )
        # 正式扩展字段落顶层（存储模型 __init__ 未声明，to_mongo 复制 __dict__ 带出）
        followup_record.provider_id = followup_data.provider_id
        if followup_data.template_id:
            followup_record.template_id = followup_data.template_id
        if followup_data.reminder_before is not None:
            followup_record.reminder_before = followup_data.reminder_before
        
        # 插入数据库
        result = await self.followup_records.insert_one(followup_record.to_mongo())
        
        # 更新ID
        followup_record._id = str(result.inserted_id)
        
        # 创建关联的时间线项目
        timeline_item = MedicalTimeline.from_follow_up(followup_record)
        await self.medical_timelines.insert_one(timeline_item.to_mongo())
        
        # 返回响应
        return self._map_followup_record_to_response(followup_record)
    
    async def get_followup_record(self, followup_id: str) -> Optional[FollowUpRecordResponse]:
        """获取随访记录
        
        Args:
            followup_id: 随访记录ID
            
        Returns:
            Optional[FollowUpRecordResponse]: 随访记录响应，不存在则返回None
        """
        # 查询数据库
        followup_doc = await self.followup_records.find_one({"_id": ObjectId(followup_id)})
        if not followup_doc:
            return None
        
        # 创建对象并返回响应
        followup_record = self._followup_from_mongo(followup_doc)
        return self._map_followup_record_to_response(followup_record)
    
    async def update_followup_record(self, followup_id: str, followup_data: FollowUpRecordUpdate) -> Optional[FollowUpRecordResponse]:
        """更新随访记录
        
        Args:
            followup_id: 随访记录ID
            followup_data: 随访记录更新请求数据
            
        Returns:
            Optional[FollowUpRecordResponse]: 更新后的随访记录响应，不存在则返回None
        """
        # 查询数据库
        followup_doc = await self.followup_records.find_one({"_id": ObjectId(followup_id)})
        if not followup_doc:
            return None
        
        # 创建对象
        followup_record = self._followup_from_mongo(followup_doc)
        
        # 更新字段。按生效 schema（FollowUpRecordUpdate:484-494）修正：
        # notes / health_record_ids 为第一代字段，停止访问；
        # 生效字段映射：description -> 存储字段 notes，related_records -> 存储字段 health_record_ids
        update_data = {}
        if followup_data.follow_up_type:
            update_data["follow_up_type"] = followup_data.follow_up_type
        if followup_data.scheduled_date:
            update_data["scheduled_date"] = followup_data.scheduled_date
        if followup_data.status:
            # 按生效 schema 修正：status 为枚举，落库取其字符串值
            update_data["status"] = followup_data.status.value
        if followup_data.description is not None:
            update_data["notes"] = followup_data.description
        if followup_data.questions is not None:
            # 按生效 schema 修正：questions 为 pydantic 模型，须转 dict 才能进 $set
            update_data["questions"] = [q.model_dump() for q in followup_data.questions]
        if followup_data.related_records is not None:
            update_data["health_record_ids"] = followup_data.related_records
        if followup_data.provider_id is not None:
            # S1 起落顶层正式字段（此前入参被静默丢弃）
            update_data["provider_id"] = followup_data.provider_id
        if followup_data.reminder_before is not None:
            update_data["reminder_before"] = followup_data.reminder_before
        if followup_data.metadata is not None:
            update_data["metadata"] = followup_data.metadata
        
        # 添加更新时间
        update_data["updated_at"] = datetime.utcnow()
        
        # 更新数据库
        await self.followup_records.update_one(
            {"_id": ObjectId(followup_id)},
            {"$set": update_data}
        )
        
        # 如果状态改变，更新时间线
        if followup_data.status:
            followup = self._followup_from_mongo(await self.followup_records.find_one({"_id": ObjectId(followup_id)}))
            timeline_item = MedicalTimeline.from_follow_up(followup)
            
            status_desc = {
                "scheduled": "已安排",
                "completed": "已完成",
                "canceled": "已取消",
                "missed": "已错过",
                "rescheduled": "已重新安排"
            }
            
            await self.medical_timelines.update_one(
                {"related_ids": followup_id, "item_type": "follow_up"},
                {"$set": {
                    "description": f"随访状态: {status_desc.get(followup.status, followup.status)}",
                    "occurred_at": followup.actual_date if followup.actual_date else followup.scheduled_date,
                    "metadata.status": followup.status
                }}
            )
        
        # 返回更新后的记录
        return await self.get_followup_record(followup_id)
    
    async def complete_followup(self, followup_id: str, data: CompleteFollowUpRequest) -> Optional[FollowUpRecordResponse]:
        """完成随访
        
        Args:
            followup_id: 随访记录ID
            data: 完成随访请求数据
            
        Returns:
            Optional[FollowUpRecordResponse]: 更新后的随访记录响应，不存在则返回None
        """
        # 查询数据库
        followup_doc = await self.followup_records.find_one({"_id": ObjectId(followup_id)})
        if not followup_doc:
            return None
        
        # 创建对象
        followup_record = self._followup_from_mongo(followup_doc)
        
        # 按生效 schema 修正：answers 为 pydantic 模型（FollowUpAnswer），须转 dict 才能落库（bson InvalidDocument）
        answers_data = [a.model_dump() for a in data.answers]

        # 更新随访状态
        followup_record.complete_followup(
            actual_date=data.actual_date,
            notes=data.notes,
            answers=answers_data
        )

        # 完成数据
        completion_data = {
            "completed_at": datetime.utcnow(),
            "result": data.follow_up_result,
            "notes": data.notes
        }

        # 更新数据库。S1 起完成数据写顶层正式字段（FollowUpRecordDB 已声明），
        # 停止 metadata.completion_data / metadata.result 顶层数据；
        # 存量文档的 metadata.* 由读取侧回退兼容（_followup_from_mongo + 映射层）。
        await self.followup_records.update_one(
            {"_id": ObjectId(followup_id)},
            {"$set": {
                "status": "completed",
                "actual_date": data.actual_date,
                "answers": answers_data,
                "notes": data.notes if data.notes else followup_record.notes,
                "updated_at": datetime.utcnow(),
                "completion_data": completion_data,
                "follow_up_result": data.follow_up_result
            }}
        )
        
        # 如果提供了下次随访日期，创建新的随访记录
        if data.next_follow_up_date:
            # 基于当前随访创建新的随访记录
            new_followup = FollowUpRecord(
                patient_id=followup_record.patient_id,
                created_by=followup_record.created_by,
                follow_up_type=followup_record.follow_up_type,
                scheduled_date=data.next_follow_up_date,
                notes=f"基于上次随访({followup_record._id})创建的后续随访",
                questions=followup_record.questions,
                health_record_ids=followup_record.health_record_ids
            )
            
            # 插入数据库
            new_result = await self.followup_records.insert_one(new_followup.to_mongo())
            
            # 更新原随访记录的next_follow_up_id（S1 起写顶层正式字段，读取侧回退兼容存量 metadata.*）
            await self.followup_records.update_one(
                {"_id": ObjectId(followup_id)},
                {"$set": {"next_follow_up_id": str(new_result.inserted_id)}}
            )
            
            # 创建关联的时间线项目
            new_followup._id = str(new_result.inserted_id)
            timeline_item = MedicalTimeline.from_follow_up(new_followup)
            await self.medical_timelines.insert_one(timeline_item.to_mongo())
        
        # 更新时间线
        timeline_item = MedicalTimeline.from_follow_up(followup_record)
        await self.medical_timelines.update_one(
            {"related_ids": followup_id, "item_type": "follow_up"},
            {"$set": {
                "description": "随访状态: 已完成",
                "occurred_at": data.actual_date,
                "metadata.status": "completed",
                "metadata.result": data.follow_up_result
            }}
        )
        
        # 返回更新后的记录
        return await self.get_followup_record(followup_id)
    
    async def cancel_followup(self, followup_id: str, data: CancelFollowUpRequest) -> Optional[FollowUpRecordResponse]:
        """取消随访
        
        Args:
            followup_id: 随访记录ID
            data: 取消随访请求数据
            
        Returns:
            Optional[FollowUpRecordResponse]: 更新后的随访记录响应，不存在则返回None
        """
        # 查询数据库
        followup_doc = await self.followup_records.find_one({"_id": ObjectId(followup_id)})
        if not followup_doc:
            return None
        
        # 创建对象
        followup_record = self._followup_from_mongo(followup_doc)
        
        # 更新随访状态
        followup_record.cancel_followup(
            reason=data.cancel_reason,
            reschedule_date=data.reschedule_date
        )
        
        # 取消数据
        cancellation_data = {
            "canceled_at": datetime.utcnow(),
            "canceled_by": data.canceled_by,
            "reason": data.cancel_reason,
            "reschedule_date": data.reschedule_date
        }
        
        # 更新字段。S1 起取消数据写顶层正式字段（FollowUpRecordDB 已声明），
        # 停止 metadata.cancellation_data 顶层数据；存量文档由读取侧回退兼容
        update_data = {
            "status": "canceled",
            "notes": followup_record.notes,
            "updated_at": datetime.utcnow(),
            "cancellation_data": cancellation_data
        }
        
        # 更新数据库
        await self.followup_records.update_one(
            {"_id": ObjectId(followup_id)},
            {"$set": update_data}
        )
        
        # 如果要重新安排随访，创建新的随访记录
        if data.reschedule_date:
            # 基于当前随访创建新的随访记录
            new_followup = FollowUpRecord(
                patient_id=followup_record.patient_id,
                created_by=followup_record.created_by,
                follow_up_type=followup_record.follow_up_type,
                scheduled_date=data.reschedule_date,
                notes=f"由于取消原随访({followup_record._id})而重新安排的随访: {data.cancel_reason}",
                questions=followup_record.questions,
                health_record_ids=followup_record.health_record_ids
            )
            
            # 插入数据库
            new_result = await self.followup_records.insert_one(new_followup.to_mongo())
            
            # 更新原随访记录的next_follow_up_id（S1 起写顶层正式字段，读取侧回退兼容存量 metadata.*）
            await self.followup_records.update_one(
                {"_id": ObjectId(followup_id)},
                {"$set": {"next_follow_up_id": str(new_result.inserted_id)}}
            )
            
            # 创建关联的时间线项目
            new_followup._id = str(new_result.inserted_id)
            timeline_item = MedicalTimeline.from_follow_up(new_followup)
            await self.medical_timelines.insert_one(timeline_item.to_mongo())
        
        # 更新时间线
        timeline_item = MedicalTimeline.from_follow_up(followup_record)
        await self.medical_timelines.update_one(
            {"related_ids": followup_id, "item_type": "follow_up"},
            {"$set": {
                "description": f"随访状态: 已取消 - {data.cancel_reason}",
                "metadata.status": "canceled",
                "metadata.reason": data.cancel_reason
            }}
        )
        
        # 返回更新后的记录
        return await self.get_followup_record(followup_id)
    
    async def reschedule_followup(self, followup_id: str, data: RescheduleFollowUpRequest) -> Optional[FollowUpRecordResponse]:
        """重新安排随访时间
        
        Args:
            followup_id: 随访记录ID
            data: 重新安排随访请求数据
            
        Returns:
            Optional[FollowUpRecordResponse]: 更新后的随访记录响应，不存在则返回None
        """
        # 查询数据库
        followup_doc = await self.followup_records.find_one({"_id": ObjectId(followup_id)})
        if not followup_doc:
            return None
        
        # 创建对象
        followup_record = self._followup_from_mongo(followup_doc)
        
        # 更新随访状态
        followup_record.reschedule(
            new_date=data.new_date,
            reason=data.reason
        )
        
        # 更新数据库
        await self.followup_records.update_one(
            {"_id": ObjectId(followup_id)},
            {"$set": {
                "status": "rescheduled",
                "scheduled_date": data.new_date,
                "notes": followup_record.notes,
                "updated_at": datetime.utcnow(),
                "metadata.reschedule_reason": data.reason,
                "metadata.reschedule_time": datetime.utcnow()
            }}
        )
        
        # 更新时间线
        timeline_item = MedicalTimeline.from_follow_up(followup_record)
        await self.medical_timelines.update_one(
            {"related_ids": followup_id, "item_type": "follow_up"},
            {"$set": {
                "description": f"随访状态: 已重新安排至 {data.new_date.strftime('%Y-%m-%d %H:%M')}",
                "occurred_at": data.new_date,
                "metadata.status": "rescheduled",
                "metadata.reason": data.reason
            }}
        )
        
        # 返回更新后的记录
        return await self.get_followup_record(followup_id)
    
    async def list_followup_records(
        self, 
        patient_id: str, 
        status: Optional[List[str]] = None,
        follow_up_type: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        skip: int = 0, 
        limit: int = 100
    ) -> List[FollowUpRecordResponse]:
        """列出患者的随访记录
        
        Args:
            patient_id: 患者ID
            status: 状态列表过滤
            follow_up_type: 随访类型过滤
            start_date: 开始日期过滤
            end_date: 结束日期过滤
            skip: 分页偏移量
            limit: 每页数量
            
        Returns:
            List[FollowUpRecordResponse]: 随访记录响应列表
        """
        # 构建查询条件
        query = {"patient_id": patient_id, "deleted": {"$ne": True}}
        
        if status:
            query["status"] = {"$in": status}
            
        if follow_up_type:
            query["follow_up_type"] = follow_up_type
            
        date_query = {}
        if start_date:
            date_query["$gte"] = start_date
        if end_date:
            date_query["$lte"] = end_date
            
        if date_query:
            query["scheduled_date"] = date_query
        
        # 查询数据库
        cursor = self.followup_records.find(query).sort("scheduled_date", 1).skip(skip).limit(limit)
        followups = await cursor.to_list(length=limit)
        
        # 转换为响应对象
        return [self._map_followup_record_to_response(self._followup_from_mongo(doc)) for doc in followups]
    
    async def get_upcoming_followups(self, patient_id: Optional[str] = None, days: int = 7) -> List[FollowUpRecordResponse]:
        """获取即将到来的随访记录
        
        Args:
            patient_id: 患者ID，不提供则获取所有患者的即将到来的随访
            days: 未来几天内的随访
            
        Returns:
            List[FollowUpRecordResponse]: 随访记录响应列表
        """
        # 构建查询条件
        query = {
            "status": {"$in": ["scheduled", "rescheduled"]},
            "scheduled_date": {
                "$gte": datetime.utcnow(),
                "$lte": datetime.utcnow() + timedelta(days=days)
            },
            "deleted": {"$ne": True}
        }
        
        if patient_id:
            query["patient_id"] = patient_id
        
        # 查询数据库
        cursor = self.followup_records.find(query).sort("scheduled_date", 1)
        followups = await cursor.to_list(length=100)
        
        # 转换为响应对象
        return [self._map_followup_record_to_response(self._followup_from_mongo(doc)) for doc in followups]
    
    async def get_followups_by_health_record(self, record_id: str) -> List[FollowUpRecordResponse]:
        """获取与健康档案关联的随访记录
        
        Args:
            record_id: 健康档案ID
            
        Returns:
            List[FollowUpRecordResponse]: 随访记录响应列表
        """
        # 查询数据库
        cursor = self.followup_records.find({"health_record_ids": record_id, "deleted": {"$ne": True}}).sort("scheduled_date", -1)
        followups = await cursor.to_list(length=100)
        
        # 转换为响应对象
        return [self._map_followup_record_to_response(self._followup_from_mongo(doc)) for doc in followups]
    
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
    
    def _map_followup_record_to_response(self, followup_record: FollowUpRecord) -> FollowUpRecordResponse:
        """将随访记录对象映射为响应对象

        扩展数据取值兼容（FU01 S1）：正式字段（顶层）优先，
        缺省回退存量文档的 metadata.*（e7e8706 缝合层约定），对外响应形状不变。

        Args:
            followup_record: 随访记录对象

        Returns:
            FollowUpRecordResponse: 随访记录响应对象
        """
        metadata = followup_record.metadata or {}

        def formal_or_meta(field: str, meta_key: str):
            value = getattr(followup_record, field, None)
            if value is not None:
                return value
            return metadata.get(meta_key)

        reminder_before = formal_or_meta("reminder_before", "reminder_before")
        if reminder_before is None:
            # 存量文档无正式字段与 metadata.reminder_before 时沿用原兜底（提醒设置）
            reminder_before = followup_record.reminder_settings.get("days_before") if hasattr(followup_record, 'reminder_settings') and followup_record.reminder_settings else None

        return FollowUpRecordResponse(
            id=followup_record._id,
            patient_id=followup_record.patient_id,
            created_by=followup_record.created_by,
            follow_up_type=followup_record.follow_up_type,
            scheduled_date=followup_record.scheduled_date,
            provider_id=formal_or_meta("provider_id", "provider_id") or followup_record.created_by,  # 无正式字段时使用创建者
            description=followup_record.notes,  # 存储字段 notes -> 响应字段 description
            questions=followup_record.questions,
            related_records=followup_record.health_record_ids,
            metadata=followup_record.metadata,
            created_at=followup_record.created_at,
            updated_at=followup_record.updated_at,
            status=followup_record.status,
            actual_date=followup_record.actual_date,
            answers=followup_record.answers,
            notes=followup_record.notes,
            follow_up_result=formal_or_meta("follow_up_result", "result"),
            next_follow_up_id=formal_or_meta("next_follow_up_id", "next_follow_up_id"),
            template_id=formal_or_meta("template_id", "template_id"),
            reminder_before=reminder_before,
            completion_data=formal_or_meta("completion_data", "completion_data"),
            cancellation_data=formal_or_meta("cancellation_data", "cancellation_data")
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
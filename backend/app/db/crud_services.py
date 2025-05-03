"""
模型CRUD服务
为各模型提供特定的CRUD操作
"""
from typing import List, Dict, Any, Optional, Type, TypeVar, Generic, Union
from motor.motor_asyncio import AsyncIOMotorDatabase
from datetime import datetime, timedelta
from bson import ObjectId

from app.db.crud import CRUDBase
from app.models.user import User, Doctor, Patient, HealthManager, SystemAdmin
from app.models.organization import Organization
from app.models.health_record import HealthRecord, FollowUpRecord
from app.models.rehabilitation import RehabilitationPlan, Exercise, ProgressRecord
from app.models.device import Device, DeviceData, DeviceCalibration
from app.models.agent import Agent, AgentInteraction
from app.models.communication import Message, Conversation


class CRUDServiceException(Exception):
    """CRUD服务异常基类"""
    pass


class UserCRUD(CRUDBase[User]):
    """用户CRUD服务"""
    
    async def find_by_email(self, email: str) -> Optional[User]:
        """通过邮箱查找用户"""
        return await self.find_one({"email": email})
    
    async def find_by_role(self, role: str, skip: int = 0, limit: int = 100) -> List[User]:
        """通过角色查找用户"""
        return await self.find({"role": role}, skip, limit)
    
    async def update_password(self, user_id: str, password_hash: str) -> bool:
        """更新用户密码"""
        try:
            result = await self.collection.update_one(
                {"_id": ObjectId(user_id)},
                {"$set": {"password_hash": password_hash, "updated_at": datetime.utcnow()}}
            )
            return result.modified_count > 0
        except Exception:
            return False


class PractitionerCRUD(UserCRUD):
    """医疗从业者基类"""
    
    async def find_by_organization(self, organization_id: str, skip: int = 0, limit: int = 100) -> List[Any]:
        """查找某组织的从业者"""
        return await self.find({"organization_id": organization_id, "role": self.role}, skip, limit)
    
    async def get_patients(self, practitioner_id: str) -> List[str]:
        """获取从业者的患者ID列表"""
        try:
            practitioner = await self.collection.find_one({"_id": ObjectId(practitioner_id), "role": self.role})
            if practitioner and "patients" in practitioner:
                return practitioner["patients"]
            return []
        except Exception as e:
            print(f"获取{self.role}患者列表时出错: {str(e)}")
            return []
    
    async def add_patient(self, practitioner_id: str, patient_id: str) -> bool:
        """为从业者添加患者"""
        try:
            result = await self.collection.update_one(
                {"_id": ObjectId(practitioner_id), "role": self.role},
                {"$addToSet": {"patients": patient_id}}
            )
            return result.modified_count > 0
        except Exception:
            return False


class DoctorCRUD(PractitionerCRUD):
    """医生CRUD服务"""
    
    def __init__(self, db: AsyncIOMotorDatabase, model_class: Type[Doctor]):
        super().__init__(db, model_class)
        self.role = "doctor"
    
    async def find_by_specialty(self, specialty: str, skip: int = 0, limit: int = 100) -> List[Doctor]:
        """查找特定专业的医生"""
        return await self.find({"specialty": specialty, "role": self.role}, skip, limit)


class PatientCRUD(CRUDBase[Patient]):
    """患者CRUD服务"""
    
    async def find_by_doctors(self, doctor_id: str, skip: int = 0, limit: int = 100) -> List[Patient]:
        """查找某医生的患者"""
        return await self.find({"practitioners": doctor_id, "role": "patient"}, skip, limit)
    
    async def find_by_health_manager(self, health_manager_id: str, skip: int = 0, limit: int = 100) -> List[Patient]:
        """查找某健康管理师的患者"""
        return await self.find({"health_managers": health_manager_id, "role": "patient"}, skip, limit)
    
    async def _get_patient_data(self, patient_doc: dict) -> dict:
        """从患者文档提取前端需要的数据"""
        if not patient_doc:
            return {}
            
        return {
            "id": str(patient_doc["_id"]),
            "name": patient_doc.get("name", "未知患者"),
            "age": patient_doc.get("age", 0),
            "gender": patient_doc.get("gender", "未知"),
            "diagnosis": patient_doc.get("diagnosis", None),
            "status": patient_doc.get("status", "未知")
        }
    
    async def find_by_doctor_id(self, doctor_id: str) -> List[dict]:
        """根据医生ID查找其管理的所有患者"""
        try:
            # 获取医生对象
            doctor_collection = self.db["users"]
            doctor = await doctor_collection.find_one({"_id": ObjectId(doctor_id), "role": "doctor"})
            
            if not doctor or "patients" not in doctor or not doctor["patients"]:
                return []
                
            # 获取患者列表
            patient_ids = doctor["patients"]
            results = []
            
            for patient_id in patient_ids:
                try:
                    patient_doc = await self.collection.find_one({"_id": ObjectId(patient_id), "role": "patient"})
                    if patient_doc:
                        results.append(self._get_patient_data(patient_doc))
                except Exception as e:
                    print(f"获取患者数据错误 (ID: {patient_id}): {str(e)}")
            
            return results
        except Exception as e:
            print(f"查找医生患者时出错: {str(e)}")
            return []
    
    async def update_medical_info(self, patient_id: str, medical_info: Dict[str, Any]) -> bool:
        """更新患者医疗信息"""
        try:
            result = await self.collection.update_one(
                {"_id": ObjectId(patient_id), "role": "patient"},
                {"$set": {"medical_info": medical_info, "updated_at": datetime.utcnow()}}
            )
            return result.modified_count > 0
        except Exception:
            return False
    
    async def add_device(self, patient_id: str, device_id: str) -> bool:
        """为患者添加设备"""
        try:
            result = await self.collection.update_one(
                {"_id": ObjectId(patient_id), "role": "patient"},
                {"$addToSet": {"devices": device_id}}
            )
            return result.modified_count > 0
        except Exception:
            return False


class HealthManagerCRUD(PractitionerCRUD):
    """健康管理师CRUD服务"""
    
    def __init__(self, db: AsyncIOMotorDatabase, model_class: Type[HealthManager]):
        super().__init__(db, model_class)
        self.role = "health_manager"


class OrganizationCRUD(CRUDBase[Organization]):
    """组织机构CRUD服务"""
    
    async def find_by_type(self, type: str, skip: int = 0, limit: int = 100) -> List[Organization]:
        """查找特定类型的组织"""
        return await self.find({"type": type}, skip, limit)
    
    async def find_children(self, parent_id: str, skip: int = 0, limit: int = 100) -> List[Organization]:
        """查找子组织"""
        return await self.find({"parent_id": parent_id}, skip, limit)
    
    async def get_hierarchy(self, org_id: str) -> List[Organization]:
        """获取组织层级"""
        result = []
        org = await self.get(org_id)
        
        while org:
            result.append(org)
            if org.parent_id:
                org = await self.get(org.parent_id)
            else:
                break
                
        return result


class RecordBaseCRUD(CRUDBase[TypeVar('T')]):
    """记录CRUD服务基类"""
    
    async def find_by_patient(self, patient_id: str, skip: int = 0, limit: int = 100) -> List[Any]:
        """查找患者的记录"""
        return await self.find({"patient_id": patient_id}, skip, limit)
    
    async def find_by_creator(self, creator_id: str, skip: int = 0, limit: int = 100) -> List[Any]:
        """查找由特定人员创建的记录"""
        return await self.find({"created_by": creator_id}, skip, limit)


class HealthRecordCRUD(RecordBaseCRUD[HealthRecord]):
    """健康档案CRUD服务"""
    
    async def find_by_type(self, patient_id: str, record_type: str, skip: int = 0, limit: int = 100) -> List[HealthRecord]:
        """查找患者的特定类型健康档案"""
        return await self.find({"patient_id": patient_id, "record_type": record_type}, skip, limit)


class FollowUpRecordCRUD(RecordBaseCRUD[FollowUpRecord]):
    """随访记录CRUD服务"""
    
    async def find_upcoming(self, skip: int = 0, limit: int = 100) -> List[FollowUpRecord]:
        """查找即将到来的随访"""
        now = datetime.utcnow()
        return await self.find({
            "status": "scheduled",
            "scheduled_date": {"$gt": now}
        }, skip, limit)
    
    async def find_overdue(self, skip: int = 0, limit: int = 100) -> List[FollowUpRecord]:
        """查找逾期随访"""
        now = datetime.utcnow()
        return await self.find({
            "status": "scheduled",
            "scheduled_date": {"$lt": now}
        }, skip, limit)


class RehabilitationPlanCRUD(RecordBaseCRUD[RehabilitationPlan]):
    """康复计划CRUD服务"""
    
    async def find_by_practitioner(self, practitioner_id: str, skip: int = 0, limit: int = 100) -> List[RehabilitationPlan]:
        """查找医生创建的康复计划"""
        return await self.find({"practitioner_id": practitioner_id}, skip, limit)
    
    async def find_active(self, patient_id: str = None, skip: int = 0, limit: int = 100) -> List[RehabilitationPlan]:
        """查找活跃的康复计划"""
        filter = {"status": "active"}
        if patient_id:
            filter["patient_id"] = patient_id
        return await self.find(filter, skip, limit)


class ExerciseCRUD(CRUDBase[Exercise]):
    """锻炼CRUD服务"""
    
    async def find_by_body_part(self, body_part: str, skip: int = 0, limit: int = 100) -> List[Exercise]:
        """查找特定身体部位的锻炼"""
        return await self.find({"body_part": body_part}, skip, limit)
    
    async def find_by_difficulty(self, difficulty: str, skip: int = 0, limit: int = 100) -> List[Exercise]:
        """查找特定难度的锻炼"""
        return await self.find({"difficulty": difficulty}, skip, limit)
    
    async def find_by_tag(self, tag: str, skip: int = 0, limit: int = 100) -> List[Exercise]:
        """查找带有特定标签的锻炼"""
        return await self.find({"tags": tag}, skip, limit)


class ProgressRecordCRUD(RecordBaseCRUD[ProgressRecord]):
    """进度记录CRUD服务"""
    
    async def find_by_plan(self, plan_id: str, skip: int = 0, limit: int = 100) -> List[ProgressRecord]:
        """查找康复计划的进度记录"""
        return await self.find({"plan_id": plan_id}, skip, limit)
    
    async def find_by_exercise(self, plan_id: str, exercise_id: str, skip: int = 0, limit: int = 100) -> List[ProgressRecord]:
        """查找特定锻炼的进度记录"""
        return await self.find({"plan_id": plan_id, "exercise_id": exercise_id}, skip, limit)
    
    async def find_recent(self, patient_id: str, days: int = 7, skip: int = 0, limit: int = 100) -> List[ProgressRecord]:
        """查找患者的最近进度记录"""
        start_date = datetime.utcnow() - timedelta(days=days)
        return await self.find({
            "patient_id": patient_id,
            "date": {"$gte": start_date}
        }, skip, limit)


class DeviceRelatedCRUD(CRUDBase[TypeVar('T')]):
    """设备相关CRUD服务基类"""
    
    async def find_by_patient(self, patient_id: str, skip: int = 0, limit: int = 100) -> List[Any]:
        """查找患者的设备相关数据"""
        return await self.find({"patient_id": patient_id}, skip, limit)
    
    async def find_by_type(self, type_field: str, skip: int = 0, limit: int = 100) -> List[Any]:
        """查找特定类型的设备相关数据"""
        field_name = f"{self.type_field_name}" if hasattr(self, 'type_field_name') else "device_type"
        return await self.find({field_name: type_field}, skip, limit)


class DeviceCRUD(DeviceRelatedCRUD[Device]):
    """设备CRUD服务"""
    
    def __init__(self, db: AsyncIOMotorDatabase, model_class: Type[Device]):
        super().__init__(db, model_class)
        self.type_field_name = "device_type"
    
    async def find_by_status(self, status: str, skip: int = 0, limit: int = 100) -> List[Device]:
        """查找特定状态的设备"""
        return await self.find({"status": status}, skip, limit)
    
    async def find_unbound(self, skip: int = 0, limit: int = 100) -> List[Device]:
        """查找未绑定的设备"""
        return await self.find({"patient_id": None}, skip, limit)


class DeviceDataCRUD(DeviceRelatedCRUD[DeviceData]):
    """设备数据CRUD服务"""
    
    def __init__(self, db: AsyncIOMotorDatabase, model_class: Type[DeviceData]):
        super().__init__(db, model_class)
        self.type_field_name = "data_type"
    
    async def find_by_device(self, device_id: str, skip: int = 0, limit: int = 100) -> List[DeviceData]:
        """查找设备的数据"""
        return await self.find({"device_id": device_id}, skip, limit)
    
    async def find_by_time_range(self, device_id: str, start_time: datetime, end_time: datetime, 
                               skip: int = 0, limit: int = 100) -> List[DeviceData]:
        """查找特定时间范围的设备数据"""
        return await self.find({
            "device_id": device_id,
            "timestamp": {"$gte": start_time, "$lte": end_time}
        }, skip, limit)


class AgentCRUD(CRUDBase[Agent]):
    """代理CRUD服务"""
    
    async def find_public(self, skip: int = 0, limit: int = 100) -> List[Agent]:
        """查找公开的代理"""
        return await self.find({"is_public": True}, skip, limit)
    
    async def find_by_creator(self, creator_id: str, skip: int = 0, limit: int = 100) -> List[Agent]:
        """查找由特定用户创建的代理"""
        return await self.find({"created_by": creator_id}, skip, limit)
    
    async def find_by_organization(self, organization_id: str, skip: int = 0, limit: int = 100) -> List[Agent]:
        """查找特定组织的代理"""
        return await self.find({"organization_id": organization_id}, skip, limit)
    
    async def find_by_model(self, model: str, skip: int = 0, limit: int = 100) -> List[Agent]:
        """查找使用特定模型的代理"""
        return await self.find({"model": model}, skip, limit)


class MessageCRUD(CRUDBase[Message]):
    """消息CRUD服务"""
    
    async def find_by_conversation(self, conversation_id: str, skip: int = 0, limit: int = 100) -> List[Message]:
        """查找对话的消息"""
        return await self.find({"conversation_id": conversation_id}, skip, limit)
    
    async def find_by_sender(self, sender_id: str, skip: int = 0, limit: int = 100) -> List[Message]:
        """查找由特定发送者发送的消息"""
        return await self.find({"sender_id": sender_id}, skip, limit)
    
    async def mark_as_read(self, message_id: str) -> bool:
        """标记消息为已读"""
        try:
            result = await self.collection.update_one(
                {"_id": ObjectId(message_id)},
                {"$set": {"is_read": True, "read_at": datetime.utcnow()}}
            )
            return result.modified_count > 0
        except Exception:
            return False
    
    async def count_unread(self, conversation_id: str, user_id: str) -> int:
        """计算用户在对话中的未读消息数"""
        try:
            return await self.collection.count_documents({
                "conversation_id": conversation_id,
                "sender_id": {"$ne": user_id},
                "is_read": False
            })
        except Exception:
            return 0


class ConversationCRUD(CRUDBase[Conversation]):
    """对话CRUD服务"""
    
    async def find_by_participant(self, user_id: str, skip: int = 0, limit: int = 100) -> List[Conversation]:
        """查找用户参与的对话"""
        return await self.find({"participants.user_id": user_id}, skip, limit)
    
    async def find_by_participants(self, user_ids: List[str], is_group: bool = False, skip: int = 0, limit: int = 100) -> List[Conversation]:
        """查找特定用户之间的对话"""
        # 根据是否为群组构建不同查询条件
        if is_group:
            query = {"participants.user_id": {"$all": user_ids}, "is_group": True}
        else:
            query = {
                "$and": [
                    {"participants.user_id": {"$all": user_ids}},
                    {"$expr": {"$eq": [{"$size": "$participants"}, len(user_ids)]}},
                    {"is_group": False}
                ]
            }
        
        return await self.find(query, skip, limit)
    
    async def find_active(self, user_id: str = None, skip: int = 0, limit: int = 100) -> List[Conversation]:
        """查找活跃的对话"""
        query = {"status": "active"}
        if user_id:
            query["participants.user_id"] = user_id
        
        return await self.find(query, skip, limit)


# 创建CRUD服务工厂函数
def get_crud_services(db: AsyncIOMotorDatabase):
    """获取所有CRUD服务"""
    return {
        "user": UserCRUD(db, User),
        "doctor": DoctorCRUD(db, Doctor),
        "patient": PatientCRUD(db, Patient),
        "health_manager": HealthManagerCRUD(db, HealthManager),
        "organization": OrganizationCRUD(db, Organization),
        "health_record": HealthRecordCRUD(db, HealthRecord),
        "followup_record": FollowUpRecordCRUD(db, FollowUpRecord),
        "rehabilitation_plan": RehabilitationPlanCRUD(db, RehabilitationPlan),
        "exercise": ExerciseCRUD(db, Exercise),
        "progress_record": ProgressRecordCRUD(db, ProgressRecord),
        "device": DeviceCRUD(db, Device),
        "device_data": DeviceDataCRUD(db, DeviceData),
        "agent": AgentCRUD(db, Agent),
        "message": MessageCRUD(db, Message),
        "conversation": ConversationCRUD(db, Conversation),
    } 
"""
模型CRUD服务
为各模型提供特定的CRUD操作
"""
from typing import List, Dict, Any, Optional
from motor.motor_asyncio import AsyncIOMotorDatabase
from datetime import datetime

from app.db.crud import CRUDBase
from app.models.user import User, Doctor, Patient, HealthManager, SystemAdmin
from app.models.organization import Organization
from app.models.health_record import HealthRecord, FollowUpRecord
from app.models.rehabilitation import RehabilitationPlan, Exercise, ProgressRecord
from app.models.device import Device, DeviceData, DeviceCalibration
from app.models.agent import Agent, AgentInteraction
from app.models.communication import Message, Conversation


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
                {"_id": user_id},
                {"$set": {"password_hash": password_hash, "updated_at": datetime.utcnow()}}
            )
            return result.modified_count > 0
        except Exception:
            return False


class DoctorCRUD(CRUDBase[Doctor]):
    """医生CRUD服务"""
    
    async def find_by_organization(self, organization_id: str, skip: int = 0, limit: int = 100) -> List[Doctor]:
        """查找某组织的医生"""
        return await self.find({"organization_id": organization_id, "role": "doctor"}, skip, limit)
    
    async def find_by_specialty(self, specialty: str, skip: int = 0, limit: int = 100) -> List[Doctor]:
        """查找特定专业的医生"""
        return await self.find({"specialty": specialty, "role": "doctor"}, skip, limit)
    
    async def get_patients(self, doctor_id: str) -> List[str]:
        """获取医生的患者ID列表"""
        doctor = await self.get(doctor_id)
        return doctor.patients if doctor else []
    
    async def add_patient(self, doctor_id: str, patient_id: str) -> bool:
        """为医生添加患者"""
        try:
            result = await self.collection.update_one(
                {"_id": doctor_id, "role": "doctor"},
                {"$addToSet": {"patients": patient_id}}
            )
            return result.modified_count > 0
        except Exception:
            return False


class PatientCRUD(CRUDBase[Patient]):
    """患者CRUD服务"""
    
    async def find_by_doctors(self, doctor_id: str, skip: int = 0, limit: int = 100) -> List[Patient]:
        """查找某医生的患者"""
        return await self.find({"practitioners": doctor_id, "role": "patient"}, skip, limit)
    
    async def find_by_health_manager(self, health_manager_id: str, skip: int = 0, limit: int = 100) -> List[Patient]:
        """查找某健康管理师的患者"""
        return await self.find({"health_managers": health_manager_id, "role": "patient"}, skip, limit)
    
    async def update_medical_info(self, patient_id: str, medical_info: Dict[str, Any]) -> bool:
        """更新患者医疗信息"""
        try:
            result = await self.collection.update_one(
                {"_id": patient_id, "role": "patient"},
                {"$set": {"medical_info": medical_info, "updated_at": datetime.utcnow()}}
            )
            return result.modified_count > 0
        except Exception:
            return False
    
    async def add_device(self, patient_id: str, device_id: str) -> bool:
        """为患者添加设备"""
        try:
            result = await self.collection.update_one(
                {"_id": patient_id, "role": "patient"},
                {"$addToSet": {"devices": device_id}}
            )
            return result.modified_count > 0
        except Exception:
            return False


class HealthManagerCRUD(CRUDBase[HealthManager]):
    """健康管理师CRUD服务"""
    
    async def find_by_organization(self, organization_id: str, skip: int = 0, limit: int = 100) -> List[HealthManager]:
        """查找某组织的健康管理师"""
        return await self.find({"organization_id": organization_id, "role": "health_manager"}, skip, limit)
    
    async def get_patients(self, health_manager_id: str) -> List[str]:
        """获取健康管理师的患者ID列表"""
        manager = await self.get(health_manager_id)
        return manager.patients if manager else []
    
    async def add_patient(self, health_manager_id: str, patient_id: str) -> bool:
        """为健康管理师添加患者"""
        try:
            result = await self.collection.update_one(
                {"_id": health_manager_id, "role": "health_manager"},
                {"$addToSet": {"patients": patient_id}}
            )
            return result.modified_count > 0
        except Exception:
            return False


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


class HealthRecordCRUD(CRUDBase[HealthRecord]):
    """健康档案CRUD服务"""
    
    async def find_by_patient(self, patient_id: str, skip: int = 0, limit: int = 100) -> List[HealthRecord]:
        """查找患者的健康档案"""
        return await self.find({"patient_id": patient_id}, skip, limit)
    
    async def find_by_type(self, patient_id: str, record_type: str, skip: int = 0, limit: int = 100) -> List[HealthRecord]:
        """查找患者的特定类型健康档案"""
        return await self.find({"patient_id": patient_id, "record_type": record_type}, skip, limit)
    
    async def find_by_creator(self, creator_id: str, skip: int = 0, limit: int = 100) -> List[HealthRecord]:
        """查找由特定人员创建的健康档案"""
        return await self.find({"created_by": creator_id}, skip, limit)


class FollowUpRecordCRUD(CRUDBase[FollowUpRecord]):
    """随访记录CRUD服务"""
    
    async def find_by_patient(self, patient_id: str, skip: int = 0, limit: int = 100) -> List[FollowUpRecord]:
        """查找患者的随访记录"""
        return await self.find({"patient_id": patient_id}, skip, limit)
    
    async def find_by_creator(self, creator_id: str, skip: int = 0, limit: int = 100) -> List[FollowUpRecord]:
        """查找由特定人员创建的随访记录"""
        return await self.find({"created_by": creator_id}, skip, limit)
    
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


class RehabilitationPlanCRUD(CRUDBase[RehabilitationPlan]):
    """康复计划CRUD服务"""
    
    async def find_by_patient(self, patient_id: str, skip: int = 0, limit: int = 100) -> List[RehabilitationPlan]:
        """查找患者的康复计划"""
        return await self.find({"patient_id": patient_id}, skip, limit)
    
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


class ProgressRecordCRUD(CRUDBase[ProgressRecord]):
    """进度记录CRUD服务"""
    
    async def find_by_plan(self, plan_id: str, skip: int = 0, limit: int = 100) -> List[ProgressRecord]:
        """查找康复计划的进度记录"""
        return await self.find({"plan_id": plan_id}, skip, limit)
    
    async def find_by_exercise(self, plan_id: str, exercise_id: str, skip: int = 0, limit: int = 100) -> List[ProgressRecord]:
        """查找特定锻炼的进度记录"""
        return await self.find({"plan_id": plan_id, "exercise_id": exercise_id}, skip, limit)
    
    async def find_recent(self, patient_id: str, days: int = 7, skip: int = 0, limit: int = 100) -> List[ProgressRecord]:
        """查找患者的最近进度记录"""
        from datetime import timedelta
        start_date = datetime.utcnow() - timedelta(days=days)
        return await self.find({
            "patient_id": patient_id,
            "date": {"$gte": start_date}
        }, skip, limit)


class DeviceCRUD(CRUDBase[Device]):
    """设备CRUD服务"""
    
    async def find_by_patient(self, patient_id: str, skip: int = 0, limit: int = 100) -> List[Device]:
        """查找患者的设备"""
        return await self.find({"patient_id": patient_id}, skip, limit)
    
    async def find_by_type(self, device_type: str, skip: int = 0, limit: int = 100) -> List[Device]:
        """查找特定类型的设备"""
        return await self.find({"device_type": device_type}, skip, limit)
    
    async def find_by_status(self, status: str, skip: int = 0, limit: int = 100) -> List[Device]:
        """查找特定状态的设备"""
        return await self.find({"status": status}, skip, limit)
    
    async def find_unbound(self, skip: int = 0, limit: int = 100) -> List[Device]:
        """查找未绑定的设备"""
        return await self.find({"patient_id": None}, skip, limit)


class DeviceDataCRUD(CRUDBase[DeviceData]):
    """设备数据CRUD服务"""
    
    async def find_by_device(self, device_id: str, skip: int = 0, limit: int = 100) -> List[DeviceData]:
        """查找设备的数据"""
        return await self.find({"device_id": device_id}, skip, limit)
    
    async def find_by_patient(self, patient_id: str, skip: int = 0, limit: int = 100) -> List[DeviceData]:
        """查找患者的设备数据"""
        return await self.find({"patient_id": patient_id}, skip, limit)
    
    async def find_by_type(self, data_type: str, skip: int = 0, limit: int = 100) -> List[DeviceData]:
        """查找特定类型的设备数据"""
        return await self.find({"data_type": data_type}, skip, limit)
    
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
                {"_id": message_id},
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
        # 构建查询条件：所有指定用户都是参与者，且参与者数量等于指定用户数量（即精确匹配）
        if is_group:
            # 对于群组对话，只要包含所有指定用户即可
            query = {"participants.user_id": {"$all": user_ids}, "is_group": True}
        else:
            # 对于一对一对话，参与者必须精确匹配
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
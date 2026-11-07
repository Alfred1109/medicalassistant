"""数据模型包
包含所有MongoDB数据模型定义
"""

from .user import User, Doctor, Patient, HealthManager, SystemAdmin
from .organization import Organization
from .health_record import HealthRecord, FollowUpRecord
from .rehabilitation import RehabilitationPlan, Exercise
from .device import Device, DeviceData
from .agent import Agent, AgentTool
# WS01 统一后：原 Message/Conversation 模型类（结构 A）已删除，
# 通信域唯一真实结构见 app/services/communication_service.py。
from .communication import Notification
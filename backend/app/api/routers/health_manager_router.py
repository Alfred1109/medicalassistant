from fastapi import APIRouter, Depends, HTTPException, Query, status
from typing import List, Optional
from app.schemas.user import UserResponse
from app.schemas.followup import FollowUpRecordCreate, FollowUpRecordResponse
from app.core.dependencies import get_current_user, get_followup_service
from app.services.followup_service import FollowupService
from app.core.followup_access import ensure_followup_patient_access, followup_patient_scope

router = APIRouter()

# 健康管理师功能路由

# 患者管理
@router.get("/patients", response_model=List[dict])
async def get_manager_patients(current_user: UserResponse = Depends(get_current_user)):
    """获取健康管理师管理的患者列表"""
    if current_user.role != "health_manager":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
    # 这里调用相应的服务层功能
    return []

# 健康档案
@router.get("/health-records/{patient_id}", response_model=dict)
async def get_patient_health_record(
    patient_id: str, 
    current_user: UserResponse = Depends(get_current_user)
):
    """获取患者健康档案"""
    if current_user.role != "health_manager":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
    # 这里调用相应的服务层功能
    return {}

# 随访管理
# FU01 S2 收敛：/api/health-managers/follow-ups 转调 FollowupService（唯一随访服务入口），
# 与唯一正典入口 /api/health-records/followups 同源同形状，
# 删除 new_follow_up_id 假 ID 存根
@router.get("/follow-ups", response_model=List[FollowUpRecordResponse])
async def get_follow_ups(
    patient_id: Optional[str] = Query(None, description="患者ID，不提供则返回全部随访"),
    followup_status: Optional[str] = Query(None, alias="status"),
    current_user: UserResponse = Depends(get_current_user),
    followup_service: FollowupService = Depends(get_followup_service)
):
    """获取随访列表（转调 FollowupService，同源同形状）"""
    if current_user.role != "health_manager":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
    if patient_id:
        await ensure_followup_patient_access(followup_service.db, patient_id, current_user)
    scope = await followup_patient_scope(followup_service.db, current_user)
    return await followup_service.list_all_followups(
        patient_id=patient_id, status=followup_status, patient_ids=scope)

@router.post("/follow-ups", status_code=status.HTTP_201_CREATED, response_model=FollowUpRecordResponse)
async def create_follow_up(
    follow_up_data: FollowUpRecordCreate,
    current_user: UserResponse = Depends(get_current_user),
    followup_service: FollowupService = Depends(get_followup_service)
):
    """创建随访计划（转调 FollowupService，返回真实记录 ID 与响应契约）"""
    if current_user.role != "health_manager":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
    # 创建人缺省为当前健康管理师（与 canonical 创建端点一致；provider_id 为必填契约字段）
    await ensure_followup_patient_access(followup_service.db, follow_up_data.patient_id, current_user, write=True)
    follow_up_data.created_by = current_user.id
    return await followup_service.create_followup_record(follow_up_data)

# 数据监测
@router.get("/patient-monitoring/{patient_id}", response_model=dict)
async def get_patient_monitoring_data(
    patient_id: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    current_user: UserResponse = Depends(get_current_user)
):
    """获取患者监测数据"""
    if current_user.role != "health_manager":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
    # 这里调用相应的服务层功能
    return {}

# 医患沟通
@router.get("/communications", response_model=List[dict])
async def get_communications(
    patient_id: Optional[str] = None,
    current_user: UserResponse = Depends(get_current_user)
):
    """获取与患者的沟通记录"""
    if current_user.role != "health_manager":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
    # 这里调用相应的服务层功能
    return []

@router.post("/communications", status_code=status.HTTP_201_CREATED)
async def create_communication(
    message_data: dict,
    current_user: UserResponse = Depends(get_current_user)
):
    """创建新的沟通消息"""
    if current_user.role != "health_manager":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
    # 这里调用相应的服务层功能
    return {"id": "new_message_id"}

# 数据统计
@router.get("/statistics", response_model=dict)
async def get_manager_statistics(
    time_range: Optional[str] = "month",
    current_user: UserResponse = Depends(get_current_user)
):
    """获取健康管理师工作统计数据"""
    if current_user.role != "health_manager":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
    # 这里调用相应的服务层功能
    return {} 
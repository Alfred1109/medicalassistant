from fastapi import APIRouter, Depends, HTTPException, Query, status
from typing import List, Optional
from app.schemas.user import UserResponse
from app.schemas.followup import FollowUpRecordCreate, FollowUpRecordResponse
from app.api.dependencies import get_current_user, get_followup_service, get_database
from app.core.exceptions import AppBaseException
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.db.crud_services import PatientCRUD
from app.models.user import Patient
from app.services.followup_service import FollowupService
from app.core.followup_access import ensure_followup_patient_access, followup_patient_scope
from app.api.routers.doctor_router import (
    collect_work_statistics, load_provider_health_record, load_provider_monitoring)

router = APIRouter()

# 健康管理师功能路由

# 患者管理
@router.get("/patients", response_model=List[dict])
async def get_manager_patients(
    skip: int = Query(0, description="分页偏移量，缺省 0（不翻页）"),
    limit: Optional[int] = Query(None, description="每页数量（1-200）；缺省不传=一次性全量"),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """获取健康管理师管理的患者列表

    skip/limit 与医生列表同一约束：缺省不传 limit 时保持原全量行为。
    """
    if current_user.role != "health_manager":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
    try:
        return await PatientCRUD(db, Patient).find_assigned_patients(
            str(current_user.id), current_user.role, skip=skip, limit=limit)
    except AppBaseException:
        # 适配器的患者标识歧义（PATIENT_IDENTITY_AMBIGUOUS/503）等业务异常
        # 保留全局处理器语义，不降级为 500（与 doctor_router 同一修法）
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail="获取患者列表失败，请稍后重试") from exc

# 健康档案
@router.get("/health-records/{patient_id}", response_model=dict)
async def get_patient_health_record(
    patient_id: str,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """获取患者健康档案（与医生端同一读取，按健康管理师归属授权）"""
    if current_user.role != "health_manager":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
    try:
        return await load_provider_health_record(
            db, patient_id, current_user.id, current_user.role)
    except (HTTPException, AppBaseException):
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail="获取健康档案失败，请稍后重试") from exc

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
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """获取患者监测快照（与医生端同一聚合，按健康管理师归属授权）

    start_date/end_date 为历史签名保留，当前快照不按时间切片。
    """
    if current_user.role != "health_manager":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
    try:
        return await load_provider_monitoring(
            db, patient_id, current_user.id, current_user.role)
    except (HTTPException, AppBaseException):
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail="获取患者监测数据失败，请稍后重试") from exc

# 数据统计
# 医患消息走 /api/communications，这里不再保留空列表或假消息 ID。
@router.get("/statistics", response_model=dict)
async def get_manager_statistics(
    time_range: Optional[str] = "month",
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
    followup_service: FollowupService = Depends(get_followup_service)
):
    """获取健康管理师工作统计数据（真实聚合，2026-11-15 替换存根空对象）

    字段语义（均来自真实集合，无数据时如实为 0）：
    - patientCount: health_managers 中关联本人的真实患者数
                    （归属走 assigned_scope_ids，与对象授权同源）
    - rehabPlans:   本人归属患者范围内的康复计划总数/进行中/已完成
                    （rehab_plans 集合，status: active/completed）
    - followUps:    本人归属患者范围内的随访记录总数/已完成/待完成
                    （followup_records，与 FollowupService 口径同源：
                    排除已删除节点；待完成 = 未终结且仍需跟进的状态）
    - completedSessionsThisMonth: 本人患者本月完成的训练进度记录数
                    （rehab_progress，completed=true 且 date 不早于本月；
                    该集合当前无写入方，通常为 0 —— 是真实空数据而非存根）
    - implemented:  显式标记端点已实现真实聚合

    与医生端共用 collect_work_statistics（唯一聚合实现），差异只在康复
    方案的归属口径（见该函数说明）与随访统计的开关。
    """
    if current_user.role != "health_manager":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
    try:
        statistics = await collect_work_statistics(
            db,
            operator_id=current_user.id,
            operator_role="health_manager",
            plan_scope="patients",
            operator_label="健康管理师",
            followup_service=followup_service,
        )
        statistics["timeRange"] = time_range
        return statistics
    except (HTTPException, AppBaseException):
        # PatientAccessError 与适配器的 LegacyPatientIdentityError 均为 AppBaseException
        raise
    except Exception as e:
        print(f"获取健康管理师统计数据时出错: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取健康管理师统计数据失败，请稍后重试"
        )

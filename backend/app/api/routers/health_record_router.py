"""
健康档案API路由
提供健康档案、随访记录和健康数据的CRUD操作接口
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Body, Path
from datetime import datetime

from app.core.dependencies import (
    get_current_user, 
    get_health_record_service,
    check_permission, 
    is_doctor, 
    is_medical_staff, 
    is_patient,
    is_health_manager
)
from app.services.health_record_service import HealthRecordService
from app.models.user import User
from app.schemas.health_record import (
    HealthRecordCreate, HealthRecordUpdate, HealthRecordResponse,
    FollowUpRecordCreate, FollowUpRecordUpdate, FollowUpRecordResponse,
    CompleteFollowUpRequest, CancelFollowUpRequest, RescheduleFollowUpRequest,
    HealthDataCreate, HealthDataResponse, HealthRecordStats, HealthTimelineItem,
    RecordType, FollowUpType, FollowUpStatus
)
from app.core.permissions import Permission

router = APIRouter(prefix="/health-records", tags=["健康档案"])

# -------- 健康档案管理 --------

@router.post("", response_model=HealthRecordResponse)
async def create_health_record(
    record_data: HealthRecordCreate,
    current_user: User = Depends(get_current_user),
    health_record_service: HealthRecordService = Depends(get_health_record_service),
    _: bool = Depends(is_medical_staff)
):
    """
    创建健康档案
    
    - **只有医疗人员可以创建健康档案**
    - 需要提供患者ID、记录类型、标题和内容
    """
    # 设置创建者为当前用户
    if not record_data.created_by:
        record_data.created_by = current_user.id
    
    # 创建档案
    result = await health_record_service.create_health_record(record_data)
    if not result:
        raise HTTPException(status_code=500, detail="创建健康档案失败")
    
    return result

@router.get("/{record_id}", response_model=HealthRecordResponse)
async def get_health_record(
    record_id: str = Path(..., description="健康档案ID"),
    current_user: User = Depends(get_current_user),
    health_record_service: HealthRecordService = Depends(get_health_record_service)
):
    """
    获取健康档案
    
    - 患者只能查看自己的健康档案
    - 医疗人员可以查看其负责的患者档案
    - 健康管理员可以查看所有档案
    """
    # 获取档案
    result = await health_record_service.get_health_record(record_id)
    if not result:
        raise HTTPException(status_code=404, detail="健康档案不存在")
    
    # 访问控制
    if (current_user.user_type == "patient" and result.patient_id != current_user.id and 
        not await check_permission(current_user, Permission.VIEW_ANY_HEALTH_RECORD)):
        raise HTTPException(status_code=403, detail="无权访问该健康档案")
    
    return result

@router.put("/{record_id}", response_model=HealthRecordResponse)
async def update_health_record(
    record_data: HealthRecordUpdate,
    record_id: str = Path(..., description="健康档案ID"),
    current_user: User = Depends(get_current_user),
    health_record_service: HealthRecordService = Depends(get_health_record_service),
    _: bool = Depends(is_medical_staff)
):
    """
    更新健康档案
    
    - **只有医疗人员可以更新健康档案**
    - 可以更新标题、内容、附件、标签等字段
    - 内容更新会自动创建版本历史
    """
    # 获取档案
    record = await health_record_service.get_health_record(record_id)
    if not record:
        raise HTTPException(status_code=404, detail="健康档案不存在")
    
    # 更新档案
    result = await health_record_service.update_health_record(
        record_id=record_id,
        record_data=record_data,
        updated_by=current_user.id
    )
    
    if not result:
        raise HTTPException(status_code=500, detail="更新健康档案失败")
    
    return result

@router.delete("/{record_id}", response_model=bool)
async def delete_health_record(
    record_id: str = Path(..., description="健康档案ID"),
    current_user: User = Depends(get_current_user),
    health_record_service: HealthRecordService = Depends(get_health_record_service),
    _: bool = Depends(check_permission(Permission.DELETE_HEALTH_RECORD))
):
    """
    删除健康档案
    
    - **需要删除健康档案权限**
    """
    # 删除档案
    result = await health_record_service.delete_health_record(record_id)
    if not result:
        raise HTTPException(status_code=404, detail="健康档案不存在或删除失败")
    
    return True

@router.get("", response_model=List[HealthRecordResponse])
async def list_health_records(
    patient_id: str = Query(..., description="患者ID"),
    record_type: Optional[str] = Query(None, description="记录类型"),
    start_date: Optional[datetime] = Query(None, description="开始日期"),
    end_date: Optional[datetime] = Query(None, description="结束日期"),
    skip: int = Query(0, description="分页偏移量"),
    limit: int = Query(100, description="每页数量"),
    current_user: User = Depends(get_current_user),
    health_record_service: HealthRecordService = Depends(get_health_record_service)
):
    """
    列出患者的健康档案
    
    - 患者只能查看自己的健康档案
    - 医疗人员可以查看其负责的患者档案
    - 健康管理员可以查看所有档案
    - 可以按记录类型和日期范围筛选
    """
    # 访问控制
    if (current_user.user_type == "patient" and patient_id != current_user.id and 
        not await check_permission(current_user, Permission.VIEW_ANY_HEALTH_RECORD)):
        raise HTTPException(status_code=403, detail="无权访问该患者的健康档案")
    
    # 获取档案列表
    result = await health_record_service.list_health_records(
        patient_id=patient_id,
        record_type=record_type,
        start_date=start_date,
        end_date=end_date,
        skip=skip,
        limit=limit
    )
    
    return result

@router.get("/version/{record_id}/{version_number}")
async def get_health_record_version(
    record_id: str = Path(..., description="健康档案ID"),
    version_number: int = Path(..., description="版本号"),
    current_user: User = Depends(get_current_user),
    health_record_service: HealthRecordService = Depends(get_health_record_service)
):
    """
    获取健康档案的特定版本
    
    - 返回健康档案的历史版本内容
    - 版本从1开始计数
    """
    # 获取档案
    record = await health_record_service.get_health_record(record_id)
    if not record:
        raise HTTPException(status_code=404, detail="健康档案不存在")
    
    # 访问控制
    if (current_user.user_type == "patient" and record.patient_id != current_user.id and 
        not await check_permission(current_user, Permission.VIEW_ANY_HEALTH_RECORD)):
        raise HTTPException(status_code=403, detail="无权访问该健康档案")
    
    # 获取版本
    version = await health_record_service.get_health_record_version(record_id, version_number)
    if not version:
        raise HTTPException(status_code=404, detail="版本不存在")
    
    return version

@router.get("/stats/{patient_id}", response_model=HealthRecordStats)
async def get_health_record_stats(
    patient_id: str = Path(..., description="患者ID"),
    current_user: User = Depends(get_current_user),
    health_record_service: HealthRecordService = Depends(get_health_record_service)
):
    """
    获取患者健康档案统计信息
    
    - 返回总记录数、记录类型分布、最近更新、即将到来的随访等统计信息
    """
    # 访问控制
    if (current_user.user_type == "patient" and patient_id != current_user.id and 
        not await check_permission(current_user, Permission.VIEW_ANY_HEALTH_RECORD)):
        raise HTTPException(status_code=403, detail="无权访问该患者的健康档案")
    
    # 获取统计信息
    result = await health_record_service.get_health_record_stats(patient_id)
    
    return result

# -------- 随访记录管理 --------

@router.post("/followups", response_model=FollowUpRecordResponse)
async def create_followup_record(
    followup_data: FollowUpRecordCreate,
    current_user: User = Depends(get_current_user),
    health_record_service: HealthRecordService = Depends(get_health_record_service),
    _: bool = Depends(is_medical_staff)
):
    """
    创建随访记录
    
    - **只有医疗人员可以创建随访记录**
    - 需要提供患者ID、随访类型、计划日期等信息
    """
    # 设置创建者为当前用户
    if not followup_data.created_by:
        followup_data.created_by = current_user.id
    
    # 创建随访记录
    result = await health_record_service.create_followup_record(followup_data)
    if not result:
        raise HTTPException(status_code=500, detail="创建随访记录失败")
    
    return result

@router.get("/followups/{followup_id}", response_model=FollowUpRecordResponse)
async def get_followup_record(
    followup_id: str = Path(..., description="随访记录ID"),
    current_user: User = Depends(get_current_user),
    health_record_service: HealthRecordService = Depends(get_health_record_service)
):
    """
    获取随访记录
    
    - 患者只能查看自己的随访记录
    - 医疗人员可以查看其负责的患者随访记录
    - 健康管理员可以查看所有随访记录
    """
    # 获取随访记录
    result = await health_record_service.get_followup_record(followup_id)
    if not result:
        raise HTTPException(status_code=404, detail="随访记录不存在")
    
    # 访问控制
    if (current_user.user_type == "patient" and result.patient_id != current_user.id and 
        not await check_permission(current_user, Permission.VIEW_ANY_HEALTH_RECORD)):
        raise HTTPException(status_code=403, detail="无权访问该随访记录")
    
    return result

@router.put("/followups/{followup_id}", response_model=FollowUpRecordResponse)
async def update_followup_record(
    followup_data: FollowUpRecordUpdate,
    followup_id: str = Path(..., description="随访记录ID"),
    current_user: User = Depends(get_current_user),
    health_record_service: HealthRecordService = Depends(get_health_record_service),
    _: bool = Depends(is_medical_staff)
):
    """
    更新随访记录
    
    - **只有医疗人员可以更新随访记录**
    - 可以更新随访类型、日期、状态、备注等字段
    """
    # 获取随访记录
    followup = await health_record_service.get_followup_record(followup_id)
    if not followup:
        raise HTTPException(status_code=404, detail="随访记录不存在")
    
    # 更新随访记录
    result = await health_record_service.update_followup_record(
        followup_id=followup_id,
        followup_data=followup_data
    )
    
    if not result:
        raise HTTPException(status_code=500, detail="更新随访记录失败")
    
    return result

@router.post("/followups/{followup_id}/complete", response_model=FollowUpRecordResponse)
async def complete_followup(
    data: CompleteFollowUpRequest,
    followup_id: str = Path(..., description="随访记录ID"),
    current_user: User = Depends(get_current_user),
    health_record_service: HealthRecordService = Depends(get_health_record_service),
    _: bool = Depends(is_medical_staff)
):
    """
    完成随访
    
    - **只有医疗人员可以完成随访**
    - 需要提供实际日期、备注、回答等信息
    """
    # 完成随访
    result = await health_record_service.complete_followup(followup_id, data)
    if not result:
        raise HTTPException(status_code=404, detail="随访记录不存在")
    
    return result

@router.post("/followups/{followup_id}/cancel", response_model=FollowUpRecordResponse)
async def cancel_followup(
    data: CancelFollowUpRequest,
    followup_id: str = Path(..., description="随访记录ID"),
    current_user: User = Depends(get_current_user),
    health_record_service: HealthRecordService = Depends(get_health_record_service),
    _: bool = Depends(is_medical_staff)
):
    """
    取消随访
    
    - **只有医疗人员可以取消随访**
    - 需要提供取消原因
    - 可以选择性地提供重新安排日期
    """
    # 取消随访
    result = await health_record_service.cancel_followup(followup_id, data)
    if not result:
        raise HTTPException(status_code=404, detail="随访记录不存在")
    
    return result

@router.post("/followups/{followup_id}/reschedule", response_model=FollowUpRecordResponse)
async def reschedule_followup(
    data: RescheduleFollowUpRequest,
    followup_id: str = Path(..., description="随访记录ID"),
    current_user: User = Depends(get_current_user),
    health_record_service: HealthRecordService = Depends(get_health_record_service),
    _: bool = Depends(is_medical_staff)
):
    """
    重新安排随访时间
    
    - **只有医疗人员可以重新安排随访时间**
    - 需要提供新的日期和变更原因
    """
    # 重新安排随访
    result = await health_record_service.reschedule_followup(followup_id, data)
    if not result:
        raise HTTPException(status_code=404, detail="随访记录不存在")
    
    return result

@router.get("/followups", response_model=List[FollowUpRecordResponse])
async def list_followup_records(
    patient_id: str = Query(..., description="患者ID"),
    status: Optional[List[str]] = Query(None, description="状态列表，可多选"),
    follow_up_type: Optional[str] = Query(None, description="随访类型"),
    start_date: Optional[datetime] = Query(None, description="开始日期"),
    end_date: Optional[datetime] = Query(None, description="结束日期"),
    skip: int = Query(0, description="分页偏移量"),
    limit: int = Query(100, description="每页数量"),
    current_user: User = Depends(get_current_user),
    health_record_service: HealthRecordService = Depends(get_health_record_service)
):
    """
    列出患者的随访记录
    
    - 患者只能查看自己的随访记录
    - 医疗人员可以查看其负责的患者随访记录
    - 健康管理员可以查看所有随访记录
    - 可以按状态、类型和日期范围筛选
    """
    # 访问控制
    if (current_user.user_type == "patient" and patient_id != current_user.id and 
        not await check_permission(current_user, Permission.VIEW_ANY_HEALTH_RECORD)):
        raise HTTPException(status_code=403, detail="无权访问该患者的随访记录")
    
    # 获取随访记录列表
    result = await health_record_service.list_followup_records(
        patient_id=patient_id,
        status=status,
        follow_up_type=follow_up_type,
        start_date=start_date,
        end_date=end_date,
        skip=skip,
        limit=limit
    )
    
    return result

@router.get("/followups/upcoming", response_model=List[FollowUpRecordResponse])
async def get_upcoming_followups(
    patient_id: Optional[str] = Query(None, description="患者ID，不提供则获取所有患者的即将到来的随访"),
    days: int = Query(7, description="未来几天内的随访"),
    current_user: User = Depends(get_current_user),
    health_record_service: HealthRecordService = Depends(get_health_record_service)
):
    """
    获取即将到来的随访记录
    
    - 患者只能查看自己的随访记录
    - 医疗人员可以查看其负责的患者随访记录
    - 健康管理员可以查看所有随访记录
    - 默认返回未来7天内的随访记录
    """
    # 访问控制
    if patient_id and current_user.user_type == "patient" and patient_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权访问该患者的随访记录")
    
    # 如果是患者，限制只能查看自己的随访
    if current_user.user_type == "patient" and not patient_id:
        patient_id = current_user.id
    
    # 获取即将到来的随访记录
    result = await health_record_service.get_upcoming_followups(patient_id, days)
    
    return result

@router.get("/related-followups/{record_id}", response_model=List[FollowUpRecordResponse])
async def get_followups_by_health_record(
    record_id: str = Path(..., description="健康档案ID"),
    current_user: User = Depends(get_current_user),
    health_record_service: HealthRecordService = Depends(get_health_record_service)
):
    """
    获取与健康档案关联的随访记录
    
    - 返回与特定健康档案关联的所有随访记录
    """
    # 获取健康档案
    record = await health_record_service.get_health_record(record_id)
    if not record:
        raise HTTPException(status_code=404, detail="健康档案不存在")
    
    # 访问控制
    if (current_user.user_type == "patient" and record.patient_id != current_user.id and 
        not await check_permission(current_user, Permission.VIEW_ANY_HEALTH_RECORD)):
        raise HTTPException(status_code=403, detail="无权访问该健康档案")
    
    # 获取关联的随访记录
    result = await health_record_service.get_followups_by_health_record(record_id)
    
    return result

# -------- 健康数据管理 --------

@router.post("/health-data", response_model=HealthDataResponse)
async def create_health_data(
    data: HealthDataCreate,
    current_user: User = Depends(get_current_user),
    health_record_service: HealthRecordService = Depends(get_health_record_service)
):
    """
    创建健康数据
    
    - 患者可以创建自己的健康数据
    - 医疗人员可以为其负责的患者创建健康数据
    - 需要提供患者ID、数据类型和数据内容
    """
    # 访问控制
    if current_user.user_type == "patient" and data.patient_id != current_user.id:
        raise HTTPException(status_code=403, detail="无法为其他患者创建健康数据")
    
    # 设置记录者为当前用户
    if not data.recorded_by:
        data.recorded_by = current_user.id
    
    # 创建健康数据
    result = await health_record_service.create_health_data(data)
    if not result:
        raise HTTPException(status_code=500, detail="创建健康数据失败")
    
    return result

@router.get("/health-data/{data_id}", response_model=HealthDataResponse)
async def get_health_data(
    data_id: str = Path(..., description="健康数据ID"),
    current_user: User = Depends(get_current_user),
    health_record_service: HealthRecordService = Depends(get_health_record_service)
):
    """
    获取健康数据
    
    - 患者只能查看自己的健康数据
    - 医疗人员可以查看其负责的患者健康数据
    - 健康管理员可以查看所有健康数据
    """
    # 获取健康数据
    result = await health_record_service.get_health_data(data_id)
    if not result:
        raise HTTPException(status_code=404, detail="健康数据不存在")
    
    # 访问控制
    if (current_user.user_type == "patient" and result.patient_id != current_user.id and 
        not await check_permission(current_user, Permission.VIEW_ANY_HEALTH_RECORD)):
        raise HTTPException(status_code=403, detail="无权访问该健康数据")
    
    return result

@router.get("/health-data", response_model=List[HealthDataResponse])
async def list_health_data(
    patient_id: str = Query(..., description="患者ID"),
    data_type: Optional[str] = Query(None, description="数据类型"),
    start_date: Optional[datetime] = Query(None, description="开始日期"),
    end_date: Optional[datetime] = Query(None, description="结束日期"),
    skip: int = Query(0, description="分页偏移量"),
    limit: int = Query(100, description="每页数量"),
    current_user: User = Depends(get_current_user),
    health_record_service: HealthRecordService = Depends(get_health_record_service)
):
    """
    列出患者的健康数据
    
    - 患者只能查看自己的健康数据
    - 医疗人员可以查看其负责的患者健康数据
    - 健康管理员可以查看所有健康数据
    - 可以按数据类型和日期范围筛选
    """
    # 访问控制
    if (current_user.user_type == "patient" and patient_id != current_user.id and 
        not await check_permission(current_user, Permission.VIEW_ANY_HEALTH_RECORD)):
        raise HTTPException(status_code=403, detail="无权访问该患者的健康数据")
    
    # 获取健康数据列表
    result = await health_record_service.list_health_data(
        patient_id=patient_id,
        data_type=data_type,
        start_date=start_date,
        end_date=end_date,
        skip=skip,
        limit=limit
    )
    
    return result

@router.post("/vital-signs", response_model=HealthDataResponse)
async def create_vital_sign(
    patient_id: str = Body(..., description="患者ID"),
    vital_type: str = Body(..., description="生命体征类型"),
    value: float = Body(..., description="生命体征值"),
    unit: Optional[str] = Body(None, description="单位"),
    measured_at: Optional[datetime] = Body(None, description="测量时间"),
    notes: Optional[str] = Body(None, description="备注"),
    device_id: Optional[str] = Body(None, description="设备ID"),
    current_user: User = Depends(get_current_user),
    health_record_service: HealthRecordService = Depends(get_health_record_service)
):
    """
    创建生命体征记录
    
    - 患者可以创建自己的生命体征记录
    - 医疗人员可以为其负责的患者创建生命体征记录
    - 需要提供患者ID、体征类型和测量值
    """
    # 访问控制
    if current_user.user_type == "patient" and patient_id != current_user.id:
        raise HTTPException(status_code=403, detail="无法为其他患者创建生命体征记录")
    
    # 创建生命体征记录
    result = await health_record_service.create_vital_sign(
        patient_id=patient_id,
        vital_type=vital_type,
        value=value,
        unit=unit,
        measured_at=measured_at,
        measured_by=current_user.id,
        device_id=device_id,
        notes=notes
    )
    
    if not result:
        raise HTTPException(status_code=500, detail="创建生命体征记录失败")
    
    return result

@router.post("/lab-results", response_model=HealthDataResponse)
async def create_lab_result(
    patient_id: str = Body(..., description="患者ID"),
    test_name: str = Body(..., description="检测名称"),
    result_value: str = Body(..., description="检测结果"),
    reference_range: Optional[str] = Body(None, description="参考范围"),
    unit: Optional[str] = Body(None, description="单位"),
    test_date: Optional[datetime] = Body(None, description="检测日期"),
    ordering_provider: Optional[str] = Body(None, description="检测医师"),
    performing_lab: Optional[str] = Body(None, description="执行实验室"),
    interpretation: Optional[str] = Body(None, description="结果解释"),
    notes: Optional[str] = Body(None, description="备注"),
    current_user: User = Depends(get_current_user),
    health_record_service: HealthRecordService = Depends(get_health_record_service),
    _: bool = Depends(is_medical_staff)
):
    """
    创建实验室检查结果记录
    
    - **只有医疗人员可以创建实验室检查结果记录**
    - 需要提供患者ID、检测名称和结果值
    """
    # 创建实验室检查结果记录
    result = await health_record_service.create_lab_result(
        patient_id=patient_id,
        test_name=test_name,
        result_value=result_value,
        reference_range=reference_range,
        unit=unit,
        test_date=test_date,
        ordering_provider=ordering_provider or current_user.id,
        performing_lab=performing_lab,
        interpretation=interpretation,
        notes=notes
    )
    
    if not result:
        raise HTTPException(status_code=500, detail="创建实验室检查结果记录失败")
    
    return result

# -------- 时间线管理 --------

@router.get("/timeline/{patient_id}", response_model=List[HealthTimelineItem])
async def get_medical_timeline(
    patient_id: str = Path(..., description="患者ID"),
    start_date: Optional[datetime] = Query(None, description="开始日期"),
    end_date: Optional[datetime] = Query(None, description="结束日期"),
    item_types: Optional[List[str]] = Query(None, description="项目类型，可多选"),
    skip: int = Query(0, description="分页偏移量"),
    limit: int = Query(100, description="每页数量"),
    current_user: User = Depends(get_current_user),
    health_record_service: HealthRecordService = Depends(get_health_record_service)
):
    """
    获取患者的医疗时间线
    
    - 患者只能查看自己的医疗时间线
    - 医疗人员可以查看其负责的患者医疗时间线
    - 健康管理员可以查看所有患者的医疗时间线
    - 可以按日期范围和项目类型筛选
    """
    # 访问控制
    if (current_user.user_type == "patient" and patient_id != current_user.id and 
        not await check_permission(current_user, Permission.VIEW_ANY_HEALTH_RECORD)):
        raise HTTPException(status_code=403, detail="无权访问该患者的医疗时间线")
    
    # 获取医疗时间线
    result = await health_record_service.get_medical_timeline(
        patient_id=patient_id,
        start_date=start_date,
        end_date=end_date,
        item_types=item_types,
        skip=skip,
        limit=limit
    )
    
    return result 
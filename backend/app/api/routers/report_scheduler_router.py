"""
报表调度器路由模块
负责报表生成调度配置与执行
"""
from fastapi import APIRouter, Depends, HTTPException, Body, Query, Path
from typing import List, Optional
from datetime import datetime, timezone
from pydantic import BaseModel, Field

from ..dependencies import get_current_user
from app.schemas.user import UserResponse
from ...services.report_scheduler_service import ReportSchedulerService, TIME_RANGES
from app.db.mongodb import get_database

router = APIRouter(prefix="/report-schedules", tags=["report-schedules"])


def get_report_scheduler_service(db=Depends(get_database)):
    """Request-scoped service; API calls do not start a scheduler loop."""
    return ReportSchedulerService(db=db)


# 数据模型
class ReportScheduleBase(BaseModel):
    name: str = Field(..., description="调度计划名称")
    description: Optional[str] = Field(None, description="调度计划描述")
    reportId: str = Field(..., description="关联的报表ID")
    reportName: Optional[str] = Field(None, description="报表名称")
    frequency: str = Field(..., description="频率: once, daily, weekly, monthly")
    weekday: Optional[int] = Field(None, description="每周几执行 (0-6, 0表示周日)")
    monthDay: Optional[int] = Field(None, description="每月几号执行 (1-31)")
    time: Optional[str] = Field(None, description="执行时间 (HH:MM)")
    nextRunTime: Optional[datetime] = Field(None, description="下次执行时间")
    recipients: List[str] = Field(..., description="接收者系统账号ID列表")
    format: str = Field(..., description="导出格式: html")
    timeRange: str = Field("month", description="统计周期: day, week, month, quarter, year")
    enabled: bool = Field(True, description="是否启用")


class ReportScheduleCreate(ReportScheduleBase):
    pass


class ReportScheduleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    reportId: Optional[str] = None
    reportName: Optional[str] = None
    frequency: Optional[str] = None
    weekday: Optional[int] = None
    monthDay: Optional[int] = None
    time: Optional[str] = None
    nextRunTime: Optional[datetime] = None
    recipients: Optional[List[str]] = None
    format: Optional[str] = None
    timeRange: Optional[str] = None
    enabled: Optional[bool] = None


class ReportScheduleResponse(ReportScheduleBase):
    id: str
    createdAt: datetime
    createdBy: str
    lastRunTime: Optional[datetime] = None
    lastRunStatus: Optional[str] = None
    executionVersion: Optional[int] = None
    retryCount: Optional[int] = None

    class Config:
        orm_mode = True


# 数据转换函数
def format_schedule(schedule: dict) -> dict:
    """格式化报表调度记录"""
    def utc(value):
        if not isinstance(value, datetime):
            return value
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    return {
        "id": schedule.get("_id"),
        "name": schedule.get("name"),
        "description": schedule.get("description"),
        "reportId": schedule.get("reportId"),
        "reportName": schedule.get("reportName"),
        "frequency": schedule.get("frequency"),
        "weekday": schedule.get("weekday"),
        "monthDay": schedule.get("monthDay"),
        "time": schedule.get("time"),
        "nextRunTime": utc(schedule.get("nextRunTime")),
        "recipients": schedule.get("recipients", []),
        "format": schedule.get("format"),
        "timeRange": schedule.get("timeRange", "month"),
        "enabled": schedule.get("enabled", True),
        "createdAt": utc(schedule.get("createdAt")),
        "createdBy": schedule.get("createdBy"),
        "lastRunTime": utc(schedule.get("lastRunTime")),
        "lastRunStatus": schedule.get("lastRunStatus"),
        "executionVersion": schedule.get("executionVersion"),
        "retryCount": schedule.get("retryCount", 0),
    }


# API端点
@router.post("", response_model=dict)
async def create_report_schedule(
    schedule: ReportScheduleCreate = Body(...),
    current_user: UserResponse = Depends(get_current_user),
    service: ReportSchedulerService = Depends(get_report_scheduler_service),
):
    """
    创建报表调度计划
    
    参数:
    - schedule: 调度计划数据
    
    返回:
    - 创建的调度计划ID
    """
    # 验证权限
    if current_user.role not in ["admin", "doctor"]:
        raise HTTPException(status_code=403, detail="没有创建报表调度计划的权限")
    
    # 准备数据
    schedule_data = schedule.dict()
    schedule_data["createdBy"] = current_user.id
    
    # 创建调度计划
    try:
        schedule_id = await service.create_schedule(schedule_data)
        return {"id": schedule_id, "message": "调度计划创建成功"}
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建调度计划失败: {str(e)}")


@router.put("/{schedule_id}", response_model=dict)
async def update_report_schedule(
    schedule_id: str = Path(..., description="调度计划ID"),
    schedule: ReportScheduleUpdate = Body(...),
    current_user: UserResponse = Depends(get_current_user),
    service: ReportSchedulerService = Depends(get_report_scheduler_service),
):
    """
    更新报表调度计划
    
    参数:
    - schedule_id: 调度计划ID
    - schedule: 调度计划更新数据
    
    返回:
    - 更新结果
    """
    # 获取现有调度计划
    existing_schedule = await service.get_schedule(schedule_id)
    if not existing_schedule:
        raise HTTPException(status_code=404, detail="调度计划不存在")
    
    # 验证权限
    if (current_user.role not in ["admin"] and
        existing_schedule.get("createdBy") != current_user.id):
        raise HTTPException(status_code=403, detail="没有更新该调度计划的权限")
    
    # 准备更新数据
    update_data = schedule.dict(exclude_unset=True)
    
    # 更新调度计划
    try:
        success = await service.update_schedule(schedule_id, update_data)
        if success:
            return {"message": "调度计划更新成功"}
        if existing_schedule.get("executionVersion") == 1:
            raise HTTPException(status_code=409, detail="计划正在执行或已并发变更，请刷新后重试")
        raise HTTPException(status_code=500, detail="更新调度计划失败")
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"更新调度计划失败: {str(e)}")


@router.delete("/{schedule_id}", response_model=dict)
async def delete_report_schedule(
    schedule_id: str = Path(..., description="调度计划ID"),
    current_user: UserResponse = Depends(get_current_user),
    service: ReportSchedulerService = Depends(get_report_scheduler_service),
):
    """
    删除报表调度计划
    
    参数:
    - schedule_id: 调度计划ID
    
    返回:
    - 删除结果
    """
    # 获取现有调度计划
    existing_schedule = await service.get_schedule(schedule_id)
    if not existing_schedule:
        raise HTTPException(status_code=404, detail="调度计划不存在")
    
    # 验证权限
    if (current_user.role not in ["admin"] and
        existing_schedule.get("createdBy") != current_user.id):
        raise HTTPException(status_code=403, detail="没有删除该调度计划的权限")
    
    # 删除调度计划
    try:
        success = await service.delete_schedule(schedule_id)
        if success:
            return {"message": "调度计划删除成功"}
        if existing_schedule.get("executionVersion") == 1:
            raise HTTPException(status_code=409, detail="计划正在执行，请稍后重试删除")
        raise HTTPException(status_code=500, detail="删除调度计划失败")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除调度计划失败: {str(e)}")


def _require_report_reader(user: UserResponse):
    if user.role not in {"admin", "doctor"}:
        raise HTTPException(status_code=403, detail="当前账号无权访问全局分析报表")


@router.get("/catalog", response_model=dict)
async def get_report_catalog(current_user: UserResponse = Depends(get_current_user)):
    """Supported report definitions backed by the analytics service."""
    _require_report_reader(current_user)
    entity_labels = {"patient": "患者", "doctor": "医生", "device": "设备",
                     "rehabilitation": "康复计划", "region": "患者地区"}
    kinds = {
        "trend": ("趋势", ("patient", "doctor", "device", "rehabilitation")),
        "distribution": ("分布", ("patient", "doctor", "device", "rehabilitation", "region")),
        "comparison": ("周期对比", ("patient", "doctor", "device", "rehabilitation")),
    }
    time_ranges = sorted(TIME_RANGES)
    items = [{"id": "overview", "label": "系统统计概览", "formats": ["html"],
              "timeRanges": []}]
    for kind, (label, entities) in kinds.items():
        items.extend({"id": f"{kind}:{entity}", "label": f"{entity_labels[entity]}{label}",
                      "formats": ["html"],
                      "timeRanges": [] if kind == "distribution" else time_ranges}
                     for entity in entities)
    return {"items": items}


@router.get("/runs", response_model=dict)
async def get_report_runs(
    limit: int = Query(20, ge=1, le=100), skip: int = Query(0, ge=0),
    current_user: UserResponse = Depends(get_current_user),
    service: ReportSchedulerService = Depends(get_report_scheduler_service),
):
    _require_report_reader(current_user)
    return await service.get_runs(current_user.id, limit, skip)


@router.get("/runs/{run_id}", response_model=dict)
async def get_report_run(
    run_id: str = Path(...), current_user: UserResponse = Depends(get_current_user),
    service: ReportSchedulerService = Depends(get_report_scheduler_service),
):
    _require_report_reader(current_user)
    row = await service.get_run(run_id, current_user.id)
    if not row:
        raise HTTPException(status_code=404, detail="报表不存在或无权访问")
    return row


@router.get("/{schedule_id}", response_model=ReportScheduleResponse)
async def get_report_schedule(
    schedule_id: str = Path(..., description="调度计划ID"),
    current_user: UserResponse = Depends(get_current_user),
    service: ReportSchedulerService = Depends(get_report_scheduler_service),
):
    """
    获取单个报表调度计划
    
    参数:
    - schedule_id: 调度计划ID
    
    返回:
    - 调度计划详情
    """
    # 获取调度计划
    schedule = await service.get_schedule(schedule_id)
    if not schedule:
        raise HTTPException(status_code=404, detail="调度计划不存在")
    
    # 验证权限
    if (current_user.role not in ["admin"] and
        schedule.get("createdBy") != current_user.id):
        raise HTTPException(status_code=403, detail="没有查看该调度计划的权限")
    
    # 格式化并返回
    return format_schedule(schedule)


@router.get("", response_model=List[ReportScheduleResponse])
async def get_report_schedules(
    report_id: Optional[str] = Query(None, description="按报表ID筛选"),
    user_id: Optional[str] = Query(None, description="按用户ID筛选"),
    current_user: UserResponse = Depends(get_current_user),
    service: ReportSchedulerService = Depends(get_report_scheduler_service),
):
    """
    获取报表调度计划列表
    
    参数:
    - report_id: 可选，按报表ID筛选
    - user_id: 可选，按用户ID筛选
    
    返回:
    - 调度计划列表
    """
    # 验证权限
    if current_user.role not in ["admin"] and user_id and user_id != current_user.id:
        raise HTTPException(status_code=403, detail="没有查看其他用户调度计划的权限")
    
    # 如果不是管理员且未指定用户ID，则只查看当前用户的调度计划
    if current_user.role not in ["admin"] and not user_id:
        user_id = current_user.id
    
    # 获取调度计划列表
    schedules = await service.get_schedules(user_id, report_id)
    
    # 格式化并返回
    return [format_schedule(schedule) for schedule in schedules]


@router.patch("/{schedule_id}/toggle", response_model=dict)
async def toggle_report_schedule(
    schedule_id: str = Path(..., description="调度计划ID"),
    enabled: bool = Query(..., description="启用状态"),
    current_user: UserResponse = Depends(get_current_user),
    service: ReportSchedulerService = Depends(get_report_scheduler_service),
):
    """
    启用或禁用报表调度计划
    
    参数:
    - schedule_id: 调度计划ID
    - enabled: 是否启用
    
    返回:
    - 操作结果
    """
    # 获取现有调度计划
    existing_schedule = await service.get_schedule(schedule_id)
    if not existing_schedule:
        raise HTTPException(status_code=404, detail="调度计划不存在")
    
    # 验证权限
    if (current_user.role not in ["admin"] and
        existing_schedule.get("createdBy") != current_user.id):
        raise HTTPException(status_code=403, detail="没有权限操作该调度计划")
    
    # 切换状态
    try:
        success = await service.toggle_schedule(schedule_id, enabled)
        if success:
            return {"message": f"调度计划已{'启用' if enabled else '禁用'}"}
        if existing_schedule.get("executionVersion") == 1:
            raise HTTPException(status_code=409, detail="计划正在执行，请稍后重试")
        raise HTTPException(status_code=500, detail="操作失败")
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"操作失败: {str(e)}")

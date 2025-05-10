"""
报表调度器路由模块
负责报表生成调度配置与执行
"""
from fastapi import APIRouter, Depends, HTTPException, Body, Query, Path
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, Field, EmailStr

from ...core.dependencies import get_current_user
from ...services.report_scheduler_service import report_scheduler_service

router = APIRouter(prefix="/report-schedules", tags=["report-schedules"])


# 数据模型
class RecipientModel(BaseModel):
    email: EmailStr


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
    recipients: List[str] = Field(..., description="接收者邮箱列表")
    format: str = Field(..., description="导出格式: pdf, excel, html")
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
    enabled: Optional[bool] = None


class ReportScheduleResponse(ReportScheduleBase):
    id: str
    createdAt: datetime
    createdBy: str
    lastRunTime: Optional[datetime] = None
    lastRunStatus: Optional[str] = None

    class Config:
        orm_mode = True


# 数据转换函数
def format_schedule(schedule: dict) -> dict:
    """格式化报表调度记录"""
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
        "nextRunTime": schedule.get("nextRunTime"),
        "recipients": schedule.get("recipients", []),
        "format": schedule.get("format"),
        "enabled": schedule.get("enabled", True),
        "createdAt": schedule.get("createdAt"),
        "createdBy": schedule.get("createdBy"),
        "lastRunTime": schedule.get("lastRunTime"),
        "lastRunStatus": schedule.get("lastRunStatus")
    }


# API端点
@router.post("", response_model=dict)
async def create_report_schedule(
    schedule: ReportScheduleCreate = Body(...),
    current_user: dict = Depends(get_current_user)
):
    """
    创建报表调度计划
    
    参数:
    - schedule: 调度计划数据
    
    返回:
    - 创建的调度计划ID
    """
    # 验证权限
    if current_user.get("role") not in ["admin", "doctor", "health_manager"]:
        raise HTTPException(status_code=403, detail="没有创建报表调度计划的权限")
    
    # 准备数据
    schedule_data = schedule.dict()
    schedule_data["createdBy"] = current_user.get("_id")
    
    # 创建调度计划
    try:
        schedule_id = await report_scheduler_service.create_schedule(schedule_data)
        return {"id": schedule_id, "message": "调度计划创建成功"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建调度计划失败: {str(e)}")


@router.put("/{schedule_id}", response_model=dict)
async def update_report_schedule(
    schedule_id: str = Path(..., description="调度计划ID"),
    schedule: ReportScheduleUpdate = Body(...),
    current_user: dict = Depends(get_current_user)
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
    existing_schedule = await report_scheduler_service.get_schedule(schedule_id)
    if not existing_schedule:
        raise HTTPException(status_code=404, detail="调度计划不存在")
    
    # 验证权限
    if (current_user.get("role") not in ["admin"] and 
        existing_schedule.get("createdBy") != current_user.get("_id")):
        raise HTTPException(status_code=403, detail="没有更新该调度计划的权限")
    
    # 准备更新数据
    update_data = schedule.dict(exclude_unset=True)
    
    # 更新调度计划
    try:
        success = await report_scheduler_service.update_schedule(schedule_id, update_data)
        if success:
            return {"message": "调度计划更新成功"}
        else:
            raise HTTPException(status_code=500, detail="更新调度计划失败")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"更新调度计划失败: {str(e)}")


@router.delete("/{schedule_id}", response_model=dict)
async def delete_report_schedule(
    schedule_id: str = Path(..., description="调度计划ID"),
    current_user: dict = Depends(get_current_user)
):
    """
    删除报表调度计划
    
    参数:
    - schedule_id: 调度计划ID
    
    返回:
    - 删除结果
    """
    # 获取现有调度计划
    existing_schedule = await report_scheduler_service.get_schedule(schedule_id)
    if not existing_schedule:
        raise HTTPException(status_code=404, detail="调度计划不存在")
    
    # 验证权限
    if (current_user.get("role") not in ["admin"] and 
        existing_schedule.get("createdBy") != current_user.get("_id")):
        raise HTTPException(status_code=403, detail="没有删除该调度计划的权限")
    
    # 删除调度计划
    try:
        success = await report_scheduler_service.delete_schedule(schedule_id)
        if success:
            return {"message": "调度计划删除成功"}
        else:
            raise HTTPException(status_code=500, detail="删除调度计划失败")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除调度计划失败: {str(e)}")


@router.get("/{schedule_id}", response_model=ReportScheduleResponse)
async def get_report_schedule(
    schedule_id: str = Path(..., description="调度计划ID"),
    current_user: dict = Depends(get_current_user)
):
    """
    获取单个报表调度计划
    
    参数:
    - schedule_id: 调度计划ID
    
    返回:
    - 调度计划详情
    """
    # 获取调度计划
    schedule = await report_scheduler_service.get_schedule(schedule_id)
    if not schedule:
        raise HTTPException(status_code=404, detail="调度计划不存在")
    
    # 验证权限
    if (current_user.get("role") not in ["admin"] and 
        schedule.get("createdBy") != current_user.get("_id")):
        raise HTTPException(status_code=403, detail="没有查看该调度计划的权限")
    
    # 格式化并返回
    return format_schedule(schedule)


@router.get("", response_model=List[ReportScheduleResponse])
async def get_report_schedules(
    report_id: Optional[str] = Query(None, description="按报表ID筛选"),
    user_id: Optional[str] = Query(None, description="按用户ID筛选"),
    current_user: dict = Depends(get_current_user)
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
    if current_user.get("role") not in ["admin"] and user_id and user_id != current_user.get("_id"):
        raise HTTPException(status_code=403, detail="没有查看其他用户调度计划的权限")
    
    # 如果不是管理员且未指定用户ID，则只查看当前用户的调度计划
    if current_user.get("role") not in ["admin"] and not user_id:
        user_id = current_user.get("_id")
    
    # 获取调度计划列表
    schedules = await report_scheduler_service.get_schedules(user_id, report_id)
    
    # 格式化并返回
    return [format_schedule(schedule) for schedule in schedules]


@router.patch("/{schedule_id}/toggle", response_model=dict)
async def toggle_report_schedule(
    schedule_id: str = Path(..., description="调度计划ID"),
    enabled: bool = Query(..., description="启用状态"),
    current_user: dict = Depends(get_current_user)
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
    existing_schedule = await report_scheduler_service.get_schedule(schedule_id)
    if not existing_schedule:
        raise HTTPException(status_code=404, detail="调度计划不存在")
    
    # 验证权限
    if (current_user.get("role") not in ["admin"] and 
        existing_schedule.get("createdBy") != current_user.get("_id")):
        raise HTTPException(status_code=403, detail="没有权限操作该调度计划")
    
    # 切换状态
    try:
        success = await report_scheduler_service.toggle_schedule(schedule_id, enabled)
        if success:
            return {"message": f"调度计划已{'启用' if enabled else '禁用'}"}
        else:
            raise HTTPException(status_code=500, detail="操作失败")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"操作失败: {str(e)}") 
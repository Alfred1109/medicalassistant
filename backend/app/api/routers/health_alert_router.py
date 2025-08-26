from datetime import datetime
from typing import List, Optional, Dict, Any

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Depends, Query, Path, status
from fastapi.responses import JSONResponse

from app.services.health_alert_service import HealthAlertService
from app.core.dependencies import get_current_user, get_health_alert_service
from app.models.health_data_threshold import HealthDataThreshold, HealthDataAlert
from app.schemas.health_data_threshold import (
    ThresholdCreate, ThresholdResponse, ThresholdUpdate,
    AlertCreate, AlertResponse, AlertUpdate, AlertStatistics
)
from app.schemas.common import ResponseModel

router = APIRouter(
    prefix="/api/health/alerts",
    tags=["健康预警"]
)

# -------- 阈值配置 API 接口 --------

@router.post("/thresholds", response_model=ThresholdResponse)
async def create_threshold(
    data: ThresholdCreate,
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: HealthAlertService = Depends(get_health_alert_service)
):
    """创建健康数据阈值配置"""
    try:
        # 根据不同数据类型处理
        if data.data_type == "vital_signs":
            if data.vital_type == "blood_pressure":
                threshold = await service.create_blood_pressure_threshold(
                    name=data.name,
                    normal_range=data.normal_range,
                    warning_range=data.warning_range,
                    critical_range=data.critical_range,
                    unit=data.unit,
                    description=data.description,
                    applies_to=data.applies_to,
                    is_default=data.is_default,
                    metadata=data.metadata,
                    created_by=current_user["id"]
                )
            else:
                threshold = await service.create_single_value_threshold(
                    name=data.name,
                    vital_type=data.vital_type,
                    normal_range=data.normal_range,
                    warning_range=data.warning_range,
                    critical_range=data.critical_range,
                    unit=data.unit,
                    description=data.description,
                    applies_to=data.applies_to,
                    is_default=data.is_default,
                    metadata=data.metadata,
                    created_by=current_user["id"]
                )
        elif data.data_type == "lab_results":
            threshold = await service.create_threshold(
                name=data.name,
                data_type=data.data_type,
                test_name=data.test_name,
                normal_range=data.normal_range,
                warning_range=data.warning_range,
                critical_range=data.critical_range,
                unit=data.unit,
                description=data.description,
                applies_to=data.applies_to,
                is_default=data.is_default,
                metadata=data.metadata,
                created_by=current_user["id"]
            )
        else:
            threshold = await service.create_threshold(
                name=data.name,
                data_type=data.data_type,
                vital_type=data.vital_type,
                test_name=data.test_name,
                normal_range=data.normal_range,
                warning_range=data.warning_range,
                critical_range=data.critical_range,
                unit=data.unit,
                description=data.description,
                applies_to=data.applies_to,
                is_default=data.is_default,
                metadata=data.metadata,
                created_by=current_user["id"]
            )
        
        return threshold
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"创建阈值配置失败: {str(e)}"
        )

@router.get("/thresholds/{threshold_id}", response_model=ThresholdResponse)
async def get_threshold(
    threshold_id: str = Path(..., description="阈值配置ID"),
    service: HealthAlertService = Depends(get_health_alert_service),
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """获取健康数据阈值配置"""
    threshold = await service.get_threshold(threshold_id)
    if not threshold:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="阈值配置不存在"
        )
    return threshold

@router.put("/thresholds/{threshold_id}", response_model=ThresholdResponse)
async def update_threshold(
    threshold_id: str,
    data: ThresholdUpdate,
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: HealthAlertService = Depends(get_health_alert_service)
):
    """更新健康数据阈值配置"""
    try:
        # 补充更新者信息
        data_dict = data.dict(exclude_unset=True)
        data_dict["updated_by"] = current_user["id"]
        
        # 更新阈值配置
        threshold = await service.update_threshold(threshold_id, data_dict)
        if not threshold:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="阈值配置不存在"
            )
        return threshold
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"更新阈值配置失败: {str(e)}"
        )

@router.delete("/thresholds/{threshold_id}", response_model=ResponseModel)
async def delete_threshold(
    threshold_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: HealthAlertService = Depends(get_health_alert_service)
):
    """删除健康数据阈值配置"""
    result = await service.delete_threshold(threshold_id)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="阈值配置不存在"
        )
    return ResponseModel(success=True, message="阈值配置已删除")

@router.get("/thresholds", response_model=List[ThresholdResponse])
async def list_thresholds(
    data_type: Optional[str] = Query(None, description="数据类型过滤"),
    vital_type: Optional[str] = Query(None, description="生命体征类型过滤"),
    test_name: Optional[str] = Query(None, description="实验室检查名称过滤"),
    is_active: Optional[bool] = Query(None, description="是否启用过滤"),
    is_default: Optional[bool] = Query(None, description="是否默认过滤"),
    skip: int = Query(0, description="分页偏移量"),
    limit: int = Query(100, description="每页数量"),
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: HealthAlertService = Depends(get_health_alert_service)
):
    """列出健康数据阈值配置"""
    try:
        thresholds = await service.list_thresholds(
            data_type=data_type,
            vital_type=vital_type,
            test_name=test_name,
            is_active=is_active,
            is_default=is_default,
            skip=skip,
            limit=limit
        )
        return thresholds
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取阈值配置列表失败: {str(e)}"
        )

# -------- 健康数据预警 API 接口 --------

@router.post("/check", response_model=Dict[str, Any])
async def check_health_data(
    health_data_id: str = Query(..., description="健康数据ID"),
    patient_id: str = Query(..., description="患者ID"),
    data_type: str = Query(..., description="数据类型"),
    vital_type: Optional[str] = Query(None, description="生命体征类型"),
    test_name: Optional[str] = Query(None, description="实验室检查名称"),
    value: Optional[float] = Query(None, description="数值"),
    unit: Optional[str] = Query(None, description="单位"),
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: HealthAlertService = Depends(get_health_alert_service)
):
    """检查健康数据是否异常"""
    try:
        result = await service.check_health_data(
            health_data_id=health_data_id,
            patient_id=patient_id,
            data_type=data_type,
            vital_type=vital_type,
            test_name=test_name,
            value=value,
            unit=unit,
            recorded_at=datetime.utcnow()
        )
        return result
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"健康数据检查失败: {str(e)}"
        )

@router.post("/alerts", response_model=AlertResponse)
async def create_alert(
    data: AlertCreate,
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: HealthAlertService = Depends(get_health_alert_service)
):
    """手动创建健康数据预警"""
    try:
        alert = await service.create_alert(data)
        return alert
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"创建预警失败: {str(e)}"
        )

@router.get("/alerts/{alert_id}", response_model=AlertResponse)
async def get_alert(
    alert_id: str = Path(..., description="预警ID"),
    service: HealthAlertService = Depends(get_health_alert_service),
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """获取健康数据预警详情"""
    alert = await service.get_alert(alert_id)
    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="预警不存在"
        )
    return alert

@router.put("/alerts/{alert_id}", response_model=AlertResponse)
async def update_alert(
    alert_id: str,
    data: AlertUpdate,
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: HealthAlertService = Depends(get_health_alert_service)
):
    """更新健康数据预警状态"""
    try:
        alert = await service.update_alert(alert_id, data)
        if not alert:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="预警不存在"
            )
        return alert
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"更新预警失败: {str(e)}"
        )

@router.put("/alerts/{alert_id}/resolve", response_model=AlertResponse)
async def resolve_alert(
    alert_id: str,
    resolution_notes: Optional[str] = Query(None, description="解决备注"),
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: HealthAlertService = Depends(get_health_alert_service)
):
    """解决健康数据预警"""
    try:
        alert = await service.resolve_alert(
            alert_id=alert_id,
            resolved_by=current_user["id"],
            resolution_notes=resolution_notes
        )
        if not alert:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="预警不存在"
            )
        return alert
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"解决预警失败: {str(e)}"
        )

@router.put("/alerts/{alert_id}/ignore", response_model=AlertResponse)
async def ignore_alert(
    alert_id: str,
    resolution_notes: Optional[str] = Query(None, description="忽略原因"),
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: HealthAlertService = Depends(get_health_alert_service)
):
    """忽略健康数据预警"""
    try:
        alert = await service.ignore_alert(
            alert_id=alert_id,
            resolved_by=current_user["id"],
            resolution_notes=resolution_notes
        )
        if not alert:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="预警不存在"
            )
        return alert
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"忽略预警失败: {str(e)}"
        )

@router.get("/alerts", response_model=List[AlertResponse])
async def list_alerts(
    patient_id: Optional[str] = Query(None, description="患者ID过滤"),
    data_type: Optional[str] = Query(None, description="数据类型过滤"),
    vital_type: Optional[str] = Query(None, description="生命体征类型过滤"),
    alert_level: Optional[str] = Query(None, description="预警级别过滤"),
    status: Optional[str] = Query(None, description="状态过滤"),
    start_date: Optional[datetime] = Query(None, description="开始日期过滤"),
    end_date: Optional[datetime] = Query(None, description="结束日期过滤"),
    skip: int = Query(0, description="分页偏移量"),
    limit: int = Query(100, description="每页数量"),
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: HealthAlertService = Depends(get_health_alert_service)
):
    """列出健康数据预警"""
    try:
        alerts = await service.list_alerts(
            patient_id=patient_id,
            data_type=data_type,
            vital_type=vital_type,
            alert_level=alert_level,
            status=status,
            start_date=start_date,
            end_date=end_date,
            skip=skip,
            limit=limit
        )
        return alerts
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取预警列表失败: {str(e)}"
        )

@router.get("/stats", response_model=AlertStatistics)
async def get_alerts_stats(
    patient_id: Optional[str] = Query(None, description="患者ID，如果提供则返回该患者的统计"),
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: HealthAlertService = Depends(get_health_alert_service)
):
    """获取健康数据预警统计"""
    try:
        if patient_id:
            stats = await service.get_patient_alerts_stats(patient_id)
        else:
            stats = await service.get_alerts_stats()
        return stats
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取预警统计失败: {str(e)}"
        ) 
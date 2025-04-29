"""
设备分析路由器
提供设备数据分析和预警相关的API接口
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Dict, List, Optional
from datetime import datetime
from pydantic import BaseModel, Field

from ...services.device_service import device_service
from ...services.device_analysis_service import device_analysis_service
from ...auth.jwt_auth import get_current_user

router = APIRouter(prefix="/device-analysis", tags=["device-analysis"])


# 数据模型
class DataAnomalyResponse(BaseModel):
    data_type: str = Field(..., description="数据类型")
    value: float = Field(..., description="异常值")
    unit: str = Field(..., description="单位")
    timestamp: datetime = Field(..., description="时间戳")
    anomaly_score: float = Field(..., description="异常分数")
    detection_method: str = Field(..., description="检测方法")
    
    class Config:
        arbitrary_types_allowed = True


class DataTrendResponse(BaseModel):
    status: str = Field(..., description="分析状态")
    message: Optional[str] = Field(None, description="状态消息")
    data_type: str = Field(..., description="数据类型")
    device_id: str = Field(..., description="设备ID")
    statistics: Optional[Dict] = Field(None, description="统计数据")
    trend: Optional[Dict] = Field(None, description="趋势数据")
    aggregated_data: Optional[List[Dict]] = Field(None, description="聚合数据")
    prediction: Optional[Dict] = Field(None, description="预测数据")
    
    class Config:
        arbitrary_types_allowed = True


class AdvancedPredictionResponse(BaseModel):
    status: str = Field(..., description="分析状态")
    message: Optional[str] = Field(None, description="状态消息")
    data_type: str = Field(..., description="数据类型")
    device_id: str = Field(..., description="设备ID")
    days_analyzed: int = Field(..., description="分析天数")
    prediction_days: int = Field(..., description="预测天数")
    method: str = Field(..., description="预测方法")
    data_points: int = Field(..., description="数据点数量")
    prediction: Dict = Field(..., description="预测结果")
    all_predictions: Optional[Dict] = Field(None, description="所有预测方法的结果")
    history: Dict = Field(..., description="历史数据")
    
    class Config:
        arbitrary_types_allowed = True


class DeviceStatusIssue(BaseModel):
    type: str = Field(..., description="问题类型")
    message: str = Field(..., description="问题描述")
    severity: str = Field(..., description="严重程度")
    
    class Config:
        arbitrary_types_allowed = True


class DeviceStatusResponse(BaseModel):
    device: Dict = Field(..., description="设备信息")
    status: Dict = Field(..., description="设备状态")
    status_score: float = Field(..., description="状态分数")
    issues: List[DeviceStatusIssue] = Field(..., description="问题列表")
    recommendations: List[str] = Field(..., description="建议列表")
    
    class Config:
        arbitrary_types_allowed = True


class DeviceAlertResponse(BaseModel):
    type: str = Field(..., description="预警类型")
    device_id: str = Field(..., description="设备ID")
    device_name: str = Field(..., description="设备名称")
    message: str = Field(..., description="预警消息")
    severity: str = Field(..., description="严重程度")
    timestamp: Optional[datetime] = Field(None, description="时间戳")
    data_type: Optional[str] = Field(None, description="数据类型")
    value: Optional[float] = Field(None, description="数据值")
    unit: Optional[str] = Field(None, description="数据单位")
    anomaly_score: Optional[float] = Field(None, description="异常分数")
    status_score: Optional[float] = Field(None, description="状态分数")
    issue_type: Optional[str] = Field(None, description="问题类型")
    recommendations: Optional[List[str]] = Field(None, description="建议列表")
    
    class Config:
        arbitrary_types_allowed = True


# API端点
@router.get("/anomalies/{device_id}", response_model=List[DataAnomalyResponse])
async def detect_data_anomalies(
    device_id: str,
    data_type: Optional[str] = None,
    days: int = Query(30, ge=1, le=365),
    method: str = Query("z_score", regex="^(z_score|range|iqr)$"),
    user=Depends(get_current_user)
):
    """
    检测设备数据异常
    
    参数:
    - device_id: 设备ID
    - data_type: 数据类型（可选）
    - days: 检测最近多少天的数据（默认30天）
    - method: 检测方法，支持z_score、range、iqr
    """
    # 检查设备访问权限
    device = await device_service.get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="设备不存在")
    
    if device.get("patient_id") != user["_id"] and user.get("role") not in ["doctor", "health_manager", "admin"]:
        raise HTTPException(status_code=403, detail="无权访问此设备数据")
    
    # 检测异常
    anomalies = await device_analysis_service.detect_data_anomalies(
        device_id=device_id,
        data_type=data_type,
        days=days,
        method=method
    )
    
    return anomalies


@router.get("/trends/{device_id}/{data_type}", response_model=DataTrendResponse)
async def analyze_data_trend(
    device_id: str,
    data_type: str,
    days: int = Query(30, ge=1, le=365),
    interval: str = Query("day", regex="^(hour|day|week|month)$"),
    user=Depends(get_current_user)
):
    """
    分析设备数据趋势
    
    参数:
    - device_id: 设备ID
    - data_type: 数据类型
    - days: 分析最近多少天的数据（默认30天）
    - interval: 数据聚合间隔，支持hour、day、week、month
    """
    # 检查设备访问权限
    device = await device_service.get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="设备不存在")
    
    if device.get("patient_id") != user["_id"] and user.get("role") not in ["doctor", "health_manager", "admin"]:
        raise HTTPException(status_code=403, detail="无权访问此设备数据")
    
    # 分析趋势
    trend = await device_analysis_service.analyze_data_trend(
        device_id=device_id,
        data_type=data_type,
        days=days,
        interval=interval
    )
    
    return trend


@router.get("/monitor/{device_id}", response_model=List[DeviceStatusResponse])
async def monitor_device_status(
    device_id: str,
    hours: int = Query(24, ge=1, le=168),
    user=Depends(get_current_user)
):
    """
    监测设备状态
    
    参数:
    - device_id: 设备ID
    - hours: 监测最近多少小时内的设备状态（默认24小时）
    """
    # 检查设备访问权限
    device = await device_service.get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="设备不存在")
    
    if device.get("patient_id") != user["_id"] and user.get("role") not in ["doctor", "health_manager", "admin"]:
        raise HTTPException(status_code=403, detail="无权访问此设备数据")
    
    # 监测状态
    statuses = await device_analysis_service.monitor_device_status(
        device_id=device_id,
        hours=hours
    )
    
    return statuses


@router.get("/patient-devices/{patient_id}", response_model=List[DeviceStatusResponse])
async def monitor_patient_devices(
    patient_id: str,
    hours: int = Query(24, ge=1, le=168),
    user=Depends(get_current_user)
):
    """
    监测患者所有设备状态
    
    参数:
    - patient_id: 患者ID
    - hours: 监测最近多少小时内的设备状态（默认24小时）
    """
    # 检查访问权限
    if user["_id"] != patient_id and user.get("role") not in ["doctor", "health_manager", "admin"]:
        raise HTTPException(status_code=403, detail="无权访问此患者数据")
    
    # 监测状态
    statuses = await device_analysis_service.monitor_device_status(
        patient_id=patient_id,
        hours=hours
    )
    
    return statuses


@router.get("/alerts/device/{device_id}", response_model=List[DeviceAlertResponse])
async def get_device_alerts(
    device_id: str,
    severity: str = Query("medium", regex="^(high|medium|low)$"),
    user=Depends(get_current_user)
):
    """
    获取设备预警信息
    
    参数:
    - device_id: 设备ID
    - severity: 预警级别阈值，只返回大于等于该级别的预警
    """
    # 检查设备访问权限
    device = await device_service.get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="设备不存在")
    
    if device.get("patient_id") != user["_id"] and user.get("role") not in ["doctor", "health_manager", "admin"]:
        raise HTTPException(status_code=403, detail="无权访问此设备数据")
    
    # 获取预警
    alerts = await device_analysis_service.generate_device_alerts(
        device_id=device_id,
        severity_threshold=severity
    )
    
    return alerts


@router.get("/alerts/patient/{patient_id}", response_model=List[DeviceAlertResponse])
async def get_patient_alerts(
    patient_id: str,
    severity: str = Query("medium", regex="^(high|medium|low)$"),
    user=Depends(get_current_user)
):
    """
    获取患者所有设备的预警信息
    
    参数:
    - patient_id: 患者ID
    - severity: 预警级别阈值，只返回大于等于该级别的预警
    """
    # 检查访问权限
    if user["_id"] != patient_id and user.get("role") not in ["doctor", "health_manager", "admin"]:
        raise HTTPException(status_code=403, detail="无权访问此患者数据")
    
    # 获取预警
    alerts = await device_analysis_service.generate_device_alerts(
        patient_id=patient_id,
        severity_threshold=severity
    )
    
    return alerts


@router.get("/predict-advanced/{device_id}", response_model=AdvancedPredictionResponse)
async def predict_device_data_advanced(
    device_id: str,
    data_type: str = Query(..., description="数据类型"),
    days: int = Query(30, description="分析最近多少天的数据"),
    prediction_days: int = Query(7, description="预测未来多少天的数据"),
    method: str = Query("linear", description="预测方法：linear, arima, prophet, ensemble"),
    confidence_interval: bool = Query(True, description="是否计算置信区间"),
    interval: str = Query("day", description="数据聚合间隔: hour, day, week, month"),
    current_user: dict = Depends(get_current_user)
):
    """
    高级数据预测分析
    支持多种预测算法和置信区间计算
    """
    # 检查设备是否存在
    device = await device_service.get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="设备不存在")
        
    # 检查预测方法是否有效
    valid_methods = ["linear", "arima", "prophet", "ensemble"]
    if method not in valid_methods:
        raise HTTPException(status_code=400, detail=f"无效的预测方法。有效值: {', '.join(valid_methods)}")
        
    # 检查时间间隔是否有效  
    valid_intervals = ["hour", "day", "week", "month"]
    if interval not in valid_intervals:
        raise HTTPException(status_code=400, detail=f"无效的时间间隔。有效值: {', '.join(valid_intervals)}")
        
    # 进行预测分析
    result = await device_analysis_service.predict_data_advanced(
        device_id=device_id,
        data_type=data_type,
        days=days,
        prediction_days=prediction_days,
        method=method,
        confidence_interval=confidence_interval,
        interval=interval
    )
    
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("message", "预测分析失败"))
        
    return result 
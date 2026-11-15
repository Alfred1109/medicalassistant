from datetime import datetime
from typing import List, Optional, Dict, Any

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Depends, Query, Path, status
from fastapi.responses import JSONResponse
from starlette.status import HTTP_500_INTERNAL_SERVER_ERROR
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.db.mongodb import get_database
from app.services.health_alert_service import HealthAlertService
from app.schemas.user import UserResponse
from app.api.dependencies import get_current_user, get_health_alert_service
from app.core.patient_access import (
    PatientAccessError,
    assigned_scope_ids,
    ensure_patient_access,
    ensure_self_patient_access,
)
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

# T76 授权收口：本路由此前仅有 get_current_user（任何登录用户可读任何患者
# 预警）。现按调用者角色分流——患者仅可读本人预警（自取语义，与
# app/clinical/router.py 患者预警端点同源：ensure_self_patient_access）；
# 医护（doctor/health_manager）按内核 ensure_patient_access / assigned_scope_ids；
# admin 豁免。阈值 CRUD 与预警写路径仅限医护/admin。
MANAGEMENT_ROLES = ("doctor", "health_manager", "admin")
ASSIGNED_ROLES = ("doctor", "health_manager")


def _access_denied(exc: PatientAccessError) -> HTTPException:
    """PatientAccessError → HTTPException（与 clinical/workspace 同款 detail 形态）。"""
    return HTTPException(
        status_code=exc.status_code,
        detail={"code": exc.error_code, "message": exc.message},
    )


def _require_management_role(current_user: UserResponse) -> None:
    """阈值 CRUD 与预警写路径的角色门槛：仅医护/admin。"""
    if current_user.role not in MANAGEMENT_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "ROLE_NOT_ALLOWED", "message": "该端点仅限医护与管理员使用"},
        )


def _raise_patient_forbidden() -> None:
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={"code": "ROLE_NOT_ALLOWED", "message": "患者无权执行该预警操作"},
    )


async def _resolve_self_patient(db: AsyncIOMotorDatabase, current_user: UserResponse,
                                patient_id: Optional[str] = None) -> str:
    """患者角色自取解析：显式 patient_id 必须为本人（legacy 同文档 /
    canonical 链接核验，与临床患者预警端点同源）。"""
    try:
        return await ensure_self_patient_access(db, current_user, patient_id)
    except PatientAccessError as exc:
        raise _access_denied(exc) from None


async def _authorize_patient_read(db: AsyncIOMotorDatabase, current_user: UserResponse,
                                  patient_id: str) -> None:
    """对象级读取授权：患者自取（显式他人 ID → 403）、医护按归属、admin 豁免。"""
    if current_user.role == "patient":
        identifier = await _resolve_self_patient(db, current_user)
        if str(patient_id) != identifier:
            raise _access_denied(PatientAccessError("无权访问该患者的数据"))
        return
    if current_user.role in ASSIGNED_ROLES:
        try:
            await ensure_patient_access(db, patient_id, str(current_user.id), current_user.role)
        except PatientAccessError as exc:
            raise _access_denied(exc) from None
    return


async def _authorize_alert_access(db: AsyncIOMotorDatabase, current_user: UserResponse,
                                  patient_id: str) -> None:
    """按预警归属做对象级读取授权（患者不得读他人预警）。"""
    await _authorize_patient_read(db, current_user, patient_id)


async def _authorize_alert_management(db: AsyncIOMotorDatabase, current_user: UserResponse,
                                      patient_id: str) -> None:
    """预警状态写路径授权：患者一律拒绝（临床处置动作）；医护按归属；admin 豁免。"""
    if current_user.role == "patient":
        _raise_patient_forbidden()
    await _authorize_patient_read(db, current_user, patient_id)

# -------- 阈值配置 API 接口 --------

@router.post("/thresholds", response_model=ThresholdResponse)
async def create_threshold(
    data: ThresholdCreate,
    current_user: UserResponse = Depends(get_current_user),
    service: HealthAlertService = Depends(get_health_alert_service)
):
    """创建健康数据阈值配置"""
    _require_management_role(current_user)
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
                    created_by=current_user.id
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
                    created_by=current_user.id
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
                created_by=current_user.id
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
                created_by=current_user.id
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
    current_user: UserResponse = Depends(get_current_user)
):
    """获取健康数据阈值配置"""
    _require_management_role(current_user)
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
    current_user: UserResponse = Depends(get_current_user),
    service: HealthAlertService = Depends(get_health_alert_service)
):
    """更新健康数据阈值配置"""
    _require_management_role(current_user)
    try:
        # 补充更新者信息
        data_dict = data.dict(exclude_unset=True)
        data_dict["updated_by"] = current_user.id
        
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
    current_user: UserResponse = Depends(get_current_user),
    service: HealthAlertService = Depends(get_health_alert_service)
):
    """删除健康数据阈值配置"""
    _require_management_role(current_user)
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
    current_user: UserResponse = Depends(get_current_user),
    service: HealthAlertService = Depends(get_health_alert_service)
):
    """列出健康数据阈值配置"""
    _require_management_role(current_user)
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
    current_user: UserResponse = Depends(get_current_user),
    service: HealthAlertService = Depends(get_health_alert_service),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """检查健康数据是否异常"""
    _require_management_role(current_user)
    await _authorize_patient_read(db, current_user, patient_id)
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
    current_user: UserResponse = Depends(get_current_user),
    service: HealthAlertService = Depends(get_health_alert_service),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """手动创建健康数据预警"""
    _require_management_role(current_user)
    await _authorize_patient_read(db, current_user, data.patient_id)
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
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """获取健康数据预警详情"""
    alert = await service.get_alert(alert_id)
    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="预警不存在"
        )
    await _authorize_alert_access(db, current_user, alert.patient_id)
    return alert

@router.put("/alerts/{alert_id}", response_model=AlertResponse)
async def update_alert(
    alert_id: str,
    data: AlertUpdate,
    current_user: UserResponse = Depends(get_current_user),
    service: HealthAlertService = Depends(get_health_alert_service),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """更新健康数据预警状态"""
    existing = await service.get_alert(alert_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="预警不存在"
        )
    await _authorize_alert_management(db, current_user, existing.patient_id)
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
    current_user: UserResponse = Depends(get_current_user),
    service: HealthAlertService = Depends(get_health_alert_service),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """解决健康数据预警"""
    existing = await service.get_alert(alert_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="预警不存在"
        )
    await _authorize_alert_management(db, current_user, existing.patient_id)
    try:
        alert = await service.resolve_alert(
            alert_id=alert_id,
            resolved_by=current_user.id,
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
    current_user: UserResponse = Depends(get_current_user),
    service: HealthAlertService = Depends(get_health_alert_service),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """忽略健康数据预警"""
    existing = await service.get_alert(alert_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="预警不存在"
        )
    await _authorize_alert_management(db, current_user, existing.patient_id)
    try:
        alert = await service.ignore_alert(
            alert_id=alert_id,
            resolved_by=current_user.id,
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
    current_user: UserResponse = Depends(get_current_user),
    service: HealthAlertService = Depends(get_health_alert_service),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """列出健康数据预警

    患者仅可读本人预警（patient_id 显式给出时必须为本人 ID，缺失时自取解析）；
    医护传入 patient_id 时按归属校验，未传入时收敛到其名下患者范围
    （assigned_scope_ids）；admin 豁免。
    """
    # 注意：本端点查询参数 status 与 fastapi.status 模块重名（历史签名，
    # 对外查询键不可变更）；授权段放在 try 外，异常转换不经过该名字。
    patient_ids: Optional[List[str]] = None
    if current_user.role == "patient":
        patient_id = await _resolve_self_patient(db, current_user, patient_id)
    elif current_user.role in ASSIGNED_ROLES:
        if patient_id:
            await _authorize_patient_read(db, current_user, patient_id)
        else:
            patient_ids = await assigned_scope_ids(db, str(current_user.id), current_user.role)
    try:
        alerts = await service.list_alerts(
            patient_id=patient_id,
            patient_ids=patient_ids,
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
    except PatientAccessError as exc:
        raise _access_denied(exc) from None
    except Exception as e:
        raise HTTPException(
            status_code=HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取预警列表失败: {str(e)}"
        )

@router.get("/stats", response_model=AlertStatistics)
async def get_alerts_stats(
    patient_id: Optional[str] = Query(None, description="患者ID，如果提供则返回该患者的统计"),
    current_user: UserResponse = Depends(get_current_user),
    service: HealthAlertService = Depends(get_health_alert_service),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """获取健康数据预警统计

    患者仅可取本人统计（patient_id 强制走自取解析，显式他人 ID 拒绝）；
    医护传入 patient_id 时按归属校验；未传入时返回全局聚合计数（不含
    患者个体明细）；admin 豁免。
    """
    if current_user.role == "patient":
        identifier = await _resolve_self_patient(db, current_user, patient_id)
        try:
            return await service.get_patient_alerts_stats(identifier)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"获取预警统计失败: {str(e)}"
            )
    if patient_id:
        await _authorize_patient_read(db, current_user, patient_id)
        try:
            return await service.get_patient_alerts_stats(patient_id)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"获取预警统计失败: {str(e)}"
            )
    try:
        return await service.get_alerts_stats()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取预警统计失败: {str(e)}"
        ) 
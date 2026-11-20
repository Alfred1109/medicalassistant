"""
设备路由器
处理设备管理相关API请求
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from typing import Any, Dict, List, Literal, Optional
from datetime import datetime
from bson import ObjectId
from pydantic import BaseModel, ConfigDict, Field, field_validator

from motor.motor_asyncio import AsyncIOMotorDatabase

from ...db.mongodb import get_database
from ..dependencies import get_device_service
from ...core.device_access import device_patient_scope, ensure_device_access, resolve_device_patient
from ...services.device_service import (
    device_service,
    DEVICE_READ_ROLES,
    DEVICE_MUTATE_ROLES,
)
from ...core.auth import get_current_active_user
from ...services.device_ingestion_service import (
    device_ingestion_service,
    DeviceIngestionError,
)


def get_device_ingestion_service() -> Any:
    """网关服务依赖（测试可 dependency_overrides 替换）。"""
    return device_ingestion_service


async def _get_device_or_404(device_id: str, device_api) -> Dict:
    """获取设备或抛 404：畸形 ID 与不存在的设备语义一致（404）。"""
    if not ObjectId.is_valid(device_id):
        raise HTTPException(status_code=404, detail="设备不存在")
    device = await device_api.get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="设备不存在")
    return device


async def _ensure_device_access(
    device: Dict,
    current_user: Any,
    db: AsyncIOMotorDatabase,
    roles: List[str],
    detail: str = "无权访问此设备",
) -> None:
    """AUTH01 对象级授权第二层（按 device_id 寻址，复用 7c5d690 两层模式）。

    调用前设备文档已加载（设备不存在 → 404 先于本判断）。语义分层：
    - admin 豁免（全局设备管理职责）；
    - 患者本人访问自己名下设备走属主判断（属主语义，不走医护归属，
      不把患者当"无归属医护"错拒）；
    - 其他用户须具备授权角色，且与设备所属患者存在归属关系
      （共享 ensure_patient_access：患者不存在 → 404 PATIENT_NOT_FOUND，
      非归属医护 → 403 PATIENT_NOT_ASSIGNED）；
    - 设备文档缺失 patient_id 的畸形数据按 404 处置（不暴露存在性）。
    """
    await ensure_device_access(db, device, current_user, roles)


def _to_device_response(device: Any) -> Any:
    """service 文档以 _id 存储主键、patient_id 可能以 ObjectId 存储，
    而 DeviceResponse/DeviceDataResponse 以 id/patient_id: str 声明；
    返回前规范字段名与形态，否则响应校验必然失败。"""
    if isinstance(device, dict):
        normalized = dict(device)
        if "_id" in normalized and "id" not in normalized:
            normalized["id"] = str(normalized["_id"])
        if normalized.get("patient_id") is not None:
            normalized["patient_id"] = str(normalized["patient_id"])
        return normalized
    return device

router = APIRouter(prefix="/devices", tags=["devices"])


# 设备请求/响应模型
class DeviceBase(BaseModel):
    device_type: str = Field(..., description="设备类型，如'血压计'、'血糖仪'等")
    name: str = Field(..., description="设备名称")
    manufacturer: Optional[str] = Field(None, description="制造商")
    model: Optional[str] = Field(None, description="型号")
    connection_type: Optional[str] = Field(None, description="连接类型，如'bluetooth'、'wifi'等")
    firmware_version: Optional[str] = Field(None, description="固件版本")
    settings: Optional[Dict] = Field(None, description="设备设置")


class DeviceCreate(DeviceBase):
    patient_id: Optional[str] = Field(None, description="设备所属患者；医护和管理员必须明确选择")


class DeviceResponse(DeviceBase):
    id: str = Field(..., description="设备ID")
    patient_id: Optional[str] = Field(None, description="患者ID")
    status: str = Field(..., description="设备状态")
    last_connected: Optional[datetime] = Field(None, description="最后连接时间")
    battery_level: Optional[float] = Field(None, description="电池电量")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")

    class Config:
        orm_mode = True


class DeviceStatusResponse(BaseModel):
    status: str = Field(..., description="设备状态（由最后连接时间推导：online/idle/offline/error）")
    battery_level: Optional[int] = Field(None, description="电池电量；设备未上报时为 null，不返回模拟值")
    signal_strength: Optional[int] = Field(None, description="信号强度；设备未上报时为 null，不返回模拟值")
    last_sync_time: Optional[datetime] = Field(None, description="最后同步时间")
    message: Optional[str] = Field(None, description="状态消息")


class DeviceDataBase(BaseModel):
    timestamp: datetime = Field(..., description="数据时间戳")
    data_type: str = Field(..., description="数据类型")
    value: Any = Field(..., description="数据值")
    unit: str = Field(..., description="单位")
    metadata: Optional[Dict] = Field(None, description="元数据")


class DeviceDataResponse(DeviceDataBase):
    id: str = Field(..., description="数据ID")
    device_id: str = Field(..., description="设备ID")
    created_at: datetime = Field(..., description="创建时间")

    class Config:
        orm_mode = True


class DeviceObservationResponse(DeviceDataResponse):
    quality_flags: Optional[List[str]] = Field(None, description="接入时记录的质量标记")


class DeviceSyncResponse(BaseModel):
    success: bool = Field(..., description="同步是否成功")
    message: str = Field(..., description="消息")
    new_data: Optional[List[DeviceDataBase]] = Field(None, description="新同步的数据")


class VeePooHeartRateReading(BaseModel):
    """Normalized F300 live heart-rate callback from the Veepoo WeChat SDK."""
    data_type: Literal["heart_rate"]
    value: float = Field(..., gt=0, allow_inf_nan=False)
    unit: Literal["bpm"]
    measured_at: datetime = Field(..., description="手机收到回调的时间，必须带时区")
    sdk_type: Literal[51] = Field(..., description="Veepoo 实时心率回调类型")
    record_key: Optional[str] = Field(None, max_length=160)
    raw_payload: Optional[Dict[str, Any]] = None

    @field_validator("measured_at")
    @classmethod
    def require_timezone(cls, value):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("measured_at 必须包含时区")
        return value


class VeePooReadingsRequest(BaseModel):
    hardware_id: str = Field(..., min_length=1, max_length=128,
                             description="用户确认的 SDK 设备标识（VPDeviceMAC）")
    readings: List[VeePooHeartRateReading] = Field(..., min_length=1, max_length=500)


@router.post("/{device_id}/veepoo/readings")
async def ingest_veepoo_readings(
    device_id: str,
    payload: VeePooReadingsRequest,
    current_user: Any = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
    device_api: Any = Depends(get_device_service),
    ingestion: Any = Depends(get_device_ingestion_service),
):
    """Store F300 live heart-rate callbacks under the authenticated binding.

    Patient identity and source are server-owned. The first user-confirmed SDK
    hardware identifier is pinned to the bound F300 record; later uploads must
    match. This is an account-level association, not cryptographic BLE proof.
    """
    device = await _get_device_or_404(device_id, device_api)
    await ensure_device_access(
        db, device, current_user, DEVICE_READ_ROLES, write=True)
    try:
        pinned = await ingestion.pin_veepoo_hardware_id(
            device, payload.hardware_id, actor=current_user)
        readings = [reading.model_dump() for reading in payload.readings]
        return await ingestion.ingest_veepoo_readings(
            pinned, readings, actor=current_user)
    except DeviceIngestionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc))


class DeviceConfigUpdate(BaseModel):
    sync_frequency: Optional[str] = Field(None, description="同步频率")
    notifications_enabled: Optional[bool] = Field(None, description="是否启用通知")
    custom_name: Optional[str] = Field(None, description="自定义名称")
    alarm_settings: Optional[Dict] = Field(None, description="警报设置")


class DeviceConfigResponse(BaseModel):
    success: bool = Field(..., description="配置是否成功")
    message: str = Field(..., description="消息")


# API路由定义
@router.get("/", response_model=List[DeviceResponse])
async def get_user_devices(
    patient_id: Optional[str] = None,
    current_user: Any = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
    device_api: Any = Depends(get_device_service),
):
    """获取当前用户绑定的设备列表"""
    # 列表与对象读取共用患者范围，医护只见已分配患者。
    scope = await device_patient_scope(db, current_user, patient_id)
    if scope is None:
        devices = await device_api.list_registered_devices()
    elif current_user.role == "patient" or patient_id is not None:
        devices = await device_api.get_user_devices(scope[0])
    else:
        devices = await device_api.get_patients_devices(scope)
    return [_to_device_response(device) for device in devices]


@router.get("/{device_id}", response_model=DeviceResponse)
async def get_device(
    device_id: str,
    current_user: Any = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
    device_api: Any = Depends(get_device_service),
):
    """获取设备详情"""
    # AUTH01：存在性校验（404 先行）+ 对象级归属校验
    device = await _get_device_or_404(device_id, device_api)
    await _ensure_device_access(device, current_user, db, list(DEVICE_READ_ROLES))
    return _to_device_response(device)


@router.post("/bind", response_model=DeviceResponse)
async def bind_device(
    device: DeviceCreate,
    current_user: Any = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
    device_api: Any = Depends(get_device_service),
):
    """为已授权患者登记设备，患者本人只能选择自己。"""
    patient_id = await resolve_device_patient(db, current_user, device.patient_id)
    result = await device_api.bind_device(patient_id, device.model_dump(exclude={"patient_id"}), actor=current_user)
    if isinstance(result, dict) and result.get("error"):
        raise HTTPException(400, detail=result["error"])
    return _to_device_response(result)


@router.delete("/{device_id}/unbind")
async def unbind_device(
    device_id: str,
    current_user: Any = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
    device_api: Any = Depends(get_device_service),
):
    """解绑用户设备"""
    device = await _get_device_or_404(device_id, device_api)

    # 无需医患归属校验：解绑属变更操作且仅限属主本人或管理员，
    # 授权规则本身即对象级（非属主医护一律排除，无归属关系可回旋）。
    await ensure_device_access(db, device, current_user, DEVICE_READ_ROLES, write=True)
    result = await device_api.unbind_device(str(device["patient_id"]), device_id, actor=current_user)
    if result:
        return {"message": "设备已解绑"}
    else:
        raise HTTPException(status_code=400, detail="解绑设备失败")


@router.get("/{device_id}/data", response_model=List[DeviceObservationResponse])
async def get_device_data(
    device_id: str,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    data_type: Optional[str] = None,
    limit: int = Query(100, ge=1, le=1000),
    automated_only: bool = False,
    current_user: Any = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
    device_api: Any = Depends(get_device_service),
):
    """获取设备观测。自动采集模式包括设备网关和 F300 小程序读数。"""
    # AUTH01：存在性校验（404 先行）+ 对象级归属校验
    device = await _get_device_or_404(device_id, device_api)
    await ensure_device_access(db, device, current_user, DEVICE_READ_ROLES)

    data = await device_api.get_device_data(
        device_id,
        start_date=start_date,
        end_date=end_date,
        data_type=data_type,
        limit=limit,
        automated_only=automated_only,
    )
    return [_to_device_response(item) for item in data]


@router.post("/{device_id}/sync", response_model=dict)
async def sync_device_data(
    device_id: str,
    current_user: Any = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
    device_api: Any = Depends(get_device_service),
):
    """
    同步设备数据

    去模拟化（REM02）：设备真实数据源（设备 SDK / 厂商云 API）尚未接入
    （评估见 docs/device-sdk-assessment-2026-11-07.md）。原实现会随机生成
    心率/睡眠/血糖等数据冒充采集结果，现已整体移除；本端点如实返回
    503"设备数据源未接入"，不写入任何数据、不更新 last_connected。
    """
    # AUTH01：存在性校验（404 先行）+ 对象级归属校验（沿用只读角色语义）
    device = await _get_device_or_404(device_id, device_api)
    await ensure_device_access(db, device, current_user, DEVICE_READ_ROLES, write=True)

    result = await device_api.sync_device_data(device_id)
    # 数据源未接入：如实 503，绝不返回随机数据伪装同步成功
    if not result.get("success"):
        raise HTTPException(status_code=503, detail=result.get("message", "设备数据源未接入"))
    return result


class ManualReading(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    data_type: str = Field(min_length=1, max_length=40)
    value: str = Field(min_length=1, max_length=80)
    unit: str = Field(default="", max_length=20)
    measured_at: datetime


@router.post("/{device_id}/readings", response_model=DeviceDataResponse, status_code=201)
async def record_reading(
    device_id: str,
    payload: ManualReading,
    current_user: Any = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
    device_api: Any = Depends(get_device_service),
):
    """Save a value a person entered. The record is marked 手工登记 and does not update battery or last connection."""
    device = await _get_device_or_404(device_id, device_api)
    await ensure_device_access(db, device, current_user, DEVICE_READ_ROLES, write=True)
    return await device_api.record_manual_reading(
        device_id, payload.data_type, payload.value, payload.unit, payload.measured_at, actor=current_user)


@router.get("/{device_id}/status", response_model=DeviceStatusResponse)
async def get_device_status(
    device_id: str,
    current_user: Any = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
    device_api: Any = Depends(get_device_service),
):
    """获取设备状态

    去模拟化：状态由设备文档 last_connected 真实推导；电量/信号强度
    无真实上报路径，响应中如实为 null（不再随机生成）。
    """
    # AUTH01：存在性校验（404 先行）+ 对象级归属校验
    device = await _get_device_or_404(device_id, device_api)
    await _ensure_device_access(device, current_user, db, list(DEVICE_READ_ROLES))

    status = await device_api.get_device_status(device_id)
    return status


@router.put("/{device_id}/config", response_model=DeviceConfigResponse)
async def configure_device(
    device_id: str,
    config: DeviceConfigUpdate,
    current_user: Any = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
    device_api: Any = Depends(get_device_service),
):
    """配置设备"""
    # AUTH01 对象级授权（变更守卫）：配置属变更操作，健康管理师只读不可
    # 变更（缺陷 B 统一）；属主患者可配置自己名下设备；非属主医生须与
    # 设备所属患者存在归属关系（ensure_patient_access）。
    device = await _get_device_or_404(device_id, device_api)
    await ensure_device_access(db, device, current_user, DEVICE_MUTATE_ROLES, write=True)

    result = await device_api.configure_device(device_id, config.dict(exclude_unset=True), actor=current_user)
    return result


# ══ T74 设备数据接入网关 ══════════════════════════════════════════════════
# 设备侧（采集端）推送通道：以 device_sn + device_key 设备凭证鉴权（非用户
# JWT）；协议解析在 device_protocol 适配器包内（JMD-540 为骨架+假设清单），
# 质量校验与幂等在 device_ingestion_service 统一管道，分析/预警复用
# device_analysis_service。
#
# 协议假设核实清单见 GET /devices/{device_id}/gateway/protocol-assumptions，
# 全部假设集中在 backend/app/services/device_protocol/jmd540.py。


class GatewayIngestRequest(BaseModel):
    """设备上报载荷（帧结构由适配器假设定义，此处不做字段白名单）。"""
    device_sn: str = Field(min_length=1, max_length=80, description="设备序列号")
    readings: List[Dict[str, Any]] = Field(..., description="原始上报帧列表（1..500）")
    device_key: Optional[str] = Field(None, description="设备凭证（亦可经 X-Device-Key 头传递）")


class GatewayHeartbeatRequest(BaseModel):
    device_sn: str = Field(min_length=1, max_length=80, description="设备序列号")
    device_key: Optional[str] = Field(None, description="设备凭证（亦可经 X-Device-Key 头传递）")


async def _authenticate_gateway(
    device_sn: str, device_key: Optional[str],
    ingestion: Any,
) -> Dict:
    """网关设备凭证鉴权 → 设备文档；失败转对应 4xx。"""
    try:
        return await ingestion.authenticate_device(device_sn, device_key)
    except DeviceIngestionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc))


@router.post("/gateway/ingest")
async def gateway_ingest(
    payload: GatewayIngestRequest,
    request: Request,
    ingestion: Any = Depends(get_device_ingestion_service),
):
    """设备数据上报端点（单条与批上报统一：readings 列表 1..500 帧）。

    链路：凭证鉴权 → 适配器解析 → 质量管道（必填/范围/时序/幂等去重）
    → device_data 入库（来源 automated、原始载荷留存）→ 触发既有分析预警链。
    纯失败帧不入库，逐条 error 在 rejected 中返回。
    """
    device_key = payload.device_key or request.headers.get("X-Device-Key")
    device = await _authenticate_gateway(payload.device_sn, device_key, ingestion)
    try:
        return await ingestion.ingest(device, payload.readings)
    except DeviceIngestionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc))


@router.post("/gateway/heartbeat")
async def gateway_heartbeat(
    payload: GatewayHeartbeatRequest,
    request: Request,
    ingestion: Any = Depends(get_device_ingestion_service),
):
    """设备心跳：刷新 last_connected（真实到达才更新），返回当前采集会话。"""
    device_key = payload.device_key or request.headers.get("X-Device-Key")
    device = await _authenticate_gateway(payload.device_sn, device_key, ingestion)
    return await ingestion.heartbeat(device)


# ── 网关管理端点（用户鉴权）──────────────────────────────────────────────


class GatewayCredentialResponse(BaseModel):
    success: bool
    message: str
    device_key: str = Field(..., description="设备凭证（仅本次响应透出，请即保存）")


class CollectionSessionStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    plan_id: Optional[str] = Field(None, description="关联患者当前已发布康复方案ID（可选）")
    version_id: Optional[str] = Field(None, description="关联方案已发布版本ID")
    prescription_item_id: Optional[str] = Field(None, description="关联稳定处方项ID")
    notes: Optional[str] = Field(None, max_length=500)


class CollectionSessionResponse(BaseModel):
    id: str = Field(..., alias="_id")
    device_id: str
    device_sn: Optional[str] = None
    patient_id: str
    status: str
    plan_id: Optional[str] = None
    version_id: Optional[str] = None
    prescription_item_id: Optional[str] = None
    linkage_status: str
    linkage_error: Optional[str] = None
    started_at: datetime
    ended_at: Optional[datetime] = None
    summary: Optional[Dict] = None
    notes: Optional[str] = None

    class Config:
        populate_by_name = True


@router.put("/{device_id}/gateway-credential", response_model=GatewayCredentialResponse)
async def set_gateway_credential(
    device_id: str,
    current_user: Any = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
    device_api: Any = Depends(get_device_service),
):
    """登记/轮换设备网关凭证（变更围栏：doctor/admin 或属主患者）。

    厂商正式鉴权方案（token/证书）到位前，device_key 为过渡共享凭证；
    假设清单见 device_protocol/jmd540.py（凭证机制假设条目）。
    """
    device = await _get_device_or_404(device_id, device_api)
    await ensure_device_access(db, device, current_user, DEVICE_MUTATE_ROLES, write=True)
    result = await device_api.set_gateway_credential(device_id, actor=current_user)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("message", "凭证登记失败"))
    return result


@router.get("/{device_id}/gateway/protocol-assumptions")
async def get_protocol_assumptions(
    device_id: str,
    current_user: Any = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
    device_api: Any = Depends(get_device_service),
    ingestion: Any = Depends(get_device_ingestion_service),
):
    """协议假设核实清单：该设备型号适配器全部待核实协议字段假设。"""
    device = await _get_device_or_404(device_id, device_api)
    await ensure_device_access(db, device, current_user, DEVICE_READ_ROLES)
    adapter = ingestion._select_adapter(device)
    if adapter is None:
        return {
            "device_id": device_id,
            "model": device.get("model"),
            "adapter_id": None,
            "message": f"设备型号 {device.get('model')!r} 未登记协议适配器",
            "assumptions": [],
        }
    return {
        "device_id": device_id,
        "model": device.get("model"),
        "adapter_id": adapter.adapter_id,
        "assumptions": adapter.describe_assumptions(),
    }


@router.get("/{device_id}/quality-report")
async def get_device_quality_report(
    device_id: str,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    current_user: Any = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
    device_api: Any = Depends(get_device_service),
    ingestion: Any = Depends(get_device_ingestion_service),
):
    """自动采集数据质量报告：按设备/时段的合格率与质量标记统计。"""
    device = await _get_device_or_404(device_id, device_api)
    await ensure_device_access(db, device, current_user, DEVICE_READ_ROLES)
    return await ingestion.quality_report(device_id, start=start, end=end)


@router.get("/{device_id}/publication-options", response_model=List[dict])
async def list_device_publication_options(
    device_id: str,
    current_user: Any = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
    device_api: Any = Depends(get_device_service),
):
    """List current published exercise items for this device's assigned patient."""
    device = await _get_device_or_404(device_id, device_api)
    await ensure_device_access(db, device, current_user, DEVICE_READ_ROLES)
    patient_id = str(device.get("patient_id") or "")
    if not patient_id:
        return []

    plans = db.rehab_plans.find({
        "patient_id": patient_id,
        "published_version_id": {"$type": "string"},
    })
    result = []
    async for plan in plans:
        if plan.get("status") in {"cancelled", "canceled", "archived"}:
            continue
        version_id = plan.get("published_version_id")
        if not ObjectId.is_valid(version_id):
            continue
        version = await db.rehab_plan_versions.find_one({
            "_id": ObjectId(version_id), "plan_id": str(plan["_id"]),
            "patient_id": patient_id, "workflow": "patient_publication",
            "status": "published",
        })
        if not version:
            continue
        items_snapshot = version.get("items_snapshot")
        # SavePublicationDraft caps the complete publication at 200 items.
        # More indicates corrupt/incompatible persisted state; never silently
        # omit a valid linked item from the selection list.
        if not isinstance(items_snapshot, list) or len(items_snapshot) > 200:
            raise HTTPException(status_code=503,
                                detail="已发布处方快照异常或超出系统上限，无法安全关联设备")
        exercise_items = [{"item_id": row["item_id"], "name": row.get("name") or "运动处方"}
                          for row in items_snapshot if isinstance(row, dict)
                          and row.get("intervention_type") == "exercise"
                          and isinstance(row.get("item_id"), str)]
        if exercise_items:
            result.append({
                "plan_id": str(plan["_id"]),
                "plan_name": (version.get("snapshot") or {}).get("name") or plan.get("name") or "康复方案",
                "version_id": version_id,
                "items": exercise_items,
            })
    return result


# ── 采集会话 ─────────────────────────────────────────────────────────────


@router.post("/{device_id}/sessions", response_model=CollectionSessionResponse, status_code=201)
async def start_collection_session(
    device_id: str,
    payload: CollectionSessionStartRequest,
    current_user: Any = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
    device_api: Any = Depends(get_device_service),
    ingestion: Any = Depends(get_device_ingestion_service),
):
    """开始独立设备观测，可显式关联患者当前已发布方案处方项。"""
    device = await _get_device_or_404(device_id, device_api)
    await ensure_device_access(db, device, current_user, DEVICE_READ_ROLES, write=True)
    patient_id = str(device.get("patient_id")) if device.get("patient_id") else None
    if not patient_id:
        raise HTTPException(status_code=409, detail="设备未绑定患者，无法开始采集会话")
    try:
        session = await ingestion.start_collection_session(
            device, patient_id, plan_id=payload.plan_id,
            version_id=payload.version_id,
            prescription_item_id=payload.prescription_item_id,
            notes=payload.notes)
    except DeviceIngestionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc))
    return session


@router.post("/{device_id}/sessions/{session_id}/end", response_model=CollectionSessionResponse)
async def end_collection_session(
    device_id: str,
    session_id: str,
    cancel: bool = Query(False, description="true = 取消会话（而非正常结束）"),
    current_user: Any = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
    device_api: Any = Depends(get_device_service),
    ingestion: Any = Depends(get_device_ingestion_service),
):
    """结束/取消设备观测会话并写入读数与质量摘要。"""
    device = await _get_device_or_404(device_id, device_api)
    await ensure_device_access(db, device, current_user, DEVICE_READ_ROLES, write=True)
    session = await ingestion.end_collection_session(
        device, session_id, cancel=cancel)
    if not session:
        raise HTTPException(status_code=404, detail="采集会话不存在或已结束")
    return session


@router.get("/{device_id}/sessions", response_model=List[CollectionSessionResponse])
async def list_collection_sessions(
    device_id: str,
    limit: int = Query(50, ge=1, le=200),
    current_user: Any = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
    device_api: Any = Depends(get_device_service),
    ingestion: Any = Depends(get_device_ingestion_service),
):
    """采集会话列表（最近优先）。"""
    device = await _get_device_or_404(device_id, device_api)
    await ensure_device_access(db, device, current_user, DEVICE_READ_ROLES)
    return await ingestion.list_collection_sessions(device_id, limit=limit)

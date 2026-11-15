"""
设备服务模块
负责设备管理、数据处理和适配器系统
"""
import logging
import math
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Union
from bson import ObjectId

from ..models.device import Device, DeviceData
from ..models.device_data_standard import (
    DeviceType, DeviceStatus, ConnectionType, DeviceDataValidator,
)
from .device_adapters import get_device_adapter
from .device_data_validator_service import device_data_validator_service
from ..db.mongodb import get_db
from ..core.exceptions import AppBaseException
from ..core.patient_access import patient_domain_mode
from ..patients.legacy import LegacyPatientRepository
from ..patients.repository import ClinicalPatientRepository

logger = logging.getLogger(__name__)


# ── 设备域角色语义统一（缺陷 B 盘点后收敛）─────────────────────────────────
# 只读路径（查看设备详情/数据/状态/分析/预警/维修记录）：医疗 staff
# doctor / health_manager / admin；健康管理师可查看其负责患者的设备数据。
DEVICE_READ_ROLES = ("doctor", "health_manager", "admin")
# 变更路径（配置/维修等）：设备属主本人或 doctor / admin；
# 健康管理师不可执行变更操作，患者仅可操作自己名下设备。
DEVICE_MUTATE_ROLES = ("doctor", "admin")


# ── 手工读数校验与阈值预警接线（T78，T69 盘点断链收口）──────────────────────
# manual 路径与 automated 路径的关系声明：
# - automated 路径（device_ingestion_service，T74 设备接入网关）有独立的
#   质量管道（硬拒绝/quality_flags 标记入库）与预警链
#   （device_analysis_service.generate_device_alerts），不经本节逻辑；
# - manual 路径（record_manual_reading）入库前走 device_data_standard
#   数据标准校验（与 device_data_validator_service 同源模型），入库提交后
#   best-effort 触发 health_alert_service.check_health_data（阈值字典比对，
#   命中即写 health_data_alerts，clinical 侧患者预警列表等既有通知链可见）。
# 两条路径互不替代：来源标记（metadata.source="手工登记" / "automated"）
# 与质量字段各归各管道。

#: 手工读数可映射到 vital_sign 阈值的数据类型（→ check_health_data.vital_type）。
#: 脉搏按心率阈值比对（同一量纲 bpm）；呼吸频率不在设备数据标准
#: （DEVICE_DATA_TYPES）内，不在此映射。
MANUAL_READING_VITAL_TYPES = {
    "heart_rate": "heart_rate",
    "pulse": "heart_rate",
    "blood_glucose": "blood_glucose",
    "body_temperature": "body_temperature",
    "oxygen_saturation": "oxygen_saturation",
}

#: 血压双分量 → check_health_data 血压字典（vital_type="blood_pressure"）的
#: 分量名；阈值按 {"systolic":…, "diastolic":…} 双分量取较严重状态。
MANUAL_READING_BLOOD_PRESSURE_PARTS = {
    "blood_pressure_systolic": "systolic",
    "blood_pressure_diastolic": "diastolic",
}

#: 血压双分量配对窗口：同设备另一分量在该读数时刻前 N 分钟内视为同次
#: 测量。先录入的分量本身不成对评估（对手分量到达时由其自身检查成对
#: 触发），窗口只向后看，避免跨次测量的旧分量误配。
BLOOD_PRESSURE_PAIR_WINDOW = timedelta(minutes=30)


class ManualReadingValidationError(AppBaseException):
    """手工读数不符合设备数据标准（畸形/超范围/设备类型不兼容）。"""

    def __init__(self, message: str, details: Optional[Dict] = None):
        super().__init__(message=message, status_code=422,
                         error_code="MANUAL_READING_INVALID",
                         details=details or {})


class DeviceService:
    """设备服务类，处理设备管理和数据相关功能"""
    
    def __init__(self, db=None):
        self.db = db

    async def _database(self):
        return self.db if self.db is not None else await get_db()

    async def get_user_devices(self, user_id: str) -> List[Dict]:
        """获取用户关联的设备列表"""
        return await self.get_patients_devices([str(user_id)])

    async def get_patients_devices(self, patient_ids) -> List[Dict]:
        db = await self._database()
        identifiers = LegacyPatientRepository._identifiers(patient_ids)
        devices = await db.devices.find(
            {"patient_id": {"$in": identifiers}, "status": {"$ne": "deleted"}}
        ).to_list(None)
        return [{**device, "_id": str(device["_id"])} for device in devices]

    async def list_registered_devices(self) -> List[Dict]:
        """管理员查看已登记设备。没有上报记录时不补造读数。"""
        db = await self._database()
        devices = await db.devices.find({"status": {"$ne": "deleted"}}).to_list(500)
        return [{**device, "_id": str(device["_id"])} for device in devices]
    
    async def get_device(self, device_id: str, *, session=None) -> Optional[Dict]:
        """获取设备详情；畸形 ID 与不存在的设备语义一致，返回 None"""
        if not ObjectId.is_valid(device_id):
            return None
        db = await self._database()
        device = await db.devices.find_one({"_id": ObjectId(device_id)},
                                          **({"session": session} if session is not None else {}))
        if device:
            device["_id"] = str(device["_id"])
        return device
    
    async def bind_device(self, user_id: str, device_data: Dict, *, actor) -> Dict:
        from app.core.device_access import resolve_device_patient
        from app.db.transactions import run_transaction
        db = await self._database()
        async def transaction(session):
            patient_id = await resolve_device_patient(db, actor, user_id, session=session, fence=True)
            return await self._insert_device(patient_id, device_data, session=session)
        return await run_transaction(db, transaction, error_code="DEVICE_TRANSACTION_UNAVAILABLE",
                                     error_message="设备绑定事务未能确认，请核查状态后重试")

    async def _insert_device(self, user_id: str, device_data: Dict, *, session):
        """绑定新设备到已存在的患者；账号角色不能替代患者实体。

        患者存在性复核按域分派（波次 5）：legacy 走 legacy 适配器（users，
        is_active 语义逐字不变）；canonical 走 ClinicalPatientRepository.get
        （clinical_patients，users 只读约定——canonical 患者实体不在 users，
        无账号患者由此可绑定设备）。canonical 文档没有 is_active 字段，
        status != "active"（迁移自 legacy 停用患者）按不可用处理，与
        内核 load_patient_doc 的 canonical 404 语义对齐。绑定后设备文档的
        patient_id 落所在域的患者主键（canonical 为 clinical_patients.
        patient_id，迁移保留主键值不变）。
        """
        db = await self._database()
        if await patient_domain_mode(db, session=session) == "canonical":
            patient = await ClinicalPatientRepository(db).get(user_id, session=session)
            if not patient or patient.get("status") != "active":
                return {"error": "设备只能绑定有效的患者档案"}
            user_id = str(patient["patient_id"])
        else:
            patient = await LegacyPatientRepository(db).get(user_id, session=session)
            if not patient or patient.get("is_active", True) is not True:
                return {"error": "设备只能绑定有效的患者档案"}
            user_id = str(patient["_id"])
        
        # 验证设备类型和固件版本
        if "device_type" in device_data and device_data["device_type"] not in [d.value for d in DeviceType]:
            return {"error": "不支持的设备类型"}
            
        # 注意：路由层传入 device.dict()，未填的可选字段以 None 出现，
        # 不能用 `"firmware_version" in device_data` 判断是否填写
        firmware_version = device_data.get("firmware_version")
        if firmware_version:
            if not device_data_validator_service.validate_device_firmware(firmware_version):
                return {"error": "固件版本格式不正确，应为x.y.z格式"}
                
        device = {
            "device_id": device_data.get("device_id", str(ObjectId())),
            "device_type": device_data["device_type"],
            "name": device_data["name"],
            "manufacturer": device_data.get("manufacturer"),
            "model": device_data.get("model"),
            "patient_id": user_id,
            "status": "active",
            "connection_type": device_data.get("connection_type"),
            "firmware_version": device_data.get("firmware_version"),
            "settings": device_data.get("settings", {}),
            "last_connected": None,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }
        
        result = await db.devices.insert_one(device, session=session)
        device["_id"] = str(result.inserted_id)
        return device
    
    async def unbind_device(self, user_id: str, device_id: str, *, actor=None) -> bool:
        """解绑用户设备；畸形 ID 视为设备不存在，返回 False"""
        if not ObjectId.is_valid(device_id):
            return False
        db = await self._database()
        from fastapi import HTTPException
        from app.core.device_access import ensure_device_access
        from app.db.transactions import run_transaction
        if actor is None:
            raise HTTPException(403, detail="设备解绑需要已认证操作者")
        async def transaction(session):
            device = await self.get_device(device_id, session=session)
            if not device or str(device.get("patient_id")) != str(user_id):
                return False
            await ensure_device_access(db, device, actor, DEVICE_READ_ROLES,
                                       write=True, session=session, fence=True)
            result = await db.devices.update_one(
                {"_id": ObjectId(device_id), "patient_id": device["patient_id"]},
                {"$set": {"status": "deleted", "updated_at": datetime.utcnow()}}, session=session)
            return result.modified_count > 0
        return await run_transaction(db, transaction, error_code="DEVICE_TRANSACTION_UNAVAILABLE",
                                     error_message="设备解绑事务未能确认，请核查状态后重试")
    
    async def get_device_data(
        self, 
        device_id: str, 
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        data_type: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict]:
        """获取设备数据"""
        db = await self._database()
        query = {"device_id": device_id}
        
        if start_date:
            query["timestamp"] = {"$gte": start_date}
        if end_date:
            if "timestamp" in query:
                query["timestamp"]["$lte"] = end_date
            else:
                query["timestamp"] = {"$lte": end_date}
        if data_type:
            query["data_type"] = data_type
            
        device_data = await db.device_data.find(query).sort(
            "timestamp", -1
        ).limit(limit).to_list(None)
        
        return [{**data, "_id": str(data["_id"])} for data in device_data]
    
    async def sync_device_data(self, device_id: str) -> Dict:
        """同步设备数据

        去模拟化（REM02）：原实现按设备类型选择适配器，随机生成心率/睡眠/
        血糖/肺功能等"采集数据"写入 device_data 集合，并更新 last_connected
        伪装连接成功。设备真实数据源（SDK/厂商云）尚未接入，此处如实拒绝，
        不生成任何数据、不更新 last_connected（未发生真实连接）。
        """
        device = await self.get_device(device_id)
        if not device:
            return {"success": False, "message": "设备不存在"}

        return {"success": False, "message": "设备数据源未接入，无法同步真实采集数据"}

    async def _device_mutation(self, device_id, actor, roles, callback):
        from fastapi import HTTPException
        from app.core.device_access import ensure_device_access
        from app.db.transactions import run_transaction
        if actor is None:
            raise HTTPException(403, detail="设备写操作需要已认证操作者")
        db = await self._database()
        async def transaction(session):
            device = await self.get_device(device_id, session=session)
            if not device or device.get("status") == "deleted":
                raise HTTPException(404, detail="设备不存在或已解绑")
            await ensure_device_access(db, device, actor, roles, write=True, session=session, fence=True)
            fence = device.get("_device_write_fence", 0)
            if type(fence) is not int or fence < 0:
                raise HTTPException(503, detail="设备写入并发状态无效")
            changed = await db.devices.update_one(
                {"_id": ObjectId(device_id), "patient_id": device.get("patient_id"), "status": device.get("status")},
                {"$inc": {"_device_write_fence": 1}}, session=session)
            if changed.matched_count != 1:
                raise HTTPException(409, detail="设备归属或状态已变化，请重新加载")
            return await callback(db, device, session)
        return await run_transaction(db, transaction, error_code="DEVICE_TRANSACTION_UNAVAILABLE",
                                     error_message="设备写入事务未能确认，请核查状态后重试")

    async def record_manual_reading(self, device_id: str, data_type: str, value: str, unit: str, measured_at: datetime, *, actor=None) -> Dict:
        """Persist explicitly manual provenance under the current patient/device authority.

        T78 接线（T69 盘点断链收口）：
        - 事务内先走设备数据标准校验（_validate_manual_reading）：畸形读数、
          超范围读数、设备类型不兼容一律拒绝（MANUAL_READING_INVALID 422，
          事务中止零写入）；未登记数据类型与自动采集管道语义一致，打
          unregistered_metric 标记放行（不硬拒、不猜测范围）；合格读数按
          标准精度与标准单位归一化后入库。
        - 事务提交后 best-effort 触发阈值预警检查
          （_run_manual_reading_alert_check）：预警是读数的派生副作用，
          不进读数事务（理由见该方法 docstring），检查结论如实写回
          metadata.health_alert 并随响应返回。
        """
        context = {}
        async def persist(db, device, session):
            validated = self._validate_manual_reading(device, data_type, value, unit)
            document = {"_id": ObjectId(), "device_id": device_id, "timestamp": measured_at,
                        "data_type": data_type, "value": validated["value"], "unit": validated["unit"],
                        "quality_flags": validated["quality_flags"],
                        "metadata": {"source": "手工登记", "recorded_by": str(actor.id)},
                        "created_at": datetime.utcnow()}
            await db.device_data.insert_one(document, session=session)
            document["id"] = str(document.pop("_id"))
            context["patient_id"] = device.get("patient_id")
            return document
        document = await self._device_mutation(device_id, actor, DEVICE_READ_ROLES, persist)
        await self._run_manual_reading_alert_check(document, context.get("patient_id"))
        return document

    def _validate_manual_reading(self, device: Dict, data_type: str, value: str, unit: str) -> Dict:
        """手工读数入库前校验/归一化（T78 接线第一段，事务内）。

        语义与 device_data_validator_service / device_data_standard 对齐：
        - 已登记数据类型：设备类型兼容性 + 数值解析 + 标准值域校验
          （DataTypeDefinition.validate_value），不合格抛
          ManualReadingValidationError(422)；数值按标准精度归一化
          （format_device_data），单位缺省回标准单位；
        - 未登记数据类型：与自动采集质量管道一致（device_ingestion_service
          的 unregistered_metric 标记入库，不硬拒绝、不猜测范围）。
        元数据必填字段（measurement_method 等）是设备上报标准语义，手工
        登记路由 schema（device_router.ManualReading，extra="forbid"）禁止
        额外字段、无法携带，故此处只校验值域与类型兼容性，不强制元数据。
        """
        data_type_def = DeviceDataValidator.get_data_type_definition(data_type)
        if data_type_def is None:
            from .device_ingestion_service import FLAG_UNREGISTERED_METRIC
            return {"value": value, "unit": unit,
                    "quality_flags": [FLAG_UNREGISTERED_METRIC]}

        # 设备类型兼容性：设备文档登记了标准设备类型才判，缺失/畸形不猜测
        # （与自动管道对畸形配置的处理一致）
        try:
            device_enum = DeviceType(device.get("device_type"))
        except ValueError:
            device_enum = None
        if device_enum is not None and device_enum not in data_type_def.device_types:
            raise ManualReadingValidationError(
                f"设备类型「{device.get('device_type')}」不支持数据类型「{data_type}」",
                details={"device_type": device.get("device_type"), "data_type": data_type})

        normalized_value, normalized_unit = value, unit or data_type_def.unit
        if data_type_def.min_value is not None or data_type_def.max_value is not None:
            # 数值型指标：手工录入值为字符串，先解析为数字再按标准值域校验；
            # 解析失败即畸形读数，越界即超范围读数，均拒绝（不入库）
            try:
                numeric = float(str(value).strip())
            except (TypeError, ValueError):
                raise ManualReadingValidationError(
                    f"读数「{value}」无法解析为数值（{data_type_def.name}）",
                    details={"data_type": data_type, "value": value})
            if not math.isfinite(numeric) or not data_type_def.validate_value(numeric):
                raise ManualReadingValidationError(
                    f"读数 {numeric:g} 超出「{data_type_def.name}」有效范围 "
                    f"[{data_type_def.min_value}, {data_type_def.max_value}]",
                    details={"data_type": data_type, "value": value,
                             "min": data_type_def.min_value, "max": data_type_def.max_value})
            normalized_value = DeviceDataValidator.format_device_data(data_type, numeric)
        return {"value": normalized_value, "unit": normalized_unit, "quality_flags": []}

    async def _run_manual_reading_alert_check(self, document: Dict, patient_id) -> None:
        """事务提交后的阈值预警检查（T78 接线第二段，best-effort）。

        事务取舍：预警是读数入库的派生副作用，写入 health_alert_service
        自己的 alerts 集合（health_data_alerts），与 device_data 读数不在
        一个一致性单元上；不进读数事务——读数入库语义保持原子，预警检查
        失败不回滚读数也不影响 201 响应，检查结论（含失败）如实写回
        metadata.health_alert 并随响应返回，漏发预警可经健康预警端点手动
        重建。结论回写亦为 best-effort：回写失败时响应内仍可见（此时仅
        库内读数 metadata 缺该备注）。
        """
        db = await self._database()
        try:
            note = await self._check_manual_reading_threshold(db, document, patient_id)
        except Exception as exc:  # noqa: BLE001 —— 预警检查失败不阻塞读数响应
            logger.warning("手工读数阈值预警检查未完成: %r (device=%s data_type=%s)",
                           exc, document.get("device_id"), document.get("data_type"))
            note = {"status": "check_failed",
                    "message": "阈值预警检查未完成，可经健康预警端点手动核查"}
        document.setdefault("metadata", {})["health_alert"] = note
        try:
            await db.device_data.update_one(
                {"_id": ObjectId(document["id"])},
                {"$set": {"metadata": document["metadata"]}})
        except Exception as exc:  # noqa: BLE001 —— 结论回写失败不影响响应
            logger.warning("手工读数预警结论回写失败: %r (reading=%s)", exc, document.get("id"))

    async def _check_manual_reading_threshold(self, db, document: Dict, patient_id) -> Dict:
        """把手工读数映射到 health_alert_service.check_health_data 并比对阈值。

        无阈值映射的数据类型（含未登记指标）如实返回 skipped，不做比对。
        """
        data_type = document["data_type"]
        vital_type = MANUAL_READING_VITAL_TYPES.get(data_type)
        check_value = self._as_numeric(document["value"])
        if check_value is None:
            return {"status": "skipped", "message": "读数值非数值，未做阈值比对"}
        if vital_type is None:
            part = MANUAL_READING_BLOOD_PRESSURE_PARTS.get(data_type)
            if part is None:
                return {"status": "skipped",
                        "message": "该数据类型未配置健康阈值映射，未做阈值比对"}
            counterpart = await self._paired_blood_pressure_value(db, document, part)
            if counterpart is None:
                return {"status": "skipped",
                        "message": "血压双分量不成对（窗口内缺另一分量读数），未做阈值比对"}
            vital_type = "blood_pressure"
            check_value = {part: check_value,
                           "diastolic" if part == "systolic" else "systolic": counterpart}

        from .health_alert_service import HealthAlertService
        check = await HealthAlertService(db).check_health_data(
            health_data_id=document["id"],
            patient_id=str(patient_id),
            data_type="vital_sign",
            vital_type=vital_type,
            value=check_value,
            recorded_at=document.get("timestamp"),
            unit=document.get("unit"))
        return {"status": check["status"], "message": check.get("message"),
                "threshold_id": check.get("threshold_id"),
                "alert_id": check.get("alert_id")}

    async def _paired_blood_pressure_value(self, db, document: Dict, part: str) -> Optional[float]:
        """取同设备、该读数时刻前配对窗口内另一血压分量的最近读数。"""
        counterpart_type = ("blood_pressure_diastolic" if part == "systolic"
                            else "blood_pressure_systolic")
        since = document["timestamp"] - BLOOD_PRESSURE_PAIR_WINDOW
        docs = await db.device_data.find({
            "device_id": document["device_id"],
            "data_type": counterpart_type,
            "timestamp": {"$gte": since, "$lte": document["timestamp"]},
        }).sort("timestamp", -1).limit(1).to_list(1)
        return self._as_numeric(docs[0].get("value")) if docs else None

    @staticmethod
    def _as_numeric(value) -> Optional[float]:
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return None
        return numeric if math.isfinite(numeric) else None

    async def get_device_status(self, device_id: str) -> Dict:
        """获取设备状态

        去模拟化：状态仅由设备文档真实字段（last_connected）推导，
        电量/信号强度全库无真实上报，如实透出 None（未上报），
        不再随机生成电量与信号格数。
        """
        device = await self.get_device(device_id)
        if not device:
            return {
                "status": "error",
                "message": "设备不存在",
                "battery_level": None,
                "signal_strength": None,
                "last_sync_time": None
            }

        # 根据设备类型选择适配器
        adapter = get_device_adapter(device["device_type"])

        # 使用适配器获取状态
        try:
            status = await adapter.get_status(device)
            return status
        except Exception as e:
            return {
                "status": "error",
                "message": f"获取状态失败: {str(e)}",
                "battery_level": None,
                "signal_strength": None,
                "last_sync_time": device.get("last_connected")
            }
    
    async def configure_device(self, device_id: str, config: Dict, *, actor=None) -> Dict:
        """Merge configuration using a transaction protected by current ownership."""
        async def persist(db, device, session):
            settings = device.get("settings") or {}
            if not isinstance(settings, dict):
                from fastapi import HTTPException
                raise HTTPException(409, detail="历史设备配置结构无效，请核实")
            await db.devices.update_one({"_id": ObjectId(device_id)}, {"$set": {
                "settings": {**settings, **config}, "updated_at": datetime.utcnow()}}, session=session)
            return {"success": True, "message": "设备配置已更新"}
        return await self._device_mutation(device_id, actor, DEVICE_MUTATE_ROLES, persist)

    async def set_gateway_credential(self, device_id: str, *, actor=None,
                                     device_key: Optional[str] = None) -> Dict:
        """登记/轮换设备网关凭证（T74 自动采集接入）。

        设备侧采集端以 device_key 作为共享凭证上报网关；生成值仅在响应中
        透出一次（库内留存用于比对，厂商正式鉴权方案到位后替换）。
        走既有设备变更事务与角色围栏（doctor/admin）。
        """
        from .device_ingestion_service import device_ingestion_service
        key = device_key or device_ingestion_service.generate_device_key()
        async def persist(db, device, session):
            await db.devices.update_one({"_id": ObjectId(device_id)}, {"$set": {
                "device_key": key, "updated_at": datetime.utcnow()}}, session=session)
            return {"success": True, "message": "设备网关凭证已登记",
                    "device_key": key}
        return await self._device_mutation(device_id, actor, DEVICE_MUTATE_ROLES, persist)

    async def get_supported_data_types(self, device_type: Optional[str] = None) -> Dict:
        """
        获取支持的数据类型
        
        参数:
        - device_type: 可选的设备类型
        
        返回:
        - 数据类型列表
        """
        if device_type:
            return device_data_validator_service.get_supported_data_types_for_device(device_type)
        else:
            # 返回所有设备类型
            all_types = []
            for device_enum in DeviceType:
                device_data_types = device_data_validator_service.get_supported_data_types_for_device(device_enum.value)
                all_types.append({
                    "device_type": device_enum.value,
                    "data_types": device_data_types
                })
            return all_types


device_service = DeviceService()

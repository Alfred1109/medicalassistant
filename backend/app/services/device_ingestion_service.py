"""设备数据接入网关服务（T74 真实设备接入软件侧框架）

链路：设备采集端 → 网关端点(device_router /gateway/*) → 设备凭证鉴权
→ DeviceProtocolAdapter.parse（device_protocol 包，按型号选择适配器）
→ 质量校验管道（本服务，入库前）→ 原子写入 device_data 原始遥测与
health_data 临床事实（模拟回放仅存遥测）→ 触发既有分析/预警链
（device_analysis_service.generate_device_alerts，复用不重造）。

职责边界：
- 协议解析在 device_protocol 适配器内；本服务只做设备无关的质量校验
  （必填、数值范围按指标可配置、时间戳合理性、重复剔除）；
- 去模拟化约定（REM02）继续有效：唯一"造数"入口是模拟回放器
  （device_protocol.jmd540.JMD540SimulatedReplayer），其输出强制携带
  simulated 标记，入库 metadata.source="automated_simulated_replay"，
  仅用于测试与演示，绝不冒充真实采集；
- 质量分级：
  * 硬拒绝（不入库）：必填缺失、时间戳无法解析/超前/过旧 —— 计入
    响应 rejected 与质量统计；
  * 标记入库：数值超范围（out_of_range:<metric>）、乱序
    （out_of_order）、未登记指标（unregistered_metric）—— 写入
    device_data.quality_flags，分析侧可见可过滤；
  * 重复剔除：device_id+timestamp+data_type 已存在（幂等），不重复写。
"""
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from bson import ObjectId

from ..db.mongodb import get_db
from .device_analysis_service import device_analysis_service
from .device_protocol import (
    DeviceProtocolAdapter,
    JMD540SimulatedReplayer,
    get_protocol_adapter,
)

#: 单次批上报帧数上限
MAX_FRAMES_PER_BATCH = 500

#: 时间戳合理性阈值（可按设备 settings.ingestion_quality 覆盖）
MAX_FUTURE_SECONDS = 300      # 未来 5 分钟以上视为设备时钟异常
MAX_AGE_DAYS = 365            # 超过一年的历史数据拒收（时钟漂移/重放防护）

#: 默认指标数值范围（指标 → (min, max)）；未登记指标不判范围只打标。
#: 与 JMD540_METRICS 指标集合对应；设备级覆盖见
#: devices.settings.ingestion_quality.ranges = {metric: [min, max]}
DEFAULT_METRIC_RANGES: Dict[str, Tuple[float, float]] = {
    "heart_rate": (20.0, 250.0),
    "spo2": (50.0, 100.0),
    "systolic_pressure": (50.0, 250.0),
    "diastolic_pressure": (30.0, 150.0),
    "body_temperature": (30.0, 43.0),
    "respiration_rate": (5.0, 60.0),
    "blood_glucose": (1.0, 35.0),
}

#: 质量标记常量（写入 device_data.quality_flags，分析侧可见）
FLAG_OUT_OF_RANGE_PREFIX = "out_of_range:"
FLAG_OUT_OF_ORDER = "out_of_order"
FLAG_UNREGISTERED_METRIC = "unregistered_metric"

#: 自动采集来源标记（metadata.source）
SOURCE_AUTOMATED = "automated"
SOURCE_AUTOMATED_SIMULATED = "automated_simulated_replay"
SOURCE_VEEPOO_WECHAT = "veepoo_wechat"


def _hardware_id_bytes(value: Any) -> Optional[bytes]:
    """Encode a hardware identifier without restricting it to an ASCII format."""
    if not isinstance(value, str):
        return None
    try:
        return value.encode("utf-8")
    except UnicodeEncodeError:
        return None


def _same_hardware_id(left: Any, right: Any) -> bool:
    left_bytes = _hardware_id_bytes(left)
    right_bytes = _hardware_id_bytes(right)
    return (left_bytes is not None and right_bytes is not None
            and secrets.compare_digest(left_bytes, right_bytes))


class DeviceIngestionError(Exception):
    """网关上报处理的结构性错误（设备未启用接入等），转 4xx 语义。"""

    def __init__(self, message: str, status_code: int = 400):
        self.status_code = status_code
        super().__init__(message)


class DeviceIngestionService:
    """设备数据接入网关：鉴权 → 适配器解析 → 质量管道 → 入库 → 分析链"""

    def __init__(self, db=None):
        self.db = db

    async def _database(self):
        return self.db if self.db is not None else await get_db()

    @staticmethod
    def _snapshot_selector(device):
        return {"_id": ObjectId(device["_id"]), "patient_id": device.get("patient_id"),
                "status": device.get("status"), "device_key": device.get("device_key")}

    @staticmethod
    def _source_filter(source):
        if source == SOURCE_AUTOMATED_SIMULATED:
            return {"$or": [{"metadata.source": SOURCE_AUTOMATED_SIMULATED},
                            {"metadata.simulated": True}]}
        return {"metadata.source": {"$ne": SOURCE_AUTOMATED_SIMULATED},
                "metadata.simulated": {"$ne": True}}

    # ── 设备凭证鉴权 ────────────────────────────────────────────────────
    async def authenticate_device(
        self, device_sn: str, device_key: str,
    ) -> Dict[str, Any]:
        """按 device_sn（devices.device_id）+ device_key 鉴权。

        返回设备文档（_id 已字符串化）；失败抛 DeviceIngestionError：
        - 设备不存在 / 已解绑（deleted）→ 统一"设备未登记"（不暴露存在性）；
        - 未配置 device_key → "未启用自动采集接入"（需先登记凭证）；
        - 凭证不符 → "设备凭证无效"。
        """
        db = await self._database()
        device = await db.devices.find_one({
            "device_id": device_sn, "status": {"$ne": "deleted"}})
        if not device:
            raise DeviceIngestionError("设备未登记或已解绑", 404)
        stored_key = device.get("device_key")
        if not stored_key:
            raise DeviceIngestionError("设备未启用自动采集接入，请先登记网关凭证", 403)
        if not device_key or not hmac.compare_digest(
                str(stored_key), str(device_key)):
            raise DeviceIngestionError("设备凭证无效", 401)
        device["_id"] = str(device["_id"])
        return device

    async def _touch_device(
        self, expected_device: Dict[str, Any], *, battery_level: Optional[float] = None,
        session=None) -> None:
        """真实上报/心跳到达 → 更新 last_connected（及可选的真实上报电量）。

        仅记录真实发生的连接；无上报路径的字段保持 None（去模拟化口径）。
        """
        db = await self._database()
        update: Dict[str, Any] = {"last_connected": datetime.utcnow(),
                                  "updated_at": datetime.utcnow()}
        if battery_level is not None:
            update["battery_level"] = battery_level
        result = await db.devices.update_one(
            self._snapshot_selector(expected_device),
            {"$set": update}, **({"session": session} if session else {}))
        if result.matched_count != 1:
            raise DeviceIngestionError("设备归属、状态或凭证已变化，未刷新连接状态", 409)

    # ── 质量校验管道 ────────────────────────────────────────────────────
    def _quality_config(self, device: Dict[str, Any]) -> Dict[str, Any]:
        """设备级质量配置（settings.ingestion_quality），缺省回全局默认。"""
        settings = device.get("settings") or {}
        quality = settings.get("ingestion_quality") or {}
        ranges = quality.get("ranges") or DEFAULT_METRIC_RANGES
        return {
            "ranges": ranges,
            "max_future_seconds": quality.get(
                "max_future_seconds", MAX_FUTURE_SECONDS),
            "max_age_days": quality.get("max_age_days", MAX_AGE_DAYS),
        }

    def _validate_timestamp(
            self, ts: datetime, config: Dict[str, Any]) -> Optional[str]:
        """时间戳合理性；不合理返回拒绝原因（硬拒绝，不入库）。"""
        ts = self._naive_utc(ts)
        now = datetime.utcnow()
        if ts > now + timedelta(seconds=config["max_future_seconds"]):
            return f"时间戳超前（设备时钟异常）: {ts.isoformat()}"
        if ts < now - timedelta(days=config["max_age_days"]):
            return f"时间戳过旧（超过 {config['max_age_days']} 天）: {ts.isoformat()}"
        return None

    def _range_flags(
            self, data_type: str, value: float,
            config: Dict[str, Any]) -> List[str]:
        """数值范围检查：返回质量标记列表（标记入库，不硬拒绝）。"""
        flags: List[str] = []
        range_def = config["ranges"].get(data_type)
        if range_def is None:
            flags.append(FLAG_UNREGISTERED_METRIC)
            return flags
        try:
            lo, hi = float(range_def[0]), float(range_def[1])
        except (TypeError, ValueError, IndexError):
            return flags  # 配置畸形时不猜测，交由人工修配置
        if not (lo <= value <= hi):
            flags.append(f"{FLAG_OUT_OF_RANGE_PREFIX}{data_type}")
        return flags

    @staticmethod
    def _naive_utc(ts: datetime) -> datetime:
        if ts.tzinfo is not None:
            return ts.astimezone(tz=timezone.utc).replace(tzinfo=None)
        return ts

    async def _is_duplicate(
            self, db, device_internal_id: str, data_type: str,
            timestamp: datetime, *, source=SOURCE_AUTOMATED, session=None) -> bool:
        """Preserve real-reading identity; simulation occupies a separate source scope."""
        existing = await db.device_data.find_one({
            "device_id": device_internal_id,
            "data_type": data_type,
            "timestamp": timestamp,
            **self._source_filter(source),
        }, session=session)
        return existing is not None

    # ── 上报主流程 ──────────────────────────────────────────────────────
    def _select_adapter(
            self, device: Dict[str, Any]) -> Optional[DeviceProtocolAdapter]:
        """按设备型号选择协议适配器；未登记型号返回 None（如实拒绝）。"""
        return get_protocol_adapter(device.get("model"))

    async def ingest(
        self, device: Dict[str, Any], frames: List[Dict[str, Any]],
        *, simulated: bool = False,
    ) -> Dict[str, Any]:
        """处理一批上报帧：解析 → 质量校验 → 入库 → 分析链。

        frames：设备原始载荷帧列表（1..500）；simulated=True 时帧数
        决定模拟回放帧数（仅测试/演示，读数强制打 simulated 标记）。
        """
        if not frames or len(frames) > MAX_FRAMES_PER_BATCH:
            raise DeviceIngestionError(
                f"上报帧数必须为 1..{MAX_FRAMES_PER_BATCH}", 400)

        if simulated:
            replayer = JMD540SimulatedReplayer()
            parsed_frames = replayer.replay(
                frame_count=len(frames), device_sn=device.get("device_id"))
            source = SOURCE_AUTOMATED_SIMULATED
        else:
            adapter = self._select_adapter(device)
            if adapter is None:
                raise DeviceIngestionError(
                    f"设备型号 {device.get('model')!r} 未登记协议适配器，"
                    "无法解析上报载荷", 422)
            parsed_frames = [adapter.parse(f) for f in frames]
            source = SOURCE_AUTOMATED
        return await self._process_parsed_frames(device, parsed_frames,
                                                 source=source)

    async def pin_veepoo_hardware_id(
        self, device: Dict[str, Any], hardware_id: str, *, actor,
    ) -> Dict[str, Any]:
        """Bind the first user-confirmed Veepoo identity to an F300 record.

        This associates an authenticated account's selected watch with its
        already-bound device record. It is not cryptographic BLE attestation.
        Later uploads must present the same SDK-reported hardware identifier.
        """
        if str(device.get("model") or "").strip().casefold() != "f300":
            raise DeviceIngestionError("此设备不是已登记的 F300", 422)
        if device.get("status") == "deleted" or not device.get("patient_id"):
            raise DeviceIngestionError("设备未绑定有效患者", 409)
        if (not isinstance(hardware_id, str) or not hardware_id.strip()
                or len(hardware_id) > 128 or _hardware_id_bytes(hardware_id) is None):
            raise DeviceIngestionError("缺少有效的 Veepoo 设备标识", 422)

        from app.db.transactions import run_transaction

        db = await self._database()
        device_internal_id = str(device["_id"])
        hardware_id = hardware_id.strip()

        async def persist(session):
            current = await db.devices.find_one(
                {"_id": ObjectId(device_internal_id)}, session=session)
            if (not current or current.get("status") == "deleted"
                    or str(current.get("patient_id")) != str(device.get("patient_id"))
                    or str(current.get("model") or "").strip().casefold() != "f300"):
                raise DeviceIngestionError("设备归属或状态已变化", 409)
            from app.core.device_access import ensure_device_access
            from .device_service import DEVICE_READ_ROLES
            await ensure_device_access(
                db, current, actor, DEVICE_READ_ROLES,
                write=True, session=session, fence=True)
            settings = current.get("settings") or {}
            if not isinstance(settings, dict):
                raise DeviceIngestionError("设备设置结构无效，无法关联手环", 409)
            claimed_id = settings.get("claimed_hardware_id")
            if claimed_id is not None and not _same_hardware_id(claimed_id, hardware_id):
                raise DeviceIngestionError("手环标识与绑定时确认的设备不一致", 409)
            saved_id = settings.get("veepoo_hardware_id")
            if saved_id is not None:
                if not _same_hardware_id(saved_id, hardware_id):
                    raise DeviceIngestionError("当前手环与已关联设备不匹配", 409)
                return current

            fence = current.get("_device_write_fence", 0)
            if type(fence) is not int or fence < 0:
                raise DeviceIngestionError("设备写入并发状态无效", 503)
            selector = {
                "_id": ObjectId(device_internal_id),
                "patient_id": current.get("patient_id"),
                "status": current.get("status"),
                "settings": current.get("settings"),
                "$or": ([{"_device_write_fence": 0},
                         {"_device_write_fence": {"$exists": False}}]
                        if fence == 0 else [{"_device_write_fence": fence}]),
            }
            updated_settings = {**settings, "veepoo_hardware_id": hardware_id}
            changed = await db.devices.update_one(
                selector,
                {"$set": {"settings": updated_settings,
                          "updated_at": datetime.utcnow()},
                 "$inc": {"_device_write_fence": 1}},
                session=session)
            if changed.matched_count != 1:
                raise DeviceIngestionError("设备归属或设置已变化，请重新同步", 409)
            current["settings"] = updated_settings
            return current

        return await run_transaction(
            db, persist, error_code="DEVICE_TRANSACTION_UNAVAILABLE",
            error_message="设备关联事务未能确认，请核查状态后重试")

    async def ingest_veepoo_readings(
        self, device: Dict[str, Any], readings: List[Dict[str, Any]], *, actor,
    ) -> Dict[str, Any]:
        """Process normalized readings from the Veepoo WeChat F300 SDK."""
        from .device_protocol.base import AdapterParseResult, StandardReading

        if not readings or len(readings) > MAX_FRAMES_PER_BATCH:
            raise DeviceIngestionError(
                f"上报读数必须为 1..{MAX_FRAMES_PER_BATCH}", 400)
        settings = device.get("settings") or {}
        expected_hardware_id = settings.get("veepoo_hardware_id")
        if not isinstance(expected_hardware_id, str) or not expected_hardware_id:
            raise DeviceIngestionError("F300 尚未关联 Veepoo 设备标识", 409)
        parsed = []
        for index, item in enumerate(readings):
            if not isinstance(item, dict):
                raise DeviceIngestionError(f"第 {index + 1} 条读数格式无效", 422)
            try:
                metadata = {
                    "adapter_id": "veepoo-wechat-f300-v1",
                    "sdk_type": item["sdk_type"],
                    "capture_time_source": "phone_callback",
                    "record_key": item.get("record_key"),
                    "raw_payload": item.get("raw_payload") or {},
                }
                reading = StandardReading(
                    data_type=item["data_type"], value=float(item["value"]),
                    unit=item["unit"], timestamp=item["measured_at"],
                    metadata=metadata)
            except (KeyError, TypeError, ValueError) as exc:
                raise DeviceIngestionError(
                    f"第 {index + 1} 条读数缺少有效字段", 422) from exc
            parsed.append(AdapterParseResult(readings=[reading]))
        return await self._process_parsed_frames(
            device, parsed, source=SOURCE_VEEPOO_WECHAT, actor=actor,
            expected_hardware_id=expected_hardware_id)

    async def _process_parsed_frames(
        self, device: Dict[str, Any], parsed_frames, *, source: str, actor=None,
        expected_hardware_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """解析结果 → 质量管道 → 入库 → 分析链（真实上报与模拟回放共用）。"""
        db = await self._database()
        device_internal_id = str(device["_id"])
        config = self._quality_config(device)

        # 会话归属：设备存在进行中的采集会话时，读数挂 session_id
        active_session = await db.device_collection_sessions.find_one(
            {"device_id": device_internal_id, "status": "active"})
        session_id = str(active_session["_id"]) if active_session else None

        # 乱序检测基准：库内该设备最新一条读数的时间戳
        latest = await db.device_data.find(
            {"device_id": device_internal_id, **self._source_filter(source)}
        ).sort("timestamp", -1).limit(1).to_list(1)
        latest_ts = latest[0]["timestamp"] if latest else None

        results: List[Dict[str, Any]] = []
        rejected: List[Dict[str, Any]] = []
        battery_seen: Optional[float] = None
        in_batch_seen = set()

        for frame_index, parsed in enumerate(parsed_frames):
            battery_seen = parsed.battery_level if parsed.battery_level is not None \
                else battery_seen
            for error in parsed.errors:
                rejected.append({"frame_index": frame_index, "error": error})
            for reading in parsed.readings:
                outcome = await self._process_reading(
                    db, device_internal_id, str(device.get("patient_id")),
                    reading, config, latest_ts, session_id, source,
                    frame_index, in_batch_seen, device, actor=actor,
                    expected_hardware_id=expected_hardware_id)
                if outcome["action"] == "written" and (source == SOURCE_AUTOMATED_SIMULATED
                                                         or outcome["clinical_fact_created"]):
                    ts = outcome["timestamp"]
                    if latest_ts is None or ts > latest_ts:
                        latest_ts = ts
                results.append(outcome)

        # 真实到达：刷新连接状态（电量仅用报文自带的真值）
        await self._touch_device(device, battery_level=battery_seen)
        alerts = await self._trigger_analysis(device_internal_id)
        return self._ingest_response(device, results, rejected, alerts=alerts)

    async def _process_reading(
        self, db, device_internal_id: str, patient_id: Optional[str],
        reading, config: Dict[str, Any], latest_ts: Optional[datetime],
        session_id: Optional[str], source: str, frame_index: int,
        in_batch_seen: set, expected_device: Dict[str, Any],
        *, actor=None, expected_hardware_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """单条标准化读数：质量校验 → 幂等去重 → 入库（或标记/拒绝）。"""
        data_type = reading.data_type
        ts = self._naive_utc(reading.timestamp)

        ts_error = self._validate_timestamp(reading.timestamp, config)
        if ts_error:
            return self._outcome("rejected", frame_index, data_type, ts,
                                 reason=ts_error, error=ts_error)

        value = float(reading.value)
        flags = self._range_flags(data_type, value, config)

        source_scope = (SOURCE_AUTOMATED_SIMULATED if source == SOURCE_AUTOMATED_SIMULATED
                        or reading.metadata.get("simulated") is True else source)
        dedup_key = (device_internal_id, data_type, ts, source_scope)
        if dedup_key in in_batch_seen:
            return self._outcome("duplicate", frame_index, data_type, ts,
                                 reason="同批次内重复读数")
        out_of_order = (latest_ts is not None and ts < latest_ts)
        if out_of_order:
            flags.append(FLAG_OUT_OF_ORDER)

        metadata = dict(reading.metadata)
        # 原始载荷留存：适配器未附带时保留最小原始字段
        raw_payload = reading.metadata.get("raw_payload")
        if raw_payload is None:
            raw_payload = {"metric": data_type, "value": reading.value}
        metadata.update({
            "source": source,
            "raw_payload": raw_payload,
            "session_id": session_id,
        })
        document = {
            "_id": ObjectId(),
            "device_id": device_internal_id,
            "patient_id": patient_id,
            "data_type": data_type,
            "value": value,
            "unit": reading.unit,
            "timestamp": ts,
            "metadata": metadata,
            "quality_flags": flags,
            "created_at": datetime.utcnow(),
        }
        from app.db.transactions import run_transaction
        from .device_health_data import fence_device_patient, insert_device_health_data

        async def persist(session):
            # Serialize with other ingestion and existing manual device mutations.
            # Recheck the authenticated ownership/status/key snapshot rather than
            # silently attaching a stale request to a new patient after rebinding.
            current = await db.devices.find_one({"_id": ObjectId(device_internal_id)}, session=session)
            if not current or current.get("status") == "deleted":
                raise DeviceIngestionError("设备已解绑或不存在，未保存本条读数", 409)
            if actor is not None:
                from app.core.device_access import ensure_device_access
                from .device_service import DEVICE_READ_ROLES
                await ensure_device_access(
                    db, current, actor, DEVICE_READ_ROLES,
                    write=True, session=session, fence=True)
            if expected_hardware_id is not None:
                current_settings = current.get("settings") or {}
                current_hardware_id = current_settings.get("veepoo_hardware_id") \
                    if isinstance(current_settings, dict) else None
                if not _same_hardware_id(current_hardware_id, expected_hardware_id):
                    raise DeviceIngestionError(
                        "F300 设备标识在上报期间已变化，未保存本条读数", 409)
            if not isinstance(current.get("patient_id"), (str, ObjectId)) or not str(current["patient_id"]):
                raise DeviceIngestionError("设备尚未关联患者，未保存本条读数", 409)
            fence = current.get("_device_write_fence", 0)
            if type(fence) is not int or fence < 0:
                raise DeviceIngestionError("设备写入并发状态无效", 503)
            selector = self._snapshot_selector(expected_device)
            changed = await db.devices.update_one(selector, {"$inc": {"_device_write_fence": 1}}, session=session)
            if changed.matched_count != 1:
                raise DeviceIngestionError("设备归属、状态或凭证已变化，未保存本条读数", 409)
            if source != SOURCE_AUTOMATED_SIMULATED:
                await fence_device_patient(db, expected_device.get("patient_id"), session=session)
            if await self._is_duplicate(db, device_internal_id, data_type, ts, source=source_scope, session=session):
                return False
            await db.device_data.insert_one(document, session=session)
            await insert_device_health_data(db, document, patient_id, session=session)
            return True

        written = await run_transaction(db, persist, error_code="DEVICE_TRANSACTION_UNAVAILABLE",
                                        error_message="设备读数事务未能确认，请使用相同载荷重试")
        in_batch_seen.add(dedup_key)
        if not written:
            return self._outcome("duplicate", frame_index, data_type, ts,
                                 reason="库内已存在同来源范围的设备+时间戳+指标；本次未新增临床事实，不回填历史")
        return self._outcome("written", frame_index, data_type, ts,
                             quality_flags=flags,
                             clinical_fact_created=(source != SOURCE_AUTOMATED_SIMULATED
                                                    and metadata.get("simulated") is not True))

    @staticmethod
    def _outcome(action: str, frame_index: int, data_type: str,
                 timestamp: datetime, *, reason: str = "",
                 error: str = "",
                 quality_flags: Optional[List[str]] = None,
                 clinical_fact_created: bool = False) -> Dict[str, Any]:
        return {
            "action": action,  # written / duplicate / rejected
            "frame_index": frame_index,
            "data_type": data_type,
            "timestamp": timestamp,
            "quality_flags": quality_flags or [],
            "reason": reason,
            "error": error,
            "clinical_fact_created": clinical_fact_created,
        }

    @staticmethod
    def _ingest_response(device: Dict[str, Any],
                         results: List[Dict[str, Any]],
                         frame_errors: List[Dict[str, Any]],
                         *, alerts: List[Dict[str, Any]]) -> Dict[str, Any]:
        written = [r for r in results if r["action"] == "written"]
        duplicated = [r for r in results if r["action"] == "duplicate"]
        # 硬拒绝 = 帧级解析错误 + 读数级质量硬拒绝（必填/时间戳异常）
        rejected = [r for r in results if r["action"] == "rejected"] + frame_errors
        flagged = [r for r in written if r["quality_flags"]]
        return {
            "success": True,
            "device": {"id": str(device["_id"]),
                       "device_sn": device.get("device_id")},
            "accepted_count": len(written),
            "clinical_facts_created": sum(r["clinical_fact_created"] for r in written),
            "duplicate_count": len(duplicated),
            "rejected_count": len(rejected),
            "rejected": rejected,
            "readings": results,
            "quality_flags_summary": {
                flag: sum(1 for r in written if flag in r["quality_flags"])
                for flag in {f for r in written for f in r["quality_flags"]}
            },
            "flagged_count": len(flagged),
            "alerts_generated": len(alerts),
            "alerts": alerts[:20],
        }

    async def _trigger_analysis(self, device_internal_id: str
                                ) -> List[Dict[str, Any]]:
        """复用既有分析/预警链（device_analysis_service），不重造。

        分析链失败不阻断入库确认（数据已落库），如实透出 alerts_error。
        """
        try:
            return await device_analysis_service.generate_device_alerts(
                device_id=device_internal_id, severity_threshold="low")
        except Exception as exc:  # 分析链不可用不应丢数据
            return [{"type": "analysis_chain_error", "message": str(exc)}]

    # ── 心跳 ───────────────────────────────────────────────────────────
    async def heartbeat(self, device: Dict[str, Any]) -> Dict[str, Any]:
        """设备心跳：刷新 last_connected，返回当前采集会话（如有）。"""
        db = await self._database()
        device_internal_id = str(device["_id"])
        await self._touch_device(device)
        session = await db.device_collection_sessions.find_one(
            {"device_id": device_internal_id, "status": "active"})
        return {
            "status": "ok",
            "server_time": datetime.utcnow(),
            "active_session_id": str(session["_id"]) if session else None,
        }

    # ── 质量报告 ────────────────────────────────────────────────────────
    async def quality_report(
        self, device_id: str, start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """按设备/时段的自动采集数据合格率统计（扫描 device_data）。"""
        db = await self._database()
        query: Dict[str, Any] = {
            "device_id": device_id,
            "metadata.source": {"$in": [SOURCE_AUTOMATED,
                                        SOURCE_AUTOMATED_SIMULATED]},
        }
        if start or end:
            ts_query: Dict[str, datetime] = {}
            if start:
                ts_query["$gte"] = start
            if end:
                ts_query["$lte"] = end
            query["timestamp"] = ts_query
        docs = await db.device_data.find(query).to_list(None)

        total = len(docs)
        flagged_docs = [d for d in docs if d.get("quality_flags")]
        flag_counter: Dict[str, int] = {}
        for d in flagged_docs:
            for flag in d.get("quality_flags") or []:
                flag_counter[flag] = flag_counter.get(flag, 0) + 1
        return {
            "device_id": device_id,
            "window": {"start": start, "end": end},
            "total_automated": total,
            "passed": total - len(flagged_docs),
            "flagged": len(flagged_docs),
            "pass_rate": (round((total - len(flagged_docs)) / total, 4)
                          if total else None),
            "flags": flag_counter,
            "out_of_range_count": sum(
                count for flag, count in flag_counter.items()
                if flag.startswith(FLAG_OUT_OF_RANGE_PREFIX)),
        }

    # ── 采集会话 ────────────────────────────────────────────────────────
    async def start_collection_session(
        self, device: Dict[str, Any], patient_id: str,
        *, plan_id: Optional[str] = None,
        version_id: Optional[str] = None,
        prescription_item_id: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """开始设备观测会话，可选绑定本患者当前已发布版本的处方项。"""
        db = await self._database()
        device_internal_id = str(device["_id"])
        existing = await db.device_collection_sessions.find_one(
            {"device_id": device_internal_id, "status": "active"})
        if existing:
            raise DeviceIngestionError(
                f"设备已有进行中的采集会话（{existing['_id']}），请先结束", 409)

        linkage_status = "none"
        linkage_error = None
        if plan_id or version_id or prescription_item_id:
            linkage_status, linkage_error = await self._verify_plan_linkage(
                db, patient_id, plan_id, version_id, prescription_item_id)

        session = {
            "_id": ObjectId(),
            "device_id": device_internal_id,
            "device_sn": device.get("device_id"),
            "patient_id": patient_id,
            "status": "active",
            "plan_id": plan_id,
            "version_id": version_id,
            "prescription_item_id": prescription_item_id,
            "linkage_status": linkage_status,
            "linkage_error": linkage_error,
            "started_at": datetime.utcnow(),
            "ended_at": None,
            "summary": {},
            "notes": notes,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }
        await db.device_collection_sessions.insert_one(session)
        # 会话期间设备标注在线采集状态（真实状态仍由心跳/上报维持）
        await db.devices.update_one(
            {"_id": ObjectId(device_internal_id)},
            {"$set": {"active_session_id": str(session["_id"]),
                      "updated_at": datetime.utcnow()}})
        session["_id"] = str(session["_id"])
        return session

    async def _verify_plan_linkage(
            self, db, patient_id: str, plan_id: Optional[str],
            version_id: Optional[str], prescription_item_id: Optional[str]
    ) -> Tuple[str, Optional[str]]:
        """Validate explicit patient, publication version, and stable item identity."""
        from .rehab_publication_service import WORKFLOW

        if not all((plan_id, version_id, prescription_item_id)):
            raise DeviceIngestionError(
                "关联新版方案时必须同时提供方案、已发布版本和处方项标识", 422)
        if not ObjectId.is_valid(plan_id) or not ObjectId.is_valid(version_id):
            raise DeviceIngestionError("方案或版本标识无效", 422)
        plan = await db.rehab_plans.find_one({
            "_id": ObjectId(plan_id), "patient_id": str(patient_id),
            "published_version_id": version_id,
        })
        if not plan or plan.get("status") in {"cancelled", "canceled", "archived"}:
            raise DeviceIngestionError("未找到该患者当前可见的已发布方案", 404)
        version = await db.rehab_plan_versions.find_one({
            "_id": ObjectId(version_id), "plan_id": plan_id,
            "patient_id": str(patient_id), "workflow": WORKFLOW,
            "status": "published",
        })
        if not version:
            raise DeviceIngestionError("处方项不属于该患者当前已发布方案版本", 404)
        items_snapshot = version.get("items_snapshot")
        if not isinstance(items_snapshot, list) or len(items_snapshot) > 200:
            raise DeviceIngestionError("已发布处方快照异常，无法安全关联设备", 503)
        matched = any(
            isinstance(item, dict)
            and item.get("item_id") == prescription_item_id
            and item.get("intervention_type") == "exercise"
            for item in items_snapshot
        )
        if not matched:
            raise DeviceIngestionError("处方项不属于该患者当前已发布方案版本", 404)
        return ("linked", None)

    async def end_collection_session(
        self, device: Dict[str, Any], session_id: str, *,
        cancel: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """结束采集会话：写设备观测摘要并解除设备在线采集标注。

        设备会话及其遥测保存在设备域；它不代表患者确认完成康复训练，
        因此不会写入康复训练进度。
        """
        db = await self._database()
        device_internal_id = str(device["_id"])
        if not ObjectId.is_valid(session_id):
            return None
        session = await db.device_collection_sessions.find_one(
            {"_id": ObjectId(session_id),
             "device_id": device_internal_id})
        if not session or session.get("status") != "active":
            return None

        ended_at = datetime.utcnow()
        window_query = {
            "device_id": device_internal_id,
            "metadata.session_id": session_id,
            "metadata.source": {"$in": [SOURCE_AUTOMATED,
                                        SOURCE_AUTOMATED_SIMULATED,
                                        SOURCE_VEEPOO_WECHAT]},
            "timestamp": {"$gte": session["started_at"], "$lte": ended_at},
        }
        session_docs = await db.device_data.find(window_query).to_list(None)
        flag_counter: Dict[str, int] = {}
        for d in session_docs:
            for flag in d.get("quality_flags") or []:
                flag_counter[flag] = flag_counter.get(flag, 0) + 1
        summary = {
            "readings_count": len(session_docs),
            "flagged_count": sum(
                1 for d in session_docs if d.get("quality_flags")),
            "flags": flag_counter,
            "ended_as": "cancelled" if cancel else "ended",
        }

        await db.device_collection_sessions.update_one(
            {"_id": ObjectId(session_id)},
            {"$set": {"status": "cancelled" if cancel else "ended",
                      "ended_at": ended_at, "summary": summary,
                      "updated_at": datetime.utcnow()}})
        await db.devices.update_one(
            {"_id": ObjectId(device_internal_id),
             "active_session_id": session_id},
            {"$unset": {"active_session_id": ""}})
        session["status"] = "cancelled" if cancel else "ended"
        session["ended_at"] = ended_at
        session["summary"] = summary
        session["_id"] = session_id
        return session

    async def list_collection_sessions(
        self, device_id: str, limit: int = 50,
    ) -> List[Dict[str, Any]]:
        db = await self._database()
        docs = await db.device_collection_sessions.find(
            {"device_id": device_id}).sort(
            "started_at", -1).limit(limit).to_list(limit)
        for doc in docs:
            doc["_id"] = str(doc["_id"])
        return docs

    # ── 模拟回放（仅测试/演示）──────────────────────────────────────────
    async def replay_simulated(
        self, device: Dict[str, Any], frame_count: int = 4,
        *, base_time: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """端到端演示入口：固定帧 → 完整网关管道（标记 simulated）。

        与真实上报唯一差异是 metadata.source；质量校验、幂等、分析链
        完全一致，确保演示路径即真实路径。
        """
        replayer = JMD540SimulatedReplayer()
        parsed_frames = replayer.replay(
            frame_count=frame_count, base_time=base_time,
            device_sn=device.get("device_id"))
        return await self._process_parsed_frames(
            device, parsed_frames, source=SOURCE_AUTOMATED_SIMULATED)

    # ── 网关凭证管理 ────────────────────────────────────────────────────
    @staticmethod
    def generate_device_key() -> str:
        """生成设备网关凭证（secrets，非随机数据冒充采集，与 REM02 无关）。"""
        return secrets.token_urlsafe(32)


device_ingestion_service = DeviceIngestionService()

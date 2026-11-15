"""设备数据接入网关服务（T74 真实设备接入软件侧框架）

链路：设备采集端 → 网关端点(device_router /gateway/*) → 设备凭证鉴权
→ DeviceProtocolAdapter.parse（device_protocol 包，按型号选择适配器）
→ 质量校验管道（本服务，入库前）→ device_data 增量写入（来源 automated、
原始载荷留存 metadata.raw_payload）→ 触发既有分析/预警链
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
        self, device_internal_id: str, *, battery_level: Optional[float] = None,
        session=None) -> None:
        """真实上报/心跳到达 → 更新 last_connected（及可选的真实上报电量）。

        仅记录真实发生的连接；无上报路径的字段保持 None（去模拟化口径）。
        """
        db = await self._database()
        update: Dict[str, Any] = {"last_connected": datetime.utcnow(),
                                  "updated_at": datetime.utcnow()}
        if battery_level is not None:
            update["battery_level"] = battery_level
        await db.devices.update_one(
            {"_id": ObjectId(device_internal_id)},
            {"$set": update}, **({"session": session} if session else {}))

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
            timestamp: datetime) -> bool:
        """幂等：device_id + timestamp + data_type 已存在即重复。"""
        existing = await db.device_data.find_one({
            "device_id": device_internal_id,
            "data_type": data_type,
            "timestamp": timestamp,
        })
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

    async def _process_parsed_frames(
        self, device: Dict[str, Any], parsed_frames, *, source: str,
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
            {"device_id": device_internal_id}
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
                    frame_index, in_batch_seen)
                if outcome["action"] == "written":
                    ts = outcome["timestamp"]
                    if latest_ts is None or ts > latest_ts:
                        latest_ts = ts
                results.append(outcome)

        # 真实到达：刷新连接状态（电量仅用报文自带的真值）
        await self._touch_device(device_internal_id,
                                 battery_level=battery_seen)
        alerts = await self._trigger_analysis(device_internal_id)
        return self._ingest_response(device, results, rejected, alerts=alerts)

    async def _process_reading(
        self, db, device_internal_id: str, patient_id: Optional[str],
        reading, config: Dict[str, Any], latest_ts: Optional[datetime],
        session_id: Optional[str], source: str, frame_index: int,
        in_batch_seen: set,
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

        dedup_key = (device_internal_id, data_type, ts)
        if dedup_key in in_batch_seen:
            return self._outcome("duplicate", frame_index, data_type, ts,
                                 reason="同批次内重复读数")
        if await self._is_duplicate(db, device_internal_id, data_type, ts):
            in_batch_seen.add(dedup_key)
            return self._outcome("duplicate", frame_index, data_type, ts,
                                 reason="库内已存在相同 device_id+时间戳+指标")

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
        await db.device_data.insert_one(document)
        in_batch_seen.add(dedup_key)
        return self._outcome("written", frame_index, data_type, ts,
                             quality_flags=flags)

    @staticmethod
    def _outcome(action: str, frame_index: int, data_type: str,
                 timestamp: datetime, *, reason: str = "",
                 error: str = "",
                 quality_flags: Optional[List[str]] = None) -> Dict[str, Any]:
        return {
            "action": action,  # written / duplicate / rejected
            "frame_index": frame_index,
            "data_type": data_type,
            "timestamp": timestamp,
            "quality_flags": quality_flags or [],
            "reason": reason,
            "error": error,
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
        await self._touch_device(device_internal_id)
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
        exercise_id: Optional[str] = None, notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """开始采集会话：关联患者与（可选）康复方案执行项。

        方案执行关联（T74 探查结论）：rehabilitation_service 的真实进度
        写入路径是 rehab_plans.exercises[].progress[]（log_exercise_progress），
        可关联——plan_id+exercise_id 均核实存在 → linkage=linked；仅登记
        （未核实）→ linkage=registered；未提供 → none。
        """
        db = await self._database()
        device_internal_id = str(device["_id"])
        existing = await db.device_collection_sessions.find_one(
            {"device_id": device_internal_id, "status": "active"})
        if existing:
            raise DeviceIngestionError(
                f"设备已有进行中的采集会话（{existing['_id']}），请先结束", 409)

        linkage_status = "none"
        linkage_error = None
        if plan_id or exercise_id:
            linkage_status, linkage_error = await self._verify_plan_linkage(
                db, plan_id, exercise_id)

        session = {
            "_id": ObjectId(),
            "device_id": device_internal_id,
            "device_sn": device.get("device_id"),
            "patient_id": patient_id,
            "status": "active",
            "plan_id": plan_id,
            "exercise_id": exercise_id,
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
            self, db, plan_id: Optional[str],
            exercise_id: Optional[str]) -> Tuple[str, Optional[str]]:
        """核实康复方案执行项存在性；失败降级为 registered（登记待人工）。"""
        if not plan_id or not exercise_id:
            return ("registered", "方案/运动项标识不完整，仅登记不关联")
        if not ObjectId.is_valid(plan_id):
            return ("registered", f"plan_id 非法: {plan_id}")
        plan = await db.rehab_plans.find_one({"_id": ObjectId(plan_id)})
        if not plan:
            return ("registered", f"康复方案不存在: {plan_id}")
        exercises = plan.get("exercises") or []
        matched = any(
            ex.get("id") == exercise_id or ex.get("name") == exercise_id
            for ex in exercises if isinstance(ex, dict))
        if not matched:
            return ("registered", f"方案内未找到运动项: {exercise_id}")
        return ("linked", None)

    async def end_collection_session(
        self, device: Dict[str, Any], session_id: str, *,
        cancel: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """结束采集会话：写摘要（读数/质量计数），解除设备在线采集标注，
        并把会话执行情况登记进关联的康复方案执行进度（linked 时）。"""
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
            "metadata.source": {"$in": [SOURCE_AUTOMATED,
                                        SOURCE_AUTOMATED_SIMULATED]},
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

        progress_logged = False
        progress_error = None
        if session.get("linkage_status") == "linked":
            progress_logged, progress_error = await self._log_rehab_progress(
                db, session, summary)
        summary["rehab_progress_logged"] = progress_logged
        if progress_error:
            summary["rehab_progress_error"] = progress_error

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

    async def _log_rehab_progress(
            self, db, session: Dict[str, Any],
            summary: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """把会话执行登记进 rehab_plans.exercises[].progress[]（打通点）。

        completed=False：设备会话完成≠患者确认完成该训练，不替患者
        虚报完成状态；进度条目 notes 如实注明"设备采集会话"来源。
        """
        try:
            from .rehabilitation_service import RehabilitationService
            rehab = RehabilitationService(db)
            result = await rehab.log_exercise_progress(
                session["plan_id"], session["exercise_id"], completed=False,
                notes=(f"设备采集会话完成，自动读数 "
                       f"{summary.get('readings_count', 0)} 条"
                       f"（来源：自动采集，未确认为训练完成）"))
            # log_exercise_progress：找不到运动项返回 {"error": ...} 而非 None
            ok = isinstance(result, dict) and "error" not in result
            return (ok, None if ok else str(result.get("error")))
        except Exception as exc:
            return (False, f"康复进度登记失败: {exc}")

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

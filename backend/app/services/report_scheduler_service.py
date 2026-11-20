"""Report schedule CRUD and real analytics snapshot generation.

The background scanner lives in report_scheduler_runtime and only claims schedules
explicitly created with executionVersion=1. Legacy records remain CRUD-visible but
cannot be executed. Artifacts are stored for authenticated in-app download; this
service performs no email or other external delivery.
"""
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta, timezone
import calendar
import re
import logging
from bson import ObjectId
from html import escape
import hashlib

from ..db.mongodb import get_db
from ..patients.repository import PATIENTS as CANONICAL_PATIENTS_COLLECTION
from .analytics_service import observe_patient_domain_state
from .analytics_service import AnalyticsService

# 患者域唯一集合名（legacy 模式：患者统一存于 users 集合，按 role 区分）。
# T66 域感知：legacy 分支仍读此常量（users + role 过滤，口径逐字不变）；
# canonical 分支改读 clinical_patients（集合名取自 patients/repository.py
# 的 PATIENTS 常量），按域分派见 _get_patient_stats。
PATIENTS_COLLECTION_NAME = "users"

# canonical 域患者聚合源：clinical_patients（与 analytics_service 同源
# patients/repository.PATIENTS 常量）；status=="active" 对齐 legacy
# users.is_active 语义（迁移映射见 patients/migration.project_legacy_patient）。
CANONICAL_PATIENTS_COLLECTION_NAME = CANONICAL_PATIENTS_COLLECTION

# 患者聚合源按域分派：mode -> (集合名, 过滤条件)。
# 口径差异声明（T12 审计）：legacy created_at = 账号注册时间；canonical 的
# created_at 对迁移患者继承 legacy 注册时间、对无账号患者（create_from_source）
# 是建档时间——「日新增患者」跨域不可比，域切换瞬间序列存在口径漂移（已知限制）。
_PATIENT_AGGREGATE_SPECS = {
    "legacy": (PATIENTS_COLLECTION_NAME, {"role": "patient"}),
    "canonical": (CANONICAL_PATIENTS_COLLECTION_NAME, {"status": "active"}),
}

logger = logging.getLogger(__name__)

REPORTS = {
    "overview",
    *(f"{kind}:{entity}" for kind, entities in {
        "trend": ("patient", "doctor", "device", "rehabilitation"),
        "distribution": ("patient", "doctor", "device", "rehabilitation", "region"),
        "comparison": ("patient", "doctor", "device", "rehabilitation"),
    }.items() for entity in entities),
}
TIME_RANGES = {"day", "week", "month", "quarter", "year"}

OVERVIEW_METRICS = {
    "patientCount": ("患者总数", ""),
    "weekPatientChange": ("近一周患者变化", "%"),
    "doctorCount": ("医生总数", ""),
    "totalDevices": ("设备总数", ""),
    "activeDeviceRate": ("活跃设备占比", "%"),
    "avgTrainingTime": ("平均训练时长", " 分钟"),
    "rehabilitationRate": ("康复有效率", "%"),
    "patientSatisfaction": ("患者满意度", "%"),
}

REPORT_TABLES = {
    "trend": (("timestamp", "统计时间（UTC）"), ("value", "新增数量")),
    "distribution": (("category", "类别"), ("value", "数量")),
    "comparison": (("category", "指标"), ("currentValue", "本期新增"), ("compareValue", "上期新增")),
}

class ReportSchedulerService:
    """Request-scoped CRUD, analytics generation and in-app artifact access."""

    def __init__(self, db=None):
        """初始化报表调度服务"""
        self.db = db

    @staticmethod
    def occurrence_key(schedule_id, occurrence):
        return hashlib.sha256(f"{schedule_id}:{occurrence.isoformat()}".encode("utf-8")).hexdigest()

    @staticmethod
    def _next_occurrence(schedule: Dict[str, Any], now: Optional[datetime] = None) -> Optional[datetime]:
        now = now or datetime.utcnow()
        frequency = schedule.get("frequency")
        if frequency == "once":
            return None
        time = schedule.get("time", "00:00")
        if not isinstance(time, str) or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", time):
            raise ValueError("执行时间必须为 HH:MM")
        hour, minute = map(int, time.split(":"))
        candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if frequency == "daily":
            return candidate if candidate > now else candidate + timedelta(days=1)
        if frequency == "weekly":
            weekday = schedule.get("weekday", 0)
            if not isinstance(weekday, int) or not 0 <= weekday <= 6:
                raise ValueError("weekday 必须介于 0 到 6")
            days = (weekday - ((now.weekday() + 1) % 7)) % 7
            candidate += timedelta(days=days)
            return candidate if candidate > now else candidate + timedelta(days=7)
        if frequency == "monthly":
            day = schedule.get("monthDay", 1)
            if not isinstance(day, int) or not 1 <= day <= 31:
                raise ValueError("monthDay 必须介于 1 到 31")
            candidate = candidate.replace(day=min(day, calendar.monthrange(candidate.year, candidate.month)[1]))
            if candidate <= now:
                month = candidate.month + 1
                year = candidate.year + (month - 1) // 12
                month = (month - 1) % 12 + 1
                candidate = candidate.replace(year=year, month=month,
                    day=min(day, calendar.monthrange(year, month)[1]))
            return candidate
        raise ValueError("frequency 必须为 once、daily、weekly 或 monthly")

    async def _database(self):
        """Use the request database when injected; retain standalone lifecycle support."""
        if self.db is None:
            self.db = await get_db()
        return self.db

    async def _validate_operational_schedule(self, schedule):
        if not (schedule.get("name") or "").strip() or len(schedule["name"]) > 120:
            raise ValueError("计划名称须为 1 至 120 个字符")
        if not isinstance(schedule.get("enabled", True), bool):
            raise ValueError("请指定有效的启用状态")
        if schedule.get("reportId") not in REPORTS:
            raise ValueError("不支持该报表类型")
        if schedule.get("format") != "html":
            raise ValueError("目前仅支持 HTML 报表")
        if schedule.get("timeRange", "month") not in TIME_RANGES:
            raise ValueError("不支持该统计周期")
        recipients = schedule.get("recipients") or []
        if (not recipients or len(set(recipients)) != len(recipients)
                or any(not ObjectId.is_valid(item) for item in recipients)):
            raise ValueError("收件人必须是至少一个有效的系统账号 ID")
        schedule["recipients"] = list(dict.fromkeys(str(ObjectId(item)) for item in recipients))
        creator_id = schedule.get("createdBy", "")
        if not ObjectId.is_valid(creator_id):
            raise ValueError("当前账号无权创建全局分析报表")
        account_ids = [ObjectId(item) for item in recipients]
        users = await self.db.users.find(
            {"_id": {"$in": account_ids}, "role": {"$in": ["admin", "doctor"]},
             "is_active": {"$ne": False}}, {"_id": 1}).to_list(length=None)
        if {str(row["_id"]) for row in users} != {str(item) for item in account_ids}:
            raise ValueError("报表收件人必须是有效的管理员或医生账号")
        creator = await self.db.users.find_one({"_id": ObjectId(creator_id),
            "role": {"$in": ["admin", "doctor"]}, "is_active": {"$ne": False}}, {"_id": 1})
        if not creator:
            raise ValueError("当前账号无权创建全局分析报表")
        if schedule.get("frequency") == "once":
            if not isinstance(schedule.get("nextRunTime"), datetime):
                raise ValueError("一次性计划必须提供 nextRunTime")
        else:
            self._next_occurrence(schedule)

    async def execute_claimed_schedule(self, schedule: Dict[str, Any], occurrence: datetime):
        """Generate and persist one in-app report, idempotently per scheduled occurrence."""
        report_id = schedule.get("reportId", "")
        report_name = schedule.get("reportName") or schedule.get("name") or report_id
        report_data = await self._generate_supported_report(
            report_id, schedule.get("timeRange", "month"))
        generated_at = datetime.now(timezone.utc)
        html = self._render_html(report_name, report_data, generated_at)
        occurrence_key = self.occurrence_key(schedule["_id"], occurrence)
        document = {
            "_id": occurrence_key,
            "scheduleId": str(schedule["_id"]),
            "createdBy": str(schedule.get("createdBy", "")),
            "recipientIds": list(schedule.get("recipients", [])),
            "reportId": report_id,
            "reportName": report_name,
            "generatedAt": generated_at,
            "scheduledFor": occurrence,
            "status": "success",
            "format": "html",
            "html": html,
            "data": report_data,
        }
        try:
            await self.db.report_schedule_runs.insert_one(document)
        except Exception as exc:
            # Duplicate-key means a previous lease holder already committed the artifact.
            if getattr(exc, "code", None) != 11000:
                raise
        return occurrence_key

    async def _generate_supported_report(self, report_id: str, time_range: str) -> Dict[str, Any]:
        if report_id not in REPORTS:
            raise ValueError("不支持该报表类型")
        if time_range not in TIME_RANGES:
            raise ValueError("不支持该统计周期")
        analytics = AnalyticsService(self.db)
        if report_id == "overview":
            metrics = await analytics.get_stats_overview()
            unavailable = {field: None for field, available in metrics.get("dataAvailable", {}).items()
                           if available is False}
            return {"kind": "overview", "data": {**metrics, **unavailable}}
        kind, data_type = report_id.split(":", 1)
        if kind == "trend":
            rows = await analytics.get_trend_data(data_type, time_range)
        elif kind == "distribution":
            rows = await analytics.get_distribution_data(data_type, time_range)
        else:
            rows = await analytics.get_comparison_data(data_type, time_range, "lastPeriod")
        result = {"kind": kind, "dataType": data_type, "data": rows}
        if kind != "distribution":
            result["timeRange"] = time_range
        return result

    @staticmethod
    def _render_html(title: str, report_data: Dict[str, Any], generated_at: datetime) -> str:
        """Render a self-contained HTML artifact from the real analytics response."""
        kind, data = report_data["kind"], report_data["data"]
        if kind == "overview":
            headings = ("指标", "数值")
            rows = [(label, f"{data[key]}{unit}" if data.get(key) is not None else "暂无可用数据")
                    for key, (label, unit) in OVERVIEW_METRICS.items()]
        else:
            columns = REPORT_TABLES[kind]
            headings = tuple(label for _, label in columns)
            rows = [tuple(row.get(key) for key, _ in columns) for row in data]
        table = "<p>暂无可用数据。</p>"
        if rows:
            header = "".join(f"<th scope='col'>{escape(label)}</th>" for label in headings)
            body = "".join(
                "<tr>" + "".join(f"<td>{escape(str(cell) if cell is not None else '暂无可用数据')}</td>"
                                 for cell in row) + "</tr>" for row in rows)
            table = f"<table><thead><tr>{header}</tr></thead><tbody>{body}</tbody></table>"
        ranges = {"day": "近 1 天", "week": "近 7 天", "month": "近一月",
                  "quarter": "近一季", "year": "近一年"}
        period = ranges.get(report_data.get("timeRange"), "生成时的业务概况")
        generated = generated_at.strftime("%Y-%m-%d %H:%M:%S UTC")
        safe_title = escape(title)
        return (
            "<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>{safe_title}</title>"
            "<style>body{margin:2rem auto;padding:0 1rem;max-width:56rem;"
            "font:1rem/1.55 system-ui,sans-serif;color:#152238}table{width:100%;border-collapse:collapse}"
            "th,td{padding:.5rem .7rem;text-align:left;border-bottom:1px solid #dbe2ec}"
            "th{background:#eef3f9}tbody tr:nth-child(even){background:#f8fafd}</style></head>"
            f"<body><h1>{safe_title}</h1><p>生成时间 {generated} · {period}</p>{table}</body></html>"
        )
    
    async def _get_chart_data(self, chart_type: str, data_type: str, time_range: str) -> List[Dict[str, Any]]:
        """获取图表数据"""
        # 这里应该根据不同的数据类型调用相应的服务获取数据
        # 下面是一个示例实现
        
        days = self._time_range_to_days(time_range)
        
        if data_type == "patient":
            # 获取患者相关数据
            return await self._get_patient_stats(days)
        elif data_type == "device":
            # 获取设备相关数据
            return await self._get_device_stats(days)
        else:
            # 默认返回空数据
            return []
    
    def _time_range_to_days(self, time_range: str) -> int:
        """将时间范围转换为天数"""
        if time_range == "day":
            return 1
        elif time_range == "week":
            return 7
        elif time_range == "month":
            return 30
        elif time_range == "quarter":
            return 90
        elif time_range == "year":
            return 365
        else:
            return 30  # 默认为一个月
    
    async def _get_patient_stats(self, days: int) -> List[Dict[str, Any]]:
        """获取患者统计数据（患者聚合源按域分派，T66）。

        legacy：users + role=="patient"（原有管道逐字保留）；canonical：
        clinical_patients + status=="active"（含无账号患者）。created_at
        口径差异与域切换瞬间漂移见 _PATIENT_AGGREGATE_SPECS 注释。

        域状态读取失败/未知状态 fail-safe 返回 []（不猜测域，与
        analytics_service.observe_patient_domain_state 的 unknown 口径一致；
        纯列表响应无 unknown 通道，空序列与"无数据"不可区分属已知限制）。
        """
        mode = await observe_patient_domain_state(self.db)
        spec = _PATIENT_AGGREGATE_SPECS.get(mode)
        if spec is None:
            return []

        collection_name, match = spec
        start_date = datetime.utcnow() - timedelta(days=days)

        pipeline = [
            # 患者聚合源按域分派（legacy: PATIENTS_COLLECTION_NAME=users；
            # canonical: clinical_patients，见 _PATIENT_AGGREGATE_SPECS），
            # 聚合语义（按天分桶计数）不变
            {"$match": {**match, "created_at": {"$gte": start_date}}},
            {"$group": {
                "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$created_at"}},
                "count": {"$sum": 1}
            }},
            {"$sort": {"_id": 1}}
        ]

        result = []
        async for doc in self.db[collection_name].aggregate(pipeline):
            result.append({
                "date": doc["_id"],
                "value": doc["count"]
            })
        
        return result
    
    async def _get_device_stats(self, days: int) -> List[Dict[str, Any]]:
        """获取设备统计数据"""
        start_date = datetime.utcnow() - timedelta(days=days)
        
        pipeline = [
            {"$match": {"timestamp": {"$gte": start_date}}},
            {"$group": {
                "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$timestamp"}},
                "count": {"$sum": 1},
                "avg_value": {"$avg": "$value"}
            }},
            {"$sort": {"_id": 1}}
        ]
        
        result = []
        async for doc in self.db.device_data.aggregate(pipeline):
            result.append({
                "date": doc["_id"],
                "count": doc["count"],
                "average": doc["avg_value"]
            })
        
        return result
    
    async def create_schedule(self, schedule_data: Dict[str, Any]) -> str:
        """创建新的报表调度计划"""
        await self._database()
        schedule_data["timeRange"] = schedule_data.get("timeRange", "month")
        await self._validate_operational_schedule(schedule_data)
        # 设置创建时间
        schedule_data["createdAt"] = datetime.utcnow()
        schedule_data["executionVersion"] = 1
        schedule_data["retryCount"] = 0
        schedule_data["nextRunTime"] = (schedule_data["nextRunTime"] if schedule_data.get("frequency") == "once"
                                         else self._next_occurrence(schedule_data))
        # 插入记录
        result = await self.db.report_schedules.insert_one(schedule_data)
        return str(result.inserted_id)

    async def get_runs(self, user_id: str, limit: int = 20, skip: int = 0):
        await self._database()
        query = {"$or": [{"createdBy": user_id}, {"recipientIds": user_id}]}
        rows = await self.db.report_schedule_runs.find(query, {
            "html": 0, "data": 0,
        }).sort("generatedAt", -1).skip(skip).limit(limit).to_list(length=limit)
        return {"items": [self._public_run(row) for row in rows],
                "total": await self.db.report_schedule_runs.count_documents(query)}

    async def get_run(self, run_id: str, user_id: str):
        await self._database()
        row = await self.db.report_schedule_runs.find_one({
            "_id": run_id, "$or": [{"createdBy": user_id}, {"recipientIds": user_id}],
        })
        return self._public_run(row, include_artifact=True) if row else None

    @staticmethod
    def _public_run(row, include_artifact=False):
        if not row:
            return None
        def utc(value):
            if not isinstance(value, datetime):
                return value
            return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
        result = {
            "id": str(row["_id"]), "scheduleId": row.get("scheduleId"),
            "reportId": row.get("reportId"), "reportName": row.get("reportName"),
            "generatedAt": utc(row.get("generatedAt")), "scheduledFor": utc(row.get("scheduledFor")),
            "status": row.get("status"), "format": row.get("format"),
        }
        if include_artifact:
            result.update(html=row.get("html", ""), data=row.get("data", {}))
        return result
    
    async def update_schedule(self, schedule_id: str, schedule_data: Dict[str, Any]) -> bool:
        """更新报表调度计划"""
        await self._database()
        if not ObjectId.is_valid(schedule_id):
            return False
        for field in ["_id", "createdAt", "createdBy", "lastRunTime", "lastRunStatus",
                      "executionVersion", "retryCount", "claimId", "leaseUntil"]:
            schedule_data.pop(field, None)
        current_schedule = await self.db.report_schedules.find_one({"_id": ObjectId(schedule_id)})
        if not current_schedule:
            return False
        updated_schedule = {**current_schedule, **schedule_data}
        operational = current_schedule.get("executionVersion") == 1
        if operational:
            await self._validate_operational_schedule(updated_schedule)
            if "recipients" in schedule_data:
                schedule_data["recipients"] = updated_schedule["recipients"]

        frequency_fields = ["frequency", "weekday", "monthDay", "time", "nextRunTime"]
        needs_update_next_run = any(field in schedule_data for field in frequency_fields)
        if operational and needs_update_next_run:
            if updated_schedule.get("frequency") == "once":
                if not isinstance(updated_schedule.get("nextRunTime"), datetime):
                    raise ValueError("一次性计划必须提供 nextRunTime")
                schedule_data["nextRunTime"] = updated_schedule["nextRunTime"]
            else:
                schedule_data["nextRunTime"] = self._next_occurrence(updated_schedule)
            schedule_data["retryCount"] = 0
        elif not operational and needs_update_next_run:
            # Preserve legacy record behavior without making it executable.
            if updated_schedule.get("frequency") == "once":
                schedule_data.setdefault("nextRunTime", datetime.utcnow())
            else:
                schedule_data["nextRunTime"] = self._next_occurrence(updated_schedule)
        schedule_data["updatedAt"] = datetime.utcnow()
        query = {"_id": ObjectId(schedule_id)}
        if operational:
            # The worker and editor race on one document: whichever writes first wins.
            # Editing a claimed row fails; an edit committed first changes its due
            # fields before the worker's atomic due filter can claim it.
            query.update(executionVersion=1, claimId={"$exists": False})
        update = {"$set": schedule_data}
        if operational and needs_update_next_run:
            update["$unset"] = {"nextAttemptAt": "", "lastRunError": ""}
        result = await self.db.report_schedules.update_one(
            query, update
        )
        return result.modified_count > 0
    
    async def delete_schedule(self, schedule_id: str) -> bool:
        """删除报表调度计划"""
        await self._database()
        query = {"_id": ObjectId(schedule_id)}
        row = await self.db.report_schedules.find_one(query, {"executionVersion": 1})
        if row and row.get("executionVersion") == 1:
            query["claimId"] = {"$exists": False}
        result = await self.db.report_schedules.delete_one(query)
        return result.deleted_count > 0
    
    async def get_schedule(self, schedule_id: str) -> Optional[Dict[str, Any]]:
        """获取单个报表调度计划"""
        await self._database()
        if not ObjectId.is_valid(schedule_id):
            return None
        schedule = await self.db.report_schedules.find_one({"_id": ObjectId(schedule_id)})
        if schedule:
            schedule["_id"] = str(schedule["_id"])
        return schedule
    
    async def get_schedules(self, user_id: Optional[str] = None, report_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """获取报表调度计划列表"""
        await self._database()
        
        query = {}
        if user_id:
            query["createdBy"] = user_id
        if report_id:
            query["reportId"] = report_id
        
        schedules = []
        async for schedule in self.db.report_schedules.find(query).sort("createdAt", -1):
            schedule["_id"] = str(schedule["_id"])
            schedules.append(schedule)
        
        return schedules
    
    async def toggle_schedule(self, schedule_id: str, enabled: bool) -> bool:
        """启用或禁用报表调度计划"""
        await self._database()
        query = {"_id": ObjectId(schedule_id)}
        row = await self.db.report_schedules.find_one(query, {"executionVersion": 1, "frequency": 1, "nextRunTime": 1})
        if row and row.get("executionVersion") == 1:
            query["claimId"] = {"$exists": False}
            if enabled and row.get("frequency") == "once":
                if not isinstance(row.get("nextRunTime"), datetime):
                    raise ValueError("请先编辑一次性计划并设定新的执行时间")
                query["nextRunTime"] = {"$type": "date"}
        result = await self.db.report_schedules.update_one(
            query,
            {"$set": {"enabled": enabled}}
        )
        return result.matched_count > 0


# 创建服务实例
report_scheduler_service = ReportSchedulerService()

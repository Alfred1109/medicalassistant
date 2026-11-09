"""Authorized process monitoring over existing domain sources only."""
import asyncio
import csv
import io
from datetime import datetime, timezone

from bson import ObjectId
from app.core.exceptions import AppBaseException
from app.core.followup_access import followup_patient_scope
from app.core.patient_access import ensure_patient_access
from app.core.patient_identity import identity_key, load_identity_groups
from app.schemas.quality_monitoring import (
    FollowupProcessSummary, PlanProcessSummary, ProcessWindow,
    QualityProcessOverview, QualityProcessPage,
)
from app.services.followup_service import FollowupService
from app.services.rehab_publication_service import RehabPublicationService
from app.services.quality_process_queries import FOLLOWUP_STATUSES, PLAN_STATUSES, PUBLICATION_STATES


def _error(code, message, status=422):
    return AppBaseException(message, status_code=status, error_code=code)


def utc(value):
    if value is None:
        return None
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise _error("QUALITY_DATE_TIMEZONE_REQUIRED", "统计日期必须包含时区")
    return value.astimezone(timezone.utc)


def csv_safe(value):
    text = "" if value is None else str(value)
    # Spreadsheet programs also recognize formulas after leading whitespace.
    return "'" + text if text.lstrip().startswith(("=", "+", "-", "@", "\t", "\r", "\n")) or text.startswith(("\t", "\r", "\n")) else text


def process_csv(overview, patient_id):
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(["section", "metric", "value", "context"])
    rows = [
        ("report", "title", "康复过程统计报告", "仅过程事实，不含临床达标或ICF评分"),
        ("report", "generated_at", overview.generated_at.isoformat(), "统计生成时间"),
        ("scope", "patient_id", patient_id or "当前账号全部授权患者", "按当前患者权限查询"),
        ("scope", "start_date", overview.window.start_date.isoformat() if overview.window.start_date else "不限", "包含起点"),
        ("scope", "end_date", overview.window.end_date.isoformat() if overview.window.end_date else "不限", "不包含终点"),
        ("scope", "followup_date_field", "scheduled_date", "随访按计划时间筛选"),
        ("scope", "plan_date_field", "created_at", "方案按创建时间筛选，发布指标为当前状态，不是窗口内发布次数"),
        ("scope", "date_quality_scope", "当前完整源数据范围", "缺失和非日期数据不能归入日期窗口，单列计数；管理员全源可包含无法核实患者引用的记录"),
        ("scope", "scope_kind", overview.scope_kind, "管理员全源可包含孤儿记录；医护仅当前有效且获分配患者，停用或已解除分配者排除；身份歧义失败关闭"),
        ("scope", "read_consistency", overview.read_consistency, "两个来源分别实时读取，可能有时间差；生成时间不代表跨集合一致快照"),
        ("scope", "publication_validation", overview.publication_validation, "核对发布引用和必要结构，不保证全部嵌套值通过患者读取校验或具有临床效力"),
    ]
    for name in ("followups", "plans"):
        summary = getattr(overview, name)
        for key in ("selected_total", "scope_total", "missing_date_count", "invalid_date_count", "unresolved_patient_count"):
            rows.append((name, key, getattr(summary, key), ""))
        rows.extend((name, "status:" + item.status, item.count, "") for item in summary.by_status)
    rows.append(("followups", "in_review_count", overview.followups.in_review_count, "当前待医护审阅节点数"))
    rows.extend(("plans", "publication:" + item.state, item.count,
        "当前发布引用及必要结构已核对；不保证全部嵌套内容通过患者DTO校验或具临床效力" if item.state == "published" else "当前发布事实")
        for item in overview.plans.publication_states)
    for row in rows:
        writer.writerow([csv_safe(value) for value in row])
    return ("\ufeff" + stream.getvalue()).encode("utf-8")


class QualityMonitoringService:
    def __init__(self, db):
        self.db = db
        self.followups = FollowupService(db)
        self.publications = RehabPublicationService(db)

    async def scope(self, actor, patient_id=None):
        if actor.role not in {"doctor", "health_manager", "admin"}:
            raise _error("QUALITY_MEDICAL_ROLE_REQUIRED", "需要医护或管理员权限", 403)
        accounts = await load_identity_groups(self.db, [actor.id], projection={"role": 1, "is_active": 1})
        matches = accounts.get(identity_key(actor.id), [])
        if (len(matches) != 1 or matches[0].get("role") != actor.role
                or matches[0].get("is_active") is not True):
            raise _error("QUALITY_ACCOUNT_UNAVAILABLE", "当前账号身份不可唯一核实或已停用", 403)
        if await self.db.patient_domain_state.find_one({"_id": "clinical-patients-v1"}):
            raise _error("QUALITY_PATIENT_DOMAIN_UNSUPPORTED", "当前患者域尚未接入质控患者范围", 503)
        values = await followup_patient_scope(self.db, actor)
        if values is not None:
            field = "practitioners" if actor.role == "doctor" else "health_managers"
            grouped = await load_identity_groups(self.db, values,
                projection={"role": 1, "is_active": 1, field: 1})
            verified = []
            for identifier in values:
                matches = grouped.get(identity_key(identifier), [])
                if len(matches) > 1:
                    raise _error("QUALITY_PATIENT_SCOPE_UNVERIFIED", "患者身份存在歧义，请先核实范围", 503)
                document = matches[0] if len(matches) == 1 else None
                assignments = document.get(field) if document else None
                if (not document or document.get("role") != "patient" or document.get("is_active") is not True
                        or not isinstance(assignments, list) or str(actor.id) not in {str(item) for item in assignments}):
                    continue
                verified.append(str(document["_id"]))
            values = list(dict.fromkeys(verified))
        if patient_id:
            patient_id = str(ObjectId(patient_id)) if ObjectId.is_valid(patient_id) else patient_id
            await ensure_patient_access(self.db, patient_id, str(actor.id), actor.role)
            if actor.role == "admin":
                grouped = await load_identity_groups(self.db, [patient_id], projection={"role": 1, "is_active": 1})
                matches = grouped.get(identity_key(patient_id), [])
                if (len(matches) != 1 or matches[0].get("role") != "patient"
                        or matches[0].get("is_active") is not True):
                    raise _error("QUALITY_PATIENT_SCOPE_UNVERIFIED", "选定患者身份不可唯一核实，请先核实范围", 503)
                patient_id = str(matches[0]["_id"])
            if values is not None and patient_id not in values:
                raise _error("QUALITY_PATIENT_NOT_ASSIGNED", "无权访问该患者的过程统计", 403)
            return [patient_id]
        return values

    @staticmethod
    def dates(start_date=None, end_date=None):
        start, end = utc(start_date), utc(end_date)
        if start is not None and end is not None and start >= end:
            raise _error("QUALITY_DATE_RANGE", "结束时间必须晚于开始时间")
        return start, end

    async def _read(self, kind, scope, start, end, **options):
        source = self.followups if kind == "followup" else self.publications
        return await source.quality_process_snapshot(scope,
            start_date=start.replace(tzinfo=None) if start else None,
            end_date=end.replace(tzinfo=None) if end else None, **options)

    @staticmethod
    def summary(rows, known):
        counts = {row["_id"]: row["count"] for row in rows.get("statuses", [])}
        dates = {row["_id"]: row["count"] for row in rows.get("dates", [])}
        references = {row["_id"]: row["count"] for row in rows.get("patient_references", [])}
        return {"selected_total": (rows.get("total") or [{"count": 0}])[0]["count"],
            "scope_total": (rows.get("scope") or [{"count": 0}])[0]["count"],
            "missing_date_count": dates.get("missing", 0) + dates.get("null", 0),
            "invalid_date_count": sum(count for kind, count in dates.items() if kind not in {"date", "missing", "null"}),
            "unresolved_patient_count": sum(count for kind, count in references.items() if kind != "valid"),
            "by_status": [{"status": value, "count": counts.get(value, 0)} for value in (*known, "__unknown__", "__missing__", "__invalid__")]}

    async def overview(self, actor, *, patient_id=None, start_date=None, end_date=None):
        start, end = self.dates(start_date, end_date)
        scope = await self.scope(actor, patient_id)
        followup, plan = await asyncio.gather(self._read("followup", scope, start, end), self._read("rehab_plan", scope, start, end))
        followup_summary = self.summary(followup, FOLLOWUP_STATUSES)
        publication_counts = {row["_id"]: row["count"] for row in plan.get("publications", [])}
        return QualityProcessOverview(generated_at=datetime.now(timezone.utc),
            scope_kind="selected_patient" if patient_id else "all_source_records" if scope is None else "assigned_patients",
            window=ProcessWindow(start_date=start, end_date=end),
            followups=FollowupProcessSummary(**followup_summary,
                in_review_count=next(item["count"] for item in followup_summary["by_status"] if item["status"] == "in_review")),
            plans=PlanProcessSummary(**self.summary(plan, PLAN_STATUSES),
                publication_states=[{"state": state, "count": publication_counts.get(state, 0)} for state in PUBLICATION_STATES]))

    async def details(self, kind, actor, *, patient_id=None, start_date=None, end_date=None, skip=0, limit=20):
        if kind not in {"followup", "rehab_plan"} or skip < 0 or not 1 <= limit <= 100:
            raise _error("QUALITY_PAGINATION", "过程统计分页参数无效")
        start, end = self.dates(start_date, end_date)
        scope = await self.scope(actor, patient_id)
        rows = await self._read(kind, scope, start, end, skip=skip, limit=limit, include_items=True)
        items = rows.get("items", [])
        for item in items:
            if isinstance(item.get("date"), datetime):
                item["date"] = item["date"].replace(tzinfo=timezone.utc)
        return QualityProcessPage(items=items, total=(rows.get("total") or [{"count": 0}])[0]["count"],
            skip=skip, limit=limit, date_field="scheduled_date" if kind == "followup" else "created_at")

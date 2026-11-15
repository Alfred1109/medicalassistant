"""ICF 评估域服务（T71）。

职责：
1. ICF 类目字典（icf_categories，可配置集合）：内置一组康复常用默认类目，
   字典口径待临床确认，可后台维护（新增/停用/启停）。
2. ICF 结构化评估（icf_assessments）：患者、评估时间、各类目限定值 0-4 或
   定性、评估来源随访/方案/手工、评估人；review 沿用 clinical_reports 的
   pending/reviewed/rejected 状态语义（简化版：无 reviewed_snapshot 历史，
   修改内容即重置 pending，mutation_version CAS 防并发覆盖）。
3. 指标自动计算（icf_metric_configs 定义可配置）：从 icf_assessments 与
   随访记录计算改善幅度、达标率、随访完成率；阈值触发复用
   health_alert_service（health_data_alerts 集合；医护通知由该服务统一经
   NotificationService 产生），不重造。
4. 正式 ICF 报告（icf_reports）：按评估生成结构化报告，review 状态机与
   clinical_reports 一致；审核通过后方可导出（结构化 JSON + 打印友好 HTML）。

所有临床口径（类目、阈值、判定）均为可配置默认值，全部标注「待临床确认」。
对象级授权经内核 app.core.patient_access（本文件只 import，不改动内核）。
"""
from copy import deepcopy
from datetime import datetime, timezone
from html import escape
from typing import Any, Dict, List, Optional

from bson import ObjectId
from fastapi import HTTPException

from app.models.icf import (
    ICF_ASSESSMENT_SOURCES, ICF_DOMAINS, IcfAssessment, IcfCategory,
    IcfMetricConfig, IcfReport)
from app.schemas.health_data_threshold import AlertCreate
from app.services.health_alert_service import HealthAlertService
from app.services.review_state_machine import (
    append_review_history, check_review_version, commit_review, export_gate,
    review_event, review_note)

CLINICAL_ROLES = {"admin", "doctor", "health_manager"}

# ICF 预警在 health_data_alerts 中的 data_type 标识（供列表过滤与去重）
ICF_ALERT_DATA_TYPE = "icf_metric"

DICTIONARY_NOTE = "字典口径待临床确认，可后台维护。"
METRIC_NOTE = "指标定义与阈值为可配置默认口径，待临床确认。"
REPORT_DISCLAIMER = ("本报告由系统按可配置口径汇总生成，"
                     "类目字典、指标阈值与判定结论均待临床确认。")

# 内置默认 ICF 类目（康复常用类目；口径待临床确认，可后台维护）。
# domain 取值：body（身体功能）/ activity（活动）/ participation（参与）。
DEFAULT_ICF_CATEGORIES = [
    {"code": "b130", "name": "精力与驱力功能", "domain": "body"},
    {"code": "b152", "name": "情绪功能", "domain": "body"},
    {"code": "b164", "name": "高层次认知功能", "domain": "body"},
    {"code": "b167", "name": "语言功能", "domain": "body"},
    {"code": "b280", "name": "痛觉", "domain": "body"},
    {"code": "b455", "name": "运动耐受功能", "domain": "body"},
    {"code": "b710", "name": "关节活动功能", "domain": "body"},
    {"code": "b730", "name": "肌肉力量功能", "domain": "body"},
    {"code": "b760", "name": "随意运动控制功能", "domain": "body"},
    {"code": "d410", "name": "变换身体基本姿势", "domain": "activity"},
    {"code": "d420", "name": "移动自身", "domain": "activity"},
    {"code": "d450", "name": "步行", "domain": "activity"},
    {"code": "d455", "name": "到处移动", "domain": "activity"},
    {"code": "d510", "name": "盥洗自身", "domain": "activity"},
    {"code": "d540", "name": "穿衣", "domain": "activity"},
    {"code": "d550", "name": "吃", "domain": "activity"},
    {"code": "d640", "name": "做家务", "domain": "activity"},
    {"code": "d710", "name": "基本人际互动", "domain": "participation"},
    {"code": "d920", "name": "娱乐与休闲", "domain": "participation"},
]

# 内置默认指标定义（口径待临床确认，可后台维护）。
DEFAULT_METRIC_CONFIGS = [
    {
        "metric_key": "qualifier_improvement",
        "name": "类目限定值改善幅度",
        "description": "同一类目首次与最近一次数值限定值之差（正值=改善）；"
                       "改善幅度低于 min_improvement 触发预警。",
        "enabled": True,
        "params": {"min_improvement": 1},
    },
    {
        "metric_key": "attainment_rate",
        "name": "类目达标率",
        "description": "最近一次数值限定值不劣于 target_qualifier 的类目占比；"
                       "低于 min_rate 触发预警。",
        "enabled": True,
        "params": {"target_qualifier": 1, "min_rate": 0.6},
    },
    {
        "metric_key": "followup_completion_rate",
        "name": "随访完成率",
        "description": "非作废随访中 status=completed 的占比；低于 min_rate 触发预警。",
        "enabled": True,
        "params": {"min_rate": 0.8},
    },
]

_VOID_FOLLOWUP_STATUS = {"canceled", "cancelled", "void"}
_COMPLETED_FOLLOWUP_STATUS = {"completed", "done", "finished"}


def _now():
    return datetime.now(timezone.utc)


def _require_clinical(actor):
    if actor.role not in CLINICAL_ROLES:
        raise HTTPException(403, detail={"code": "ROLE_NOT_ALLOWED"})


async def _patient_for(db, actor, patient_id):
    """对象级授权：与 clinical/workspace 同源策略，经内核 ensure_patient_access。"""
    from app.core.patient_access import (
        ensure_patient_access, load_patient_doc, resolve_self_patient_id)
    if actor.role == "patient":
        identifier = resolve_self_patient_id(actor, patient_id)
        return await load_patient_doc(db, identifier)
    if actor.role not in CLINICAL_ROLES:
        raise HTTPException(403, detail={"code": "ROLE_NOT_ALLOWED"})
    if actor.role == "admin":
        return await load_patient_doc(db, patient_id)
    try:
        patient = await ensure_patient_access(db, patient_id, str(actor.id), actor.role)
    except Exception as exc:
        status_code = getattr(exc, "status_code", None)
        if status_code:
            raise HTTPException(status_code, detail={"code": getattr(exc, "error_code", "PATIENT_NOT_ASSIGNED"),
                                                     "message": str(exc)}) from None
        raise
    viewer = await db.users.find_one({"_id": ObjectId(str(actor.id))})
    patient_project = patient.get("source_project_id")
    viewer_project = (viewer or {}).get("source_project_id")
    if patient_project and viewer_project and patient_project != viewer_project:
        raise HTTPException(403, detail={"code": "DIFFERENT_PROJECT",
                                         "message": "患者与当前账号不属于同一个来源项目"})
    return patient


# ------------------------------------------------------------------
# ICF 类目字典（可配置集合）
# ------------------------------------------------------------------

async def ensure_default_categories(db):
    """幂等播种内置默认字典；已有任何类目（含已停用）时不重复播种。"""
    existing = await db.icf_categories.find_one({})
    if existing:
        return {"seeded": False, "count": 0}
    now = _now()
    documents = [IcfCategory(code=item["code"], name=item["name"], domain=item["domain"],
                             description=item["name"], enabled=True, source="builtin",
                             created_at=now, updated_at=now,
                             metadata={"note": DICTIONARY_NOTE}).to_mongo()
                 for item in DEFAULT_ICF_CATEGORIES]
    if documents:
        await db.icf_categories.insert_many(documents)
    return {"seeded": True, "count": len(documents)}


async def list_categories(db, actor):
    await ensure_default_categories(db)
    rows = [IcfCategory.from_mongo(doc) async for doc in
            db.icf_categories.find({}).sort("code", 1)]
    return {"categories": [_category_public(row) for row in rows if row is not None],
            "note": DICTIONARY_NOTE}


def _category_public(row):
    return {"id": str(row._id), "code": row.code, "name": row.name, "domain": row.domain,
            "description": row.description, "enabled": bool(row.enabled), "source": row.source,
            "note": DICTIONARY_NOTE}


async def create_category(db, actor, *, code, name, domain, description=""):
    _require_clinical(actor)
    code, name = code.strip().lower(), name.strip()
    description = (description or "").strip()
    if not code or len(code) > 20 or not name or len(name) > 80 or len(description) > 500:
        raise HTTPException(422, detail={"code": "INVALID_CATEGORY"})
    if domain not in ICF_DOMAINS:
        raise HTTPException(422, detail={"code": "INVALID_ICF_DOMAIN"})
    existing = await db.icf_categories.find_one({"code": code})
    if existing:
        raise HTTPException(409, detail={"code": "ICF_CATEGORY_EXISTS"})
    document = IcfCategory(code=code, name=name, domain=domain, description=description,
                           enabled=True, source="custom", created_by=str(actor.id),
                           metadata={"note": DICTIONARY_NOTE})
    await db.icf_categories.insert_one(document.to_mongo())
    return _category_public(document)


async def update_category(db, actor, category_id, *, name=None, domain=None,
                          description=None, enabled=None):
    _require_clinical(actor)
    if not ObjectId.is_valid(category_id):
        raise HTTPException(422, detail={"code": "INVALID_CATEGORY_ID"})
    row = await db.icf_categories.find_one({"_id": ObjectId(category_id)})
    if not row:
        raise HTTPException(404, detail={"code": "ICF_CATEGORY_NOT_FOUND"})
    update = {"updated_at": _now(), "updated_by": str(actor.id)}
    if name is not None:
        name = name.strip()
        if not name or len(name) > 80:
            raise HTTPException(422, detail={"code": "INVALID_CATEGORY"})
        update["name"] = name
    if domain is not None:
        if domain not in ICF_DOMAINS:
            raise HTTPException(422, detail={"code": "INVALID_ICF_DOMAIN"})
        update["domain"] = domain
    if description is not None:
        description = description.strip()
        if len(description) > 500:
            raise HTTPException(422, detail={"code": "INVALID_CATEGORY"})
        update["description"] = description
    if enabled is not None:
        update["enabled"] = bool(enabled)
    await db.icf_categories.update_one({"_id": ObjectId(category_id)}, {"$set": update})
    return {"id": category_id, **{key: value for key, value in update.items()
                                  if key not in {"updated_at", "updated_by"}},
            "updated": True}


# ------------------------------------------------------------------
# ICF 结构化评估
# ------------------------------------------------------------------

def _normalize_item(item, category_by_code):
    if not isinstance(item, dict):
        raise HTTPException(422, detail={"code": "INVALID_ICF_ITEM"})
    code = str(item.get("code") or "").strip().lower()
    category = category_by_code.get(code)
    if not category:
        raise HTTPException(422, detail={"code": "ICF_CODE_NOT_IN_DICTIONARY",
                                         "message": f"类目编码 {code} 不在启用字典中"})
    if not category.get("enabled", True):
        raise HTTPException(422, detail={"code": "ICF_CODE_DISABLED",
                                         "message": f"类目编码 {code} 已停用"})
    qualifier = item.get("qualifier")
    note = str(item.get("note") or "").strip()
    if len(note) > 500:
        raise HTTPException(422, detail={"code": "INVALID_ICF_ITEM"})
    if isinstance(qualifier, bool):
        raise HTTPException(422, detail={"code": "INVALID_ICF_QUALIFIER"})
    if isinstance(qualifier, int) and 0 <= qualifier <= 4:
        kind = "numeric"
    elif isinstance(qualifier, str) and qualifier.strip() and len(qualifier.strip()) <= 20:
        qualifier = qualifier.strip()
        kind = "text"
    else:
        raise HTTPException(422, detail={"code": "INVALID_ICF_QUALIFIER"})
    return {"code": code, "name": category["name"], "domain": category["domain"],
            "qualifier": qualifier, "qualifier_kind": kind, "note": note}


def _normalize_items(items, category_rows):
    if not isinstance(items, list) or not items:
        raise HTTPException(422, detail={"code": "INVALID_ICF_ITEMS"})
    category_by_code = {row["code"]: row for row in category_rows}
    normalized = []
    seen_codes = set()
    for item in items:
        normalized_item = _normalize_item(item, category_by_code)
        if normalized_item["code"] in seen_codes:
            raise HTTPException(422, detail={"code": "ICF_CODE_DUPLICATED",
                                             "message": f"类目编码 {normalized_item['code']} 重复"})
        seen_codes.add(normalized_item["code"])
        normalized.append(normalized_item)
    return normalized


async def _enabled_categories(db):
    rows = []
    async for doc in db.icf_categories.find({"enabled": True}):
        row = IcfCategory.from_mongo(doc)
        if row:
            rows.append(_category_public(row))
    return rows


def _assessment_public(row, *, include_items=True):
    result = {"id": str(row["_id"]), "patient_id": row["patient_id"],
              "assessor_id": row["assessor_id"], "source": row.get("source") or "manual",
              "source_ref": row.get("source_ref") or "",
              "assessed_at": row["assessed_at"], "note": row.get("note") or "",
              "review_status": row.get("review_status") or "pending",
              "review_note": row.get("review_note") or "",
              "mutation_version": _version(row), "content_revision": row.get("content_revision", 1),
              "created_at": row.get("created_at"), "updated_at": row.get("updated_at")}
    if include_items:
        result["items"] = deepcopy(row.get("items") or [])
    return result


def _version(row):
    value = row.get("mutation_version", 0)
    if type(value) is not int or value < 0:
        raise HTTPException(409, detail={"code": "ICF_ASSESSMENT_VERSION_INVALID"})
    return value


async def create_assessment(db, actor, patient_id, *, items, source="manual",
                            source_ref="", assessed_at=None, note=""):
    _require_clinical(actor)
    if source not in ICF_ASSESSMENT_SOURCES:
        raise HTTPException(422, detail={"code": "INVALID_ICF_SOURCE"})
    patient = await _patient_for(db, actor, patient_id)
    await ensure_default_categories(db)
    normalized = _normalize_items(items, await _enabled_categories(db))
    note = (note or "").strip()
    if len(note) > 2000:
        raise HTTPException(422, detail={"code": "INVALID_ICF_NOTE"})
    document = IcfAssessment(patient_id=str(patient["_id"]), assessor_id=str(actor.id),
                             items=normalized, source=source,
                             source_ref=(source_ref or "").strip()[:120],
                             assessed_at=assessed_at or _now(), note=note,
                             metadata={"note": METRIC_NOTE})
    await db.icf_assessments.insert_one(document.to_mongo())
    return _assessment_public(document.to_mongo())


async def list_assessments(db, actor, patient_id):
    await _patient_for(db, actor, patient_id)
    rows = [row async for row in
            db.icf_assessments.find({"patient_id": str(patient_id)}).sort("assessed_at", -1)]
    return {"assessments": [_assessment_public(row) for row in rows],
            "note": DICTIONARY_NOTE}


async def _load_assessment(db, assessment_id):
    if not ObjectId.is_valid(assessment_id):
        raise HTTPException(422, detail={"code": "INVALID_ICF_ASSESSMENT_ID"})
    row = await db.icf_assessments.find_one({"_id": ObjectId(assessment_id)})
    if not row:
        raise HTTPException(404, detail={"code": "ICF_ASSESSMENT_NOT_FOUND"})
    return row


async def get_assessment(db, actor, assessment_id):
    row = await _load_assessment(db, assessment_id)
    await _patient_for(db, actor, row["patient_id"])
    return _assessment_public(row)


async def update_assessment(db, actor, assessment_id, *, items, note,
                            expected_version):
    _require_clinical(actor)
    row = await _load_assessment(db, assessment_id)
    await _patient_for(db, actor, row["patient_id"])
    if type(expected_version) is not int or expected_version != _version(row):
        raise HTTPException(409, detail={"code": "ICF_ASSESSMENT_CONFLICT",
                                         "message": "评估已变化，请重新加载后修改"})
    normalized = _normalize_items(items, await _enabled_categories(db))
    note = (note or "").strip()
    if len(note) > 2000:
        raise HTTPException(422, detail={"code": "INVALID_ICF_NOTE"})
    revision = row.get("content_revision", 1)
    update = {"$set": {"items": normalized, "note": note,
                       "content_revision": revision + 1,
                       "review_status": "pending", "review_note": "",
                       "reviewer_id": None, "reviewed_at": None,
                       "mutation_version": expected_version + 1,
                       "updated_at": _now(), "updated_by": str(actor.id)}}
    result = await db.icf_assessments.update_one(
        {"_id": row["_id"], "mutation_version": expected_version}, update)
    if result.matched_count != 1:
        raise HTTPException(409, detail={"code": "ICF_ASSESSMENT_CONFLICT",
                                         "message": "评估已变化，请重新加载后修改"})
    return _assessment_public({**row, **update["$set"]})


async def review_assessment(db, actor, assessment_id, *, accepted, note, expected_version):
    """review 沿用 clinical_reports 语义：医护核对，备注必填，CAS 防并发。

    （R4-A1 收敛：状态机骨架迁 services/review_state_machine.py；本域为
    简化形态——不绑 reviewed_snapshot、不记 review_history，经不传
    snapshot_of/history_event 表达，字段集与原实现逐字一致。）
    """
    _require_clinical(actor)
    row = await _load_assessment(db, assessment_id)
    await _patient_for(db, actor, row["patient_id"])
    note = review_note(note)
    check_review_version(expected_version, _version(row),
                         code="ICF_ASSESSMENT_CONFLICT", message="评估已变化，请重新加载后审核")
    values = await commit_review(db.icf_assessments, row, expected_version=expected_version,
        accepted=accepted, note=note, actor_id=str(actor.id), now=_now(),
        code="ICF_ASSESSMENT_CONFLICT", message="评估已变化，请重新加载后审核")
    return _assessment_public({**row, **values})


# ------------------------------------------------------------------
# 指标定义（可配置）
# ------------------------------------------------------------------

async def list_metric_configs(db):
    configs = [IcfMetricConfig.from_mongo(doc) async for doc in db.icf_metric_configs.find({})]
    if not configs:
        await _seed_default_metric_configs(db)
        configs = [IcfMetricConfig.from_mongo(doc) async for doc in db.icf_metric_configs.find({})]
    return {"metrics": [_metric_config_public(row) for row in configs if row],
            "note": METRIC_NOTE}


async def _seed_default_metric_configs(db):
    for item in DEFAULT_METRIC_CONFIGS:
        existing = await db.icf_metric_configs.find_one({"metric_key": item["metric_key"]})
        if existing:
            continue
        config = IcfMetricConfig(metric_key=item["metric_key"], name=item["name"],
                                 description=item["description"], enabled=item["enabled"],
                                 params=deepcopy(item["params"]))
        await db.icf_metric_configs.insert_one(config.to_mongo())


def _metric_config_public(row):
    return {"id": str(row._id), "metric_key": row.metric_key, "name": row.name,
            "description": row.description, "enabled": bool(row.enabled),
            "params": deepcopy(row.params), "note": METRIC_NOTE}


async def update_metric_config(db, actor, metric_key, *, enabled=None, params=None):
    _require_clinical(actor)
    row = await db.icf_metric_configs.find_one({"metric_key": metric_key})
    if not row:
        raise HTTPException(404, detail={"code": "ICF_METRIC_NOT_FOUND"})
    update = {"updated_at": _now(), "updated_by": str(actor.id)}
    if enabled is not None:
        update["enabled"] = bool(enabled)
    if params is not None:
        if not isinstance(params, dict):
            raise HTTPException(422, detail={"code": "INVALID_METRIC_PARAMS"})
        update["params"] = params
    await db.icf_metric_configs.update_one({"metric_key": metric_key}, {"$set": update})
    return {"metric_key": metric_key, **{key: value for key, value in update.items()
                                         if key not in {"updated_at", "updated_by"}},
            "updated": True, "note": METRIC_NOTE}


# ------------------------------------------------------------------
# 指标自动计算与预警触发
# ------------------------------------------------------------------

def _numeric_observation(item):
    if item.get("qualifier_kind") != "numeric":
        return None
    value = item.get("qualifier")
    return value if isinstance(value, int) and 0 <= value <= 4 else None


def _latest_items_by_code(assessments):
    """按评估时间正序扫描，得到每个类目编码的（首次数值, 最近数值, 数值次数）。"""
    ordered = sorted(assessments, key=lambda row: (row.get("assessed_at") or row.get("created_at")
                                                   or datetime.min.replace(tzinfo=None)))
    first_numeric, last_numeric, numeric_count = {}, {}, {}
    for row in ordered:
        for item in row.get("items") or []:
            code = item.get("code")
            if not code:
                continue
            value = _numeric_observation(item)
            if value is None:
                continue
            first_numeric.setdefault(code, value)
            last_numeric[code] = value
            numeric_count[code] = numeric_count.get(code, 0) + 1
    return first_numeric, last_numeric, numeric_count


def _compute_qualifier_improvement(assessments, params):
    min_improvement = params.get("min_improvement", 1)
    first, last, counts = _latest_items_by_code(assessments)
    details = []
    alert_codes = []
    for code, value in last.items():
        if counts.get(code, 0) < 2:
            continue
        improvement = first[code] - value
        breached = improvement < min_improvement
        if breached:
            alert_codes.append(code)
        details.append({"code": code, "improvement": improvement,
                        "state": "alert" if breached else "ok"})
    if not details:
        return {"metric_key": "qualifier_improvement", "state": "insufficient_data",
                "value": None, "threshold": min_improvement,
                "detail": [], "message": "暂无同一类目两次数值限定值，无法计算改善幅度。"}
    return {"metric_key": "qualifier_improvement",
            "state": "alert" if alert_codes else "ok",
            "value": len(alert_codes), "threshold": min_improvement,
            "detail": details,
            "message": (f"{len(alert_codes)} 个类目改善幅度低于阈值 {min_improvement}。"
                        if alert_codes else "全部可比类目改善幅度达到阈值。")}


def _compute_attainment_rate(assessments, params):
    target = params.get("target_qualifier", 1)
    min_rate = params.get("min_rate", 0.6)
    _, last, _ = _latest_items_by_code(assessments)
    compared = sorted(last.items())
    if not compared:
        return {"metric_key": "attainment_rate", "state": "insufficient_data",
                "value": None, "threshold": min_rate, "detail": [],
                "message": "暂无数值限定值，无法计算达标率。"}
    attained = [code for code, value in compared if value <= target]
    rate = len(attained) / len(compared)
    details = [{"code": code, "qualifier": value, "attained": value <= target}
               for code, value in compared]
    breached = rate < min_rate
    return {"metric_key": "attainment_rate",
            "state": "alert" if breached else "ok",
            "value": round(rate, 4), "threshold": min_rate,
            "detail": details,
            "message": (f"达标率 {rate:.0%} 低于阈值 {min_rate:.0%}（口径待临床确认）。"
                        if breached else f"达标率 {rate:.0%} 达到阈值。")}


def _compute_followup_completion(followups, params):
    min_rate = params.get("min_rate", 0.8)
    rows = [row for row in followups
            if (row.get("status") or "") not in _VOID_FOLLOWUP_STATUS]
    if not rows:
        return {"metric_key": "followup_completion_rate", "state": "insufficient_data",
                "value": None, "threshold": min_rate, "detail": [],
                "message": "暂无非作废随访记录，无法计算完成率。"}
    completed = sum(1 for row in rows
                    if (row.get("status") or "") in _COMPLETED_FOLLOWUP_STATUS)
    rate = completed / len(rows)
    breached = rate < min_rate
    return {"metric_key": "followup_completion_rate",
            "state": "alert" if breached else "ok",
            "value": round(rate, 4), "threshold": min_rate,
            "detail": [{"total": len(rows), "completed": completed}],
            "message": (f"随访完成率 {rate:.0%} 低于阈值 {min_rate:.0%}（口径待临床确认）。"
                        if breached else f"随访完成率 {rate:.0%} 达到阈值。")}


_COMPUTERS = {
    "qualifier_improvement": _compute_qualifier_improvement,
    "attainment_rate": _compute_attainment_rate,
    "followup_completion_rate": _compute_followup_completion,
}

# 随访完成率指标的取样上限（口径待临床确认；超出按最近 500 条计算）。
_FOLLOWUP_SAMPLE_LIMIT = 500


async def _load_followups(db, patient_id):
    """随访数据源走唯一服务入口 FollowupService（服务集合收敛门 S2）。

    只取完成率所需的 status 字段；软删除由 FollowupService 过滤。
    """
    from app.services.followup_service import FollowupService
    records = await FollowupService(db).list_all_followups(
        patient_id, skip=0, limit=_FOLLOWUP_SAMPLE_LIMIT)
    return [{"status": str(record.status or "")} for record in records]


async def compute_patient_metrics(db, actor, patient_id):
    """从 icf_assessments 与随访记录（经 FollowupService）计算指标；不触发预警。"""
    await _patient_for(db, actor, patient_id)
    return await _compute_metrics_for(db, str(patient_id))


async def _compute_metrics_for(db, patient_id):
    configs = [IcfMetricConfig.from_mongo(doc) async for doc in db.icf_metric_configs.find({})]
    if not configs:
        await _seed_default_metric_configs(db)
        configs = [IcfMetricConfig.from_mongo(doc) async for doc in db.icf_metric_configs.find({})]
    assessments = [row async for row in
                   db.icf_assessments.find({"patient_id": patient_id})]
    followups = await _load_followups(db, patient_id)
    metric_sources = {
        "qualifier_improvement": assessments,
        "attainment_rate": assessments,
        "followup_completion_rate": followups,
    }
    rows = []
    for config in configs:
        if not config.enabled:
            rows.append({"metric_key": config.metric_key, "name": config.name,
                         "state": "disabled", "value": None,
                         "threshold": None, "detail": [],
                         "message": "该指标已被停用（可后台重新启用）。"})
            continue
        computer = _COMPUTERS.get(config.metric_key)
        if computer is None:
            rows.append({"metric_key": config.metric_key, "name": config.name,
                         "state": "unsupported", "value": None, "threshold": None,
                         "detail": [], "message": "未知的指标定义，请检查配置。"})
            continue
        result = computer(metric_sources.get(config.metric_key, []), config.params)
        result["name"] = config.name
        rows.append(result)
    return {"patient_id": patient_id, "computed_at": _now(), "metrics": rows,
            "note": METRIC_NOTE}


async def evaluate_metrics_and_alert(db, actor, patient_id):
    """计算指标并对越界项触发预警：复用 health_alert_service.create_alert
    （health_data_alerts 集合；医护通知由该服务统一经 NotificationService
    产生），同一患者同一指标存在未处理预警时去重，不重复轰炸。"""
    _require_clinical(actor)
    patient = await _patient_for(db, actor, patient_id)
    pid = str(patient["_id"])
    result = await _compute_metrics_for(db, pid)
    alert_service = HealthAlertService(db)
    triggered, skipped = [], []
    latest_assessment_id = ""
    if result["metrics"]:
        latest = await db.icf_assessments.find_one(
            {"patient_id": pid}, sort=[("assessed_at", -1)])
        if latest:
            latest_assessment_id = str(latest["_id"])
    for row in result["metrics"]:
        if row["state"] != "alert" or row["value"] is None:
            continue
        metric_key = row["metric_key"]
        dedup_query = {"patient_id": pid, "data_type": ICF_ALERT_DATA_TYPE,
                       "status": "active", "metadata.metric_key": metric_key}
        if await alert_service.alerts.find_one(dedup_query):
            skipped.append({"metric_key": metric_key,
                            "message": "已存在同指标未处理预警，本次不重复创建。"})
            continue
        data = AlertCreate(
            health_data_id=latest_assessment_id or pid,
            patient_id=pid,
            data_type=ICF_ALERT_DATA_TYPE,
            value=float(row["value"]),
            alert_level="warning",
            recorded_at=_now(),
            metadata={"metric_key": metric_key, "metric_name": row.get("name") or metric_key,
                      "threshold": row.get("threshold"), "message": row.get("message") or "",
                      "source": "icf_metric_evaluation", "note": METRIC_NOTE},
        )
        alert = await alert_service.create_alert(data)
        triggered.append({"metric_key": metric_key, "alert_id": alert.id})
    return {**result, "triggered": triggered, "skipped": skipped}


# ------------------------------------------------------------------
# 正式 ICF 报告
# ------------------------------------------------------------------

def _content_snapshot(row):
    return deepcopy(row.get("payload") or {})


def _report_public(row, *, include_payload=True):
    result = {"id": str(row["_id"]), "patient_id": row["patient_id"],
              "assessment_id": row.get("assessment_id") or "",
              "title": row.get("title") or "", "generated_by": row.get("generated_by") or "",
              "generated_at": row.get("created_at"),
              "review_status": row.get("review_status") or "pending",
              "review_note": row.get("review_note") or "",
              "mutation_version": _report_version(row),
              "content_revision": row.get("content_revision", 1),
              "created_at": row.get("created_at"), "updated_at": row.get("updated_at"),
              "exportable": export_gate(row, _content_snapshot(row))}
    if include_payload:
        result["payload"] = deepcopy(row.get("payload") or {})
    if include_payload:
        history = [{key: event.get(key) for key in
                    ("action", "at", "actor_id", "note", "accepted")}
                   for event in (row.get("review_history") or [])]
        result["review_history"] = history
    return result


def _report_version(row):
    value = row.get("mutation_version", 0)
    if type(value) is not int or value < 0:
        raise HTTPException(409, detail={"code": "ICF_REPORT_VERSION_INVALID"})
    return value


async def generate_report(db, actor, patient_id, assessment_id):
    """按已审核评估生成结构化正式报告（含各域限定值汇总与指标结论）。"""
    _require_clinical(actor)
    if not ObjectId.is_valid(assessment_id):
        raise HTTPException(422, detail={"code": "INVALID_ICF_ASSESSMENT_ID"})
    patient = await _patient_for(db, actor, patient_id)
    assessment = await db.icf_assessments.find_one({"_id": ObjectId(assessment_id)})
    if not assessment or assessment.get("patient_id") != str(patient["_id"]):
        raise HTTPException(404, detail={"code": "ICF_ASSESSMENT_NOT_FOUND"})
    if assessment.get("review_status") != "reviewed":
        raise HTTPException(409, detail={"code": "ICF_ASSESSMENT_NOT_REVIEWED",
                                         "message": "评估尚未经医护审核，不能生成正式报告"})
    metrics = await _compute_metrics_for(db, str(patient["_id"]))
    domains = {name: [] for name in ICF_DOMAINS}
    for item in assessment.get("items") or []:
        domains.setdefault(item.get("domain") or "body", []).append(deepcopy(item))
    patient_name = patient.get("name") or ""
    payload = {
        "patient": {"id": str(patient["_id"]), "name": patient_name,
                    "source_project_id": patient.get("source_project_id"),
                    "source_center_id": patient.get("source_center_id")},
        "assessment": {"id": str(assessment["_id"]),
                       "assessed_at": assessment.get("assessed_at"),
                       "source": assessment.get("source") or "manual",
                       "source_ref": assessment.get("source_ref") or "",
                       "assessor_id": assessment.get("assessor_id") or "",
                       "review_status": assessment.get("review_status")},
        "domains": domains,
        "metrics": metrics["metrics"],
        "disclaimer": REPORT_DISCLAIMER,
    }
    document = IcfReport(patient_id=str(patient["_id"]),
                         assessment_id=str(assessment["_id"]),
                         title=f"{patient_name or '患者'} ICF 评估报告",
                         generated_by=str(actor.id), payload=payload)
    await db.icf_reports.insert_one(document.to_mongo())
    return _report_public(document.to_mongo())


async def list_reports(db, actor, patient_id):
    await _patient_for(db, actor, patient_id)
    rows = [row async for row in
            db.icf_reports.find({"patient_id": str(patient_id)}).sort("created_at", -1)]
    return {"reports": [_report_public(row) for row in rows],
            "disclaimer": REPORT_DISCLAIMER}


async def get_report(db, actor, report_id):
    row = await _load_report(db, report_id)
    await _patient_for(db, actor, row["patient_id"])
    return _report_public(row)


async def load_report_for_export(db, actor, report_id):
    """导出前的原始文档加载（含对象级授权），供路由的 export 端点复用。"""
    row = await _load_report(db, report_id)
    await _patient_for(db, actor, row["patient_id"])
    return row


async def _load_report(db, report_id):
    if not ObjectId.is_valid(report_id):
        raise HTTPException(422, detail={"code": "INVALID_ICF_REPORT_ID"})
    row = await db.icf_reports.find_one({"_id": ObjectId(report_id)})
    if not row:
        raise HTTPException(404, detail={"code": "ICF_REPORT_NOT_FOUND"})
    return row


async def review_icf_report(db, actor, report_id, *, accepted, note, expected_version):
    """复用 clinical_reports 的 review 状态语义：备注必填、CAS、
    通过时保存 reviewed_snapshot，导出仅对与快照一致的已审核报告开放。
    （R4-A1 收敛：骨架迁 services/review_state_machine.py；快照构造留本域
    回调 _content_snapshot，历史事件经 review_event/append_review_history。）"""
    _require_clinical(actor)
    row = await _load_report(db, report_id)
    await _patient_for(db, actor, row["patient_id"])
    note = review_note(note)
    check_review_version(expected_version, _report_version(row),
                         code="ICF_REPORT_CONFLICT", message="报告已变化，请重新加载后审核")
    now = _now()
    values = await commit_review(db.icf_reports, row, expected_version=expected_version,
        accepted=accepted, note=note, actor_id=str(actor.id), now=now,
        code="ICF_REPORT_CONFLICT", message="报告已变化，请重新加载后审核",
        snapshot_of=_content_snapshot,
        history_event=append_review_history(
            row, review_event(str(actor.id), note, accepted, now)))
    return _report_public({**row, **values})


def _require_exportable(row):
    if not export_gate(row, _content_snapshot(row)):
        raise HTTPException(409, detail={"code": "ICF_REPORT_NOT_REVIEWED",
                                         "message": "报告未经医护审核或内容已变化，不能导出"})


def export_report_json(row):
    """审核通过的报告导出为结构化 JSON（含审核信息与免责口径说明）。"""
    _require_exportable(row)
    payload = _content_snapshot(row)
    return {"id": str(row["_id"]), "title": row.get("title") or "",
            "generated_at": row.get("created_at"), "generated_by": row.get("generated_by") or "",
            "review": {"status": row.get("review_status"), "note": row.get("review_note") or "",
                       "reviewer_id": row.get("reviewer_id"), "reviewed_at": row.get("reviewed_at")},
            "payload": payload}


_QUALIFIER_LABELS = {0: "无问题", 1: "轻度", 2: "中度", 3: "重度", 4: "完全"}
_DOMAIN_LABELS = {"body": "身体功能", "activity": "活动", "participation": "参与"}


def export_report_html(row):
    """审核通过的报告导出为打印友好 HTML（无脚本、内联样式）。"""
    _require_exportable(row)
    payload = _content_snapshot(row)
    review = {"status": row.get("review_status"), "note": row.get("review_note") or "",
              "reviewed_at": row.get("reviewed_at")}
    patient = payload.get("patient") or {}
    assessment = payload.get("assessment") or {}
    parts = [
        "<!DOCTYPE html>",
        '<html lang="zh-CN"><head><meta charset="utf-8">',
        f"<title>{escape(row.get('title') or 'ICF 评估报告')}</title>",
        "<style>",
        "body{font-family:'Songti SC','SimSun',serif;margin:32px auto;max-width:800px;color:#111}",
        "h1{font-size:22px} h2{font-size:16px;border-bottom:1px solid #ccc;padding-bottom:4px}",
        "table{border-collapse:collapse;width:100%;margin:8px 0 16px}",
        "th,td{border:1px solid #999;padding:6px 8px;font-size:13px;text-align:left}",
        "th{background:#f2f2f2}",
        ".meta{font-size:13px;color:#444} .note{font-size:12px;color:#666}",
        "@media print{body{margin:0}}",
        "</style></head><body>",
        f"<h1>{escape(row.get('title') or 'ICF 评估报告')}</h1>",
        f'<p class="meta">患者：{escape(str(patient.get("name") or ""))}'
        f'（ID: {escape(str(patient.get("id") or ""))}）　'
        f'评估来源：{escape(str(assessment.get("source") or ""))}　'
        f'生成时间：{escape(str(row.get("created_at") or ""))}</p>',
    ]
    for domain in ICF_DOMAINS:
        items = (payload.get("domains") or {}).get(domain) or []
        if not items:
            continue
        parts.append(f"<h2>{escape(_DOMAIN_LABELS.get(domain, domain))}</h2>")
        parts.append("<table><tr><th>编码</th><th>类目</th><th>限定值</th><th>说明</th></tr>")
        for item in items:
            qualifier = item.get("qualifier")
            qualifier_text = (_QUALIFIER_LABELS.get(qualifier, str(qualifier))
                              if isinstance(qualifier, int) else str(qualifier))
            parts.append(f"<tr><td>{escape(str(item.get('code') or ''))}</td>"
                         f"<td>{escape(str(item.get('name') or ''))}</td>"
                         f"<td>{escape(qualifier_text)}</td>"
                         f"<td>{escape(str(item.get('note') or ''))}</td></tr>")
        parts.append("</table>")
    metrics = payload.get("metrics") or []
    if metrics:
        parts.append("<h2>指标结论（口径待临床确认）</h2><table><tr><th>指标</th><th>结果</th><th>阈值</th><th>说明</th></tr>")
        for metric in metrics:
            value = metric.get("value")
            value_text = "—" if value is None else str(value)
            parts.append(f"<tr><td>{escape(str(metric.get('name') or metric.get('metric_key') or ''))}</td>"
                         f"<td>{escape(str(metric.get('state') or ''))}</td>"
                         f"<td>{escape(value_text)}</td>"
                         f"<td>{escape(str(metric.get('message') or ''))}</td></tr>")
        parts.append("</table>")
    parts.append(f'<p class="note">{escape(str(payload.get("disclaimer") or ""))}</p>')
    parts.append(f'<p class="note">审核状态：{escape(str(review.get("status") or ""))}　'
                 f'审核时间：{escape(str(review.get("reviewed_at") or ""))}　'
                 f'审核备注：{escape(review.get("note"))}</p>')
    parts.append("</body></html>")
    return "\n".join(parts)

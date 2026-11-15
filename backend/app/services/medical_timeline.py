"""Read-only, patient-scoped projection of current facts and retained history.

Source replicas are never written here. The history view retains old snapshots;
current excludes a snapshot whenever its exact same-patient source still exists,
including a soft-deleted source, so deletion cannot revive a stale replica.
"""
from app.schemas.health_record import HealthTimelineItem
from app.core.exceptions import AppBaseException
from datetime import timezone


def _text(value, default=""):
    return {"$convert": {"input": value, "to": "string", "onError": default, "onNull": default}}


def _date(*fields):
    return {"$switch": {"branches": [{"case": {"$eq": [{"$type": field}, "date"]},
                                      "then": field} for field in fields], "default": None}}


def _object(field):
    return {"$cond": [{"$eq": [{"$type": field}, "object"]}, field, {}]}


def _measurement(value):
    pairs = {"$reduce": {"input": {"$objectToArray": _object(value)}, "initialValue": "",
        "in": {"$concat": ["$$value", {"$cond": [{"$eq": ["$$value", ""]}, "", ", "]},
                            "$$this.k", ": ", _text("$$this.v", "复合值（见原始数据）")]}}}
    return {"$cond": [{"$eq": [{"$type": value}, "object"]}, pairs, _text(value)]}


def _project(collection, item_type, title, description, timestamp, metadata, original):
    identifier = _text("$_id")
    return {"$project": {"_id": 0, "id": {"$concat": [collection + ":", {"$type": "$_id"}, ":", identifier]},
        "patient_id": 1, "item_type": item_type, "title": title, "description": description,
        "timestamp": timestamp, "data": {"related_ids": [identifier], "metadata": metadata,
            "source": {"collection": collection, "id": identifier, "view": "current"},
            "original_timestamp": original}, "importance": {"$literal": 0}}}


def _sources(patient_id):
    base = {"patient_id": patient_id, "deleted": {"$ne": True}}
    status = _text("$status", "未记录")
    kinds = {"vital_sign": "生命体征", "lab_result": "实验室检查", "medication": "用药记录",
             "activity": "活动记录", "sleep": "睡眠记录", "diet": "饮食记录"}
    health_data_title = {"$switch": {"branches": [{"case": {"$eq": ["$data_type", key]},
        "then": value} for key, value in kinds.items()], "default": _text("$data_type", "健康数据")}}
    return [
        ("health_records", [{"$match": base}, _project("health_records", {"$literal": "health_record"},
            _text("$title", "健康记录"), {"$concat": [_text("$record_type"), " 记录"]},
            _date("$updated_at", "$created_at"), {"record_type": _text("$record_type"),
                "timestamp_basis": "updated_at_then_created_at"}, _date("$created_at"))]),
        ("followup_records", [{"$match": base}, _project("followup_records", {"$literal": "follow_up"},
            {"$concat": [_text("$follow_up_type"), " 随访"]}, {"$concat": ["随访状态: ", status]},
            _date("$actual_date", "$scheduled_date"), {"status": status, "type": _text("$follow_up_type")},
            _date("$scheduled_date"))]),
        ("health_data", [{"$match": base}, _project("health_data",
            {"$concat": ["health_data_", _text("$data_type", "unknown")]}, health_data_title,
            {"$cond": [{"$eq": ["$data_type", "lab_result"]},
                {"$concat": [_text("$data.test_name"), ": ", _measurement("$data.result_value"), " ", _text("$data.unit")]},
                {"$concat": [_text("$data.type"), ": ", _measurement("$data.value"), " ", _text("$data.unit")]}]},
            _date("$recorded_at"), {"$mergeObjects": [_object("$metadata"),
                {"data_type": _text("$data_type"), "source": _text("$source"),
                 "device_id": _text("$device_id"), "values": _object("$data"),
                 "quality_flags": {"$ifNull": ["$metadata.quality_flags", {"$ifNull": ["$quality_flags", []]}]}}]},
            _date("$recorded_at"))]),
        ("rehab_assessments", [{"$match": base}, _project("rehab_assessments",
            {"$literal": "rehabilitation_assessment"}, {"$literal": "康复评估"}, _text("$assessment_type"),
            _date("$created_at"), {"assessment_type": _text("$assessment_type")}, _date("$created_at"))]),
        ("icf_assessments", [{"$match": base}, _project("icf_assessments", {"$literal": "icf_assessment"},
            {"$literal": "ICF 评估"}, {"$concat": ["审核状态: ", _text("$review_status", "pending")]},
            _date("$assessed_at", "$created_at"), {"review_status": _text("$review_status", "pending")},
            _date("$assessed_at"))]),
    ]


def _history(patient_id, view):
    stages = [{"$match": {"patient_id": patient_id}}, {"$set": {
        "_primary": _text({"$arrayElemAt": [{"$cond": [{"$isArray": "$related_ids"}, "$related_ids", []]}, 0]}),
        "_kind": _text("$item_type", "historical")}}]
    stages.append({"$set": {"_primary_ids": {"$filter": {"input": ["$_primary",
        {"$convert": {"input": "$_primary", "to": "objectId", "onError": None, "onNull": None}}],
        "as": "identifier", "cond": {"$and": [{"$ne": ["$$identifier", ""]}, {"$ne": ["$$identifier", None]}]}}}}})
    matches = {"health_records": {"$eq": ["$_kind", "health_record"]},
        "followup_records": {"$eq": ["$_kind", "follow_up"]},
        "health_data": {"$or": [{"$eq": [{"$indexOfCP": ["$_kind", "health_data_"]}, 0]},
                               {"$in": ["$_kind", ["vital_sign", "lab_result", "medication"]]}]},
        "rehab_assessments": {"$eq": ["$_kind", "rehabilitation_assessment"]},
        "icf_assessments": {"$eq": ["$_kind", "icf_assessment"]}}
    for collection, kind in matches.items():
        stages.append({"$lookup": {"from": collection,
            "localField": "_primary_ids", "foreignField": "_id", "let": {"kind_matches": kind},
            "pipeline": [{"$match": {"patient_id": patient_id, "$expr": "$$kind_matches"}},
                {"$limit": 2}, {"$project": {"_id": 1}}], "as": "_source_" + collection}})
    stages.append({"$set": {"_linked_count": {"$add": [{"$size": "$_source_" + collection} for collection in matches]}}})
    if view == "current":
        stages.append({"$match": {"_linked_count": {"$ne": 1}}})
    stages.append({"$project": {"_id": 0, "id": {"$concat": ["medical_timelines:", {"$type": "$_id"}, ":", _text("$_id")]},
        "patient_id": 1, "item_type": "$_kind", "title": _text("$title", "历史记录"),
        "description": _text("$description"), "timestamp": _date("$occurred_at"),
        "data": {"related_ids": {"$cond": [{"$isArray": "$related_ids"}, "$related_ids", []]},
            "metadata": _object("$metadata"), "source": {"collection": "medical_timelines",
                "id": _text("$_id"), "view": "history", "orphan": {"$eq": ["$_linked_count", 0]},
                "ambiguous": {"$gt": ["$_linked_count", 1]}},
            "original_timestamp": _date("$occurred_at")},
        "icon": _text("$metadata.icon", None), "color": _text("$metadata.color", None),
        "importance": {"$convert": {"input": "$metadata.importance", "to": "int", "onError": 0, "onNull": 0}}}})
    return stages


def timeline_pipeline(patient_id, *, view="current", start_date=None, end_date=None,
                      item_types=None, skip=0, limit=100):
    if not patient_id or view not in {"current", "history"} or skip < 0 or not 1 <= limit <= 500:
        raise AppBaseException("时间线查询参数无效", status_code=422, error_code="TIMELINE_QUERY_INVALID")
    # Stored dates and existing unzoned query values use UTC, never host local time.
    def utc(value):
        if value is None:
            return None
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    start_date, end_date = utc(start_date), utc(end_date)
    if start_date is not None and end_date is not None and start_date > end_date:
        raise AppBaseException("时间线结束时间不能早于开始时间", status_code=422, error_code="TIMELINE_DATE_WINDOW_INVALID")
    if view == "history":
        collection, pipeline = "medical_timelines", _history(patient_id, view)
    else:
        sources = _sources(patient_id)
        collection, pipeline = sources[0]
        for name, branch in sources[1:]:
            pipeline.append({"$unionWith": {"coll": name, "pipeline": branch}})
        pipeline.append({"$unionWith": {"coll": "medical_timelines", "pipeline": _history(patient_id, view)}})
    filters = {}
    if item_types:
        types = set(item_types)
        types.update("health_data_" + item for item in item_types if item in {"vital_sign", "lab_result", "medication"})
        filters["item_type"] = {"$in": sorted(types)}
    dates = {}
    if start_date is not None:
        dates["$gte"] = start_date
    if end_date is not None:
        dates["$lte"] = end_date
    if dates:
        filters["timestamp"] = dates
    if filters:
        pipeline.append({"$match": filters})
    pipeline.extend([{"$sort": {"timestamp": -1, "id": 1}}, {"$skip": skip}, {"$limit": limit}])
    return collection, pipeline


async def read_timeline(db, patient_id, **options):
    collection, pipeline = timeline_pipeline(patient_id, **options)
    rows = await db[collection].aggregate(pipeline).to_list(length=options.get("limit", 100))
    return [HealthTimelineItem(**row) for row in rows]

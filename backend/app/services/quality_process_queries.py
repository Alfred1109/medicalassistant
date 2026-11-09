"""Pure Mongo query construction for process facts; no clinical scoring rules."""

FOLLOWUP_STATUSES = ("pending_schedule", "scheduled", "awaiting_fill", "in_review",
                     "completed", "canceled", "missed", "overdue", "lost", "rescheduled")
PLAN_STATUSES = ("draft", "active", "completed", "cancelled", "canceled", "archived")
PUBLICATION_STATES = ("published", "unpublished", "withdrawn", "stopped", "invalid_reference")


def _nonempty_string(value):
    return {"$and": [{"$eq": [{"$type": value}, "string"]},
        {"$gt": [{"$strLenCP": {"$trim": {"input": {"$cond": [{"$eq": [{"$type": value}, "string"]}, value, ""]}}}}, 0]}]}


def _required_publication_structure():
    items = {"$cond": [{"$eq": [{"$type": "$items_snapshot"}, "array"]}, "$items_snapshot", []]}
    return {"$and": [
        {"$eq": [{"$type": "$snapshot"}, "object"]},
        *[_nonempty_string("$snapshot." + field) for field in ("name", "description", "goal")],
        {"$eq": [{"$type": "$snapshot.start_date"}, "date"]},
        {"$or": [{"$in": [{"$type": "$snapshot.end_date"}, ["missing", "null"]]},
            {"$and": [{"$eq": [{"$type": "$snapshot.end_date"}, "date"]},
                       {"$gte": ["$snapshot.end_date", "$snapshot.start_date"]}]}]},
        {"$eq": [{"$type": "$published_at"}, "date"]},
        _nonempty_string("$published_by"), _nonempty_string("$confirmation_note"),
        {"$in": [{"$type": "$publication_revision"}, ["int", "long"]]},
        {"$gt": ["$publication_revision", 0]},
        {"$gt": [{"$size": items}, 0]}, {"$lte": [{"$size": items}, 200]},
        {"$allElementsTrue": [{"$map": {"input": items, "as": "item", "in": {"$and": [
            {"$eq": [{"$type": "$$item"}, "object"]}, _nonempty_string("$$item.name"),
            {"$in": ["$$item.intervention_type", ["diet", "exercise", "medication", "psychology"]]},
            {"$regexMatch": {"input": {"$cond": [{"$eq": [{"$type": "$$item.item_id"}, "string"]}, "$$item.item_id", ""]}, "regex": "^[0-9a-f]{24}$"}},
        ]}}}]},
    ]}


def _status_expression(known):
    return {"$switch": {"branches": [
        {"case": {"$in": [{"$type": "$status"}, ["missing", "null"]]}, "then": "__missing__"},
        {"case": {"$ne": [{"$type": "$status"}, "string"]}, "then": "__invalid__"},
        {"case": {"$in": ["$status", list(known)]}, "then": "$status"},
    ], "default": "__unknown__"}}


def _publication_stages(versions_collection):
    return [
        {"$set": {"_qc_pointer": {"$convert": {"input": {"$cond": [{"$eq": [{"$type": "$published_version_id"}, "string"]}, "$published_version_id", None]}, "to": "objectId", "onError": None, "onNull": None}}}},
        {"$lookup": {"from": versions_collection, "let": {"pointer": "$_qc_pointer", "plan": {"$convert": {"input": "$_id", "to": "string", "onError": None}}, "patient": "$patient_id"},
            "pipeline": [{"$match": {"$expr": {"$and": [
                {"$ne": ["$$pointer", None]}, {"$ne": ["$$plan", None]}, {"$eq": ["$_id", "$$pointer"]},
                {"$eq": ["$plan_id", "$$plan"]}, {"$eq": ["$patient_id", "$$patient"]},
                {"$eq": ["$workflow", "patient_publication"]}, {"$eq": ["$status", "published"]},
                _required_publication_structure(),
            ]}}}, {"$project": {"_id": 1}}], "as": "_qc_version"}},
        {"$lookup": {"from": versions_collection, "let": {"plan": {"$convert": {"input": "$_id", "to": "string", "onError": None}}, "patient": "$patient_id", "history": "$has_publication_history"},
            "pipeline": [{"$match": {"$expr": {"$and": [
                {"$eq": ["$$history", True]}, {"$ne": ["$$plan", None]}, {"$eq": ["$plan_id", "$$plan"]},
                {"$eq": ["$patient_id", "$$patient"]}, {"$eq": ["$workflow", "patient_publication"]},
                {"$eq": ["$status", "withdrawn"]}, _required_publication_structure(),
            ]}}}, {"$limit": 1}, {"$project": {"_id": 1}}], "as": "_qc_withdrawn"}},
        {"$set": {"_qc_publication": {"$switch": {"branches": [
            {"case": {"$in": ["$status", ["cancelled", "canceled", "archived"]]}, "then": "stopped"},
            {"case": {"$eq": [{"$size": "$_qc_version"}, 1]}, "then": "published"},
            {"case": {"$in": [{"$type": "$published_version_id"}, ["missing", "null"]]},
             "then": {"$cond": [{"$eq": ["$has_publication_history", True]},
                 {"$cond": [{"$eq": [{"$size": "$_qc_withdrawn"}, 1]}, "withdrawn", "invalid_reference"]}, "unpublished"]}},
        ], "default": "invalid_reference"}}}},
    ]


def _patient_reference_stages():
    return [
        {"$set": {"_qc_patient_oid": {"$convert": {"input": "$patient_id", "to": "objectId", "onError": None, "onNull": None}}}},
        {"$lookup": {"from": "users", "let": {"raw": "$patient_id", "oid": "$_qc_patient_oid"}, "pipeline": [
            {"$match": {"role": "patient", "$expr": {"$or": [
                {"$eq": ["$_id", "$$raw"]}, {"$and": [{"$ne": ["$$oid", None]}, {"$eq": ["$_id", "$$oid"]}]}
            ]}}}, {"$project": {"_id": 1, "is_active": 1}}], "as": "_qc_patient"}},
        {"$set": {"_qc_patient_reference": {"$switch": {"branches": [
            {"case": {"$in": [{"$type": "$patient_id"}, ["missing", "null"]]}, "then": "missing"},
            {"case": {"$ne": [{"$type": "$patient_id"}, "string"]}, "then": "invalid"},
            {"case": {"$gt": [{"$size": "$_qc_patient"}, 1]}, "then": "ambiguous"},
            {"case": {"$eq": [{"$size": "$_qc_patient"}, 1]}, "then": "valid"},
        ], "default": "not_found"}}}},
        {"$set": {"_qc_issue_eligible": {"$and": [
            {"$eq": [{"$size": "$_qc_patient"}, 1]},
            {"$eq": [{"$type": "$patient_id"}, "string"]},
            {"$ne": ["$_qc_patient_oid", None]},
            {"$eq": ["$patient_id", {"$toString": "$_qc_patient_oid"}]},
            {"$eq": [{"$arrayElemAt": ["$_qc_patient.is_active", 0]}, True]},
            {"$eq": [{"$type": "$_id"}, "objectId"]},
        ]}}},
    ]


def monitoring_pipeline(kind, patient_ids, *, start_date=None, end_date=None, skip=0, limit=20,
                        include_items=False, versions_collection="rehab_plan_versions"):
    """Scope is applied before every count, lookup and page; windows are half open.

    Missing/invalid date counts cover the entire authorized source scope. They
    cannot be attributed to a date window and are never silently assigned one.
    """
    field = "scheduled_date" if kind == "followup" else "created_at"
    known = FOLLOWUP_STATUSES if kind == "followup" else PLAN_STATUSES
    base = {"deleted": {"$ne": True}}
    if patient_ids is not None:
        base["patient_id"] = {"$in": list(patient_ids)}
    date_filter = {}
    if start_date is not None:
        date_filter["$gte"] = start_date
    if end_date is not None:
        date_filter["$lt"] = end_date
    selected = [{"$match": {field: {"$type": "date", **date_filter}}}] if date_filter else []
    selected += [{"$set": {"_qc_status": _status_expression(known)}}]
    metrics = {"statuses": selected + [{"$group": {"_id": "$_qc_status", "count": {"$sum": 1}}}],
               "total": selected + [{"$count": "count"}]}
    if kind == "rehab_plan":
        metrics["publications"] = selected + _publication_stages(versions_collection) + [{"$group": {"_id": "$_qc_publication", "count": {"$sum": 1}}}]
    if include_items:
        projection = {"_id": 0, "source_type": {"$literal": kind}, "source_id": {"$convert": {"input": "$_id", "to": "string", "onError": "[unaddressable]", "onNull": "[unaddressable]"}},
            "source_reference_state": {"$cond": [{"$eq": [{"$type": "$_id"}, "objectId"]}, "valid", "unaddressable"]},
            "patient_id": {"$cond": [{"$eq": [{"$type": "$patient_id"}, "string"]}, "$patient_id", None]},
            "status": "$_qc_status", "date": {"$cond": [{"$eq": [{"$type": "$" + field}, "date"]}, "$" + field, None]},
            "patient_reference_state": "$_qc_patient_reference",
            "issue_eligible": "$_qc_issue_eligible",
            "date_quality": {"$switch": {"branches": [
                {"case": {"$eq": [{"$type": "$" + field}, "date"]}, "then": "valid"},
                {"case": {"$in": [{"$type": "$" + field}, ["missing", "null"]]}, "then": "missing"},
            ], "default": "invalid"}}}
        if kind == "rehab_plan":
            projection["publication_state"] = "$_qc_publication"
        metrics["items"] = selected + [{"$sort": {field: -1, "_id": -1}}, {"$skip": skip}, {"$limit": limit}] + (
            _publication_stages(versions_collection) if kind == "rehab_plan" else []) + [{"$project": projection}]
    metrics.update(scope=[{"$count": "count"}],
                   patient_references=[{"$group": {"_id": "$_qc_patient_reference", "count": {"$sum": 1}}}],
                   dates=[{"$group": {"_id": {"$type": "$" + field}, "count": {"$sum": 1}}}])
    return [{"$match": base}] + _patient_reference_stages() + [{"$facet": metrics}]

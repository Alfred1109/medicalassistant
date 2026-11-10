"""Record the outcome of a real catalog import. Retry repeats that same import."""
from datetime import datetime, timezone

from bson import ObjectId
from fastapi import HTTPException


def public_run(doc):
    return {"id": str(doc["_id"]), "kind": doc["kind"], "project_id": doc["project_id"],
            "status": doc["status"], "started_at": doc["started_at"], "finished_at": doc["finished_at"],
            "created": doc.get("created"), "existing": doc.get("existing"),
            "error_code": doc.get("error_code"), "message": doc.get("message") or ""}


async def record_run(db, *, kind, project_id, actor_id, status, started_at, created=None,
                     existing=None, error_code=None, message=""):
    document = {"_id": ObjectId(), "kind": kind, "project_id": project_id, "actor_id": actor_id,
                "status": status, "started_at": started_at, "finished_at": datetime.now(timezone.utc),
                "created": created, "existing": existing, "error_code": error_code, "message": message}
    await db.integration_runs.insert_one(document)
    return public_run(document)


async def summarize_runs(db):
    """Newest outcome per project. This does not invent a cursor the import never stored."""
    summary = {}
    for run in await list_runs(db, limit=200):
        slot = summary.setdefault(run["project_id"], {"project_id": run["project_id"], "attempts": 0,
                                                      "last_success": None, "last_failure": None})
        slot["attempts"] += 1
        if run["status"] == "succeeded" and slot["last_success"] is None:
            slot["last_success"] = run
        if run["status"] == "failed" and slot["last_failure"] is None:
            slot["last_failure"] = run
    return list(summary.values())


async def list_runs(db, limit=50):
    cursor = db.integration_runs.find({}).sort("finished_at", -1)
    rows = []
    async for row in cursor:
        rows.append(public_run(row))
        if len(rows) >= limit:
            break
    return rows


async def load_failed_import(db, run_id):
    if not ObjectId.is_valid(run_id):
        raise HTTPException(422, detail={"code": "INVALID_RUN_ID"})
    row = await db.integration_runs.find_one({"_id": ObjectId(run_id)})
    if not row:
        raise HTTPException(404, detail={"code": "RUN_NOT_FOUND"})
    if row.get("kind") != "people_import" or row.get("status") != "failed":
        raise HTTPException(409, detail={"code": "RUN_NOT_RETRYABLE"})
    return row

"""Visible clinical records that already exist locally.

Imported roster data, follow-ups and published plans are shown with their real
status. Education is text written by a clinician. Reports and voice notes are
stored for a person to review; nothing here extracts measurements or a transcript.
A clinician and a patient who both carry a source project must share that project.
"""
import hashlib
from datetime import datetime, timezone

from bson import ObjectId
from fastapi import HTTPException

from app.core.patient_access import ensure_patient_access, load_patient_doc

CLINICAL_ROLES = {"admin", "doctor", "health_manager"}
REPORT_TYPES = {"application/pdf", "image/jpeg", "image/png"}
VOICE_TYPES = {"audio/webm", "audio/ogg", "audio/wav", "audio/mp4"}
VOID_PLAN = {"cancelled", "canceled", "archived"}


def _now():
    return datetime.now(timezone.utc)


def _time_state(value):
    if value is None or value == "":
        return "missing"
    if isinstance(value, datetime):
        return "present"
    return "invalid"


async def _actor(db, actor):
    identifier = actor.id
    query = {"_id": ObjectId(identifier)} if ObjectId.is_valid(str(identifier)) else {"_id": identifier}
    return await db.users.find_one(query)


async def _patient_for(db, actor, patient_id):
    if actor.role == "patient":
        if str(actor.id) != str(patient_id):
            raise HTTPException(403, detail={"code": "PATIENT_NOT_ASSIGNED"})
        return await load_patient_doc(db, patient_id)
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
    viewer = await _actor(db, actor)
    patient_project = patient.get("source_project_id")
    viewer_project = (viewer or {}).get("source_project_id")
    if patient_project and viewer_project and patient_project != viewer_project:
        raise HTTPException(403, detail={"code": "DIFFERENT_PROJECT",
                                         "message": "患者与当前账号不属于同一个来源项目"})
    return patient


def _patient_public(patient):
    return {"id": str(patient["_id"]), "name": patient.get("name") or "",
            "source_project_id": patient.get("source_project_id"),
            "source_center_id": patient.get("source_center_id")}


async def scope_status(db, actor, patient_id):
    if actor.role == "patient" and str(actor.id) != str(patient_id):
        raise HTTPException(403, detail={"code": "PATIENT_NOT_ASSIGNED"})
    if actor.role not in CLINICAL_ROLES | {"patient"}:
        raise HTTPException(403, detail={"code": "ROLE_NOT_ALLOWED"})
    if actor.role in {"doctor", "health_manager"}:
        try:
            patient = await ensure_patient_access(db, patient_id, str(actor.id), actor.role)
        except Exception as exc:
            status_code = getattr(exc, "status_code", None)
            if status_code:
                raise HTTPException(status_code, detail={"code": getattr(exc, "error_code", "PATIENT_NOT_ASSIGNED")}) from None
            raise
    else:
        patient = await load_patient_doc(db, patient_id)
    viewer = await _actor(db, actor)
    patient_project = patient.get("source_project_id")
    viewer_project = (viewer or {}).get("source_project_id")
    comparable = bool(patient_project and viewer_project)
    same = patient_project == viewer_project if comparable else None
    return {"patient_project_id": patient_project, "viewer_project_id": viewer_project,
            "same_project": same, "clinical_access": same is not False or actor.role == "admin",
            "share_granted": False,
            "message": "跨项目共享还没有 113.44 的授权，这里不能打开其他项目的患者资料。" if same is False and actor.role != "admin"
            else "当前范围只包含这名患者已有的本地记录。"}


def _followup_view(row, now):
    status = row.get("status") or "unknown"
    void = status in {"canceled", "cancelled"}
    scheduled = _time_state(row.get("scheduled_date"))
    actual = _time_state(row.get("actual_date"))
    overdue = (not void and status in {"scheduled", "pending", "planned"}
               and isinstance(row.get("scheduled_date"), datetime) and row["scheduled_date"] < now)
    if void:
        display = "void"
    elif status == "lost":
        display = "lost"
    elif status == "overdue" or overdue:
        display = "overdue"
    elif scheduled != "present" and actual != "present":
        display = "missing_time"
    else:
        display = "recorded"
    return {"id": str(row["_id"]), "status": status, "scheduled_time": scheduled, "actual_time": actual,
            "void": void, "display_state": display}


async def portrait(db, actor, patient_id):
    patient = await _patient_for(db, actor, patient_id)
    now = _now()
    pid = str(patient["_id"])
    followups = [_followup_view(row, now) async for row in db.followup_records.find({"patient_id": pid})]
    plans = []
    async for row in db.rehab_plans.find({"patient_id": pid}):
        status = row.get("status") or "unknown"
        plans.append({"id": str(row["_id"]), "status": status, "void": status in VOID_PLAN,
                      "published": bool(row.get("published_version_id")) and status not in VOID_PLAN,
                      "published_time": _time_state(row.get("published_at"))})
    timeline = [{"kind": "followup", "id": row["id"], "state": row["display_state"]} for row in followups]
    timeline.extend({"kind": "plan", "id": row["id"], "state": "void" if row["void"] else "published" if row["published"] else "draft"}
                    for row in plans)
    async for row in db.education_assignments.find({"patient_id": pid}):
        timeline.append({"kind": "education", "id": str(row["_id"]), "state": row.get("status") or "assigned"})
    async for row in db.clinical_reports.find({"patient_id": pid}):
        timeline.append({"kind": "report", "id": str(row["_id"]), "state": row.get("review_status") or "pending"})
    async for row in db.voice_notes.find({"patient_id": pid}):
        timeline.append({"kind": "voice", "id": str(row["_id"]), "state": "not_transcribed"})
    return {"recorded_at": now, "patient": _patient_public(patient),
            "followups": followups, "plans": plans, "timeline": timeline,
            "missing_followup_time": sum(1 for row in followups if row["display_state"] == "missing_time"),
            "overdue_followups": sum(1 for row in followups if row["display_state"] == "overdue")}


async def create_material(db, actor, title, body):
    if actor.role not in CLINICAL_ROLES:
        raise HTTPException(403, detail={"code": "ROLE_NOT_ALLOWED"})
    title, body = title.strip(), body.strip()
    if not title or len(title) > 120 or not body or len(body) > 8000:
        raise HTTPException(422, detail={"code": "INVALID_MATERIAL"})
    document = {"_id": ObjectId(), "title": title, "body": body, "author_id": str(actor.id),
                "created_at": _now()}
    await db.education_materials.insert_one(document)
    return {"id": str(document["_id"]), "title": title, "body": body, "author_id": document["author_id"]}


async def list_materials(db, actor, patient_id=None):
    if actor.role == "patient":
        patient_id = str(actor.id)
    elif patient_id:
        await _patient_for(db, actor, patient_id)
    if actor.role == "patient" or patient_id:
        ids = []
        async for row in db.education_assignments.find({"patient_id": str(patient_id)}):
            ids.append(row["material_id"])
        rows = []
        for material_id in ids:
            material = await db.education_materials.find_one({"_id": ObjectId(material_id)})
            assignment = await db.education_assignments.find_one(
                {"patient_id": str(patient_id), "material_id": material_id})
            if material and assignment:
                rows.append({**_material_public(material), "assignment_id": str(assignment["_id"]),
                             "status": assignment["status"], "feedback": assignment.get("feedback") or "",
                             "guidance": assignment.get("guidance") or ""})
        return rows
    query = {} if actor.role == "admin" else {"author_id": str(actor.id)}
    return [_material_public(row) async for row in db.education_materials.find(query)]


def _material_public(row):
    return {"id": str(row["_id"]), "title": row["title"], "body": row["body"], "author_id": row["author_id"]}


async def assign_material(db, actor, material_id, patient_id):
    await _patient_for(db, actor, patient_id)
    if not ObjectId.is_valid(material_id):
        raise HTTPException(422, detail={"code": "INVALID_MATERIAL_ID"})
    material = await db.education_materials.find_one({"_id": ObjectId(material_id)})
    if not material:
        raise HTTPException(404, detail={"code": "MATERIAL_NOT_FOUND"})
    existing = await db.education_assignments.find_one({"material_id": material_id, "patient_id": str(patient_id)})
    if existing:
        return {"id": str(existing["_id"]), "status": existing["status"]}
    document = {"_id": ObjectId(), "material_id": material_id, "patient_id": str(patient_id),
                "assigned_by": str(actor.id), "status": "assigned", "feedback": "", "created_at": _now()}
    await db.education_assignments.insert_one(document)
    return {"id": str(document["_id"]), "status": "assigned"}


async def acknowledge_material(db, actor, assignment_id, feedback):
    if actor.role != "patient":
        raise HTTPException(403, detail={"code": "PATIENT_FEEDBACK_ONLY"})
    if not ObjectId.is_valid(assignment_id):
        raise HTTPException(422, detail={"code": "INVALID_ASSIGNMENT_ID"})
    feedback = (feedback or "").strip()
    if len(feedback) > 1000:
        raise HTTPException(422, detail={"code": "FEEDBACK_TOO_LONG"})
    row = await db.education_assignments.find_one({"_id": ObjectId(assignment_id), "patient_id": str(actor.id)})
    if not row:
        raise HTTPException(404, detail={"code": "ASSIGNMENT_NOT_FOUND"})
    await db.education_assignments.update_one(
        {"_id": row["_id"]}, {"$set": {"status": "read", "feedback": feedback, "read_at": _now()}})
    return {"id": assignment_id, "status": "read", "feedback": feedback}


async def guide_material(db, actor, assignment_id, guidance):
    if actor.role not in CLINICAL_ROLES:
        raise HTTPException(403, detail={"code": "ROLE_NOT_ALLOWED"})
    if not ObjectId.is_valid(assignment_id):
        raise HTTPException(422, detail={"code": "INVALID_ASSIGNMENT_ID"})
    row = await db.education_assignments.find_one({"_id": ObjectId(assignment_id)})
    if not row:
        raise HTTPException(404, detail={"code": "ASSIGNMENT_NOT_FOUND"})
    await _patient_for(db, actor, row["patient_id"])
    guidance = guidance.strip()
    if not guidance or len(guidance) > 1000:
        raise HTTPException(422, detail={"code": "INVALID_GUIDANCE"})
    await db.education_assignments.update_one(
        {"_id": row["_id"]}, {"$set": {"guidance": guidance, "guided_by": str(actor.id), "guided_at": _now()}})
    return {"id": assignment_id, "guidance": guidance}


def _store_file(kind, content_type, content, allowed, limit):
    content_type = (content_type or "").split(";", 1)[0].strip().lower()
    if content_type not in allowed:
        raise HTTPException(422, detail={"code": "UNSUPPORTED_FILE"})
    if not content or len(content) > limit:
        raise HTTPException(422, detail={"code": "INVALID_FILE_SIZE"})
    return {"content_type": content_type, "size": len(content),
            "sha256": hashlib.sha256(content).hexdigest(), "content": content, "kind": kind}


async def add_report(db, actor, patient_id, *, filename, content_type, content, report_date, stated_patient_id):
    await _patient_for(db, actor, patient_id)
    if stated_patient_id != str(patient_id):
        raise HTTPException(422, detail={"code": "PATIENT_MISMATCH"})
    if not report_date:
        raise HTTPException(422, detail={"code": "REPORT_DATE_REQUIRED"})
    try:
        parsed_date = datetime.fromisoformat(report_date)
    except ValueError:
        raise HTTPException(422, detail={"code": "INVALID_REPORT_DATE"}) from None
    stored = _store_file("report", content_type, content, REPORT_TYPES, 5 * 1024 * 1024)
    document = {"_id": ObjectId(), "patient_id": str(patient_id), "filename": (filename or "report")[:180],
                "report_date": parsed_date.date().isoformat(), "uploaded_by": str(actor.id),
                "parse_status": "not_parsed", "extracted_values": [], "review_status": "pending",
                "review_note": "", "created_at": _now(), **stored}
    document["findings"] = []
    excerpt, source = await _report_excerpt(content, stored["content_type"])
    if excerpt and source:
        document["parse_status"] = "model_suggested"
        document["findings"] = [{"label": "报告文字摘录", "value": excerpt, "unit": "", "source": source}]
    await db.clinical_reports.insert_one(document)
    return _report_public(document, include_findings=True)


async def _report_excerpt(content: bytes, content_type: str):
    if content_type == "application/pdf":
        text = await _pdf_text(content)
        if len(text) >= 20:
            return text[:800], "PDF文字层，待人工审核"
        image = await _pdf_first_page(content)
        if image:
            excerpt = await _image_excerpt(image, "image/png")
            if excerpt:
                return excerpt, "模型识别，待人工审核"
        return None, None
    if content_type in {"image/jpeg", "image/png"}:
        return await _image_excerpt(content, content_type), "模型识别，待人工审核"
    return None, None


def _run_pdf_tool(content: bytes, command: list) -> str:
    import os
    import subprocess
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".pdf") as handle:
        handle.write(content)
        handle.flush()
        rendered = [part.format(path=handle.name) if part == "{path}" else part for part in command]
        try:
            completed = subprocess.run(rendered, check=True, timeout=20, capture_output=True)
        except (OSError, subprocess.SubprocessError):
            return ""
        return completed.stdout.decode("utf-8", errors="replace").strip()


async def _pdf_text(content: bytes) -> str:
    import asyncio
    return await asyncio.to_thread(_run_pdf_tool, content, ["pdftotext", "-q", "-enc", "UTF-8", "{path}", "-"])


async def _pdf_first_page(content: bytes) -> bytes:
    import asyncio
    return await asyncio.to_thread(_pdf_first_page_sync, content)


def _pdf_first_page_sync(content: bytes) -> bytes:
    return _pdf_first_page_bytes(content)


def _pdf_first_page_bytes(content: bytes) -> bytes:
    import os
    import subprocess
    import tempfile
    with tempfile.TemporaryDirectory() as folder:
        source = os.path.join(folder, "report.pdf")
        with open(source, "wb") as handle:
            handle.write(content)
        target = os.path.join(folder, "page")
        try:
            subprocess.run(["pdftoppm", "-png", "-f", "1", "-l", "1", "-singlefile", source, target],
                           check=True, timeout=20, capture_output=True)
        except (OSError, subprocess.SubprocessError):
            return b""
        image = target + ".png"
        if not os.path.isfile(image):
            return b""
        with open(image, "rb") as handle:
            return handle.read()


async def _image_excerpt(content: bytes, content_type: str):
    """Ask the configured vision model to copy visible text. Failure leaves the report unparsed."""
    import base64
    import os
    key = os.getenv("VISION_API_KEY")
    base = os.getenv("VISION_API_BASE_URL")
    model = os.getenv("VISION_API_MODEL")
    if not key or not base or not model:
        return None
    try:
        from openai import OpenAI
        client = OpenAI(base_url=base, api_key=key)
        encoded = base64.b64encode(content).decode()
        completion = client.chat.completions.create(
            model=model,
            temperature=0,
            messages=[{"role": "user", "content": [
                {"type": "text", "text": "只摘录图片上能看清的文字，不要补充图片里没有的数值。看不清就只回复看不清。不超过800字。"},
                {"type": "image_url", "image_url": {"url": f"data:{content_type};base64,{encoded}"}},
            ]}],
        )
        text = (completion.choices[0].message.content or "").strip()
    except Exception:
        return None
    if not text or text == "看不清":
        return None
    return text[:800]


def _report_public(row, *, include_findings):
    findings = row.get("findings") or [] if include_findings else []
    return {"id": str(row["_id"]), "patient_id": row["patient_id"], "filename": row["filename"],
            "report_date": row["report_date"], "content_type": row["content_type"], "size": row["size"],
            "sha256": row["sha256"], "parse_status": row.get("parse_status") or "not_parsed", "extracted_values": [],
            "findings": [{"label": item["label"], "value": item["value"], "unit": item.get("unit") or "",
                          "source": item.get("source") or "人工阅读原件", "report_id": str(row["_id"])} for item in findings],
            "review_status": row.get("review_status") or "pending", "review_note": row.get("review_note") or ""}


def _show_findings(actor, row):
    return actor.role in CLINICAL_ROLES or row.get("review_status") == "reviewed"


async def list_reports(db, actor, patient_id):
    await _patient_for(db, actor, patient_id)
    return [_report_public(row, include_findings=_show_findings(actor, row))
            async for row in db.clinical_reports.find({"patient_id": str(patient_id)})]


async def review_report(db, actor, report_id, *, accepted, note):
    if actor.role not in CLINICAL_ROLES:
        raise HTTPException(403, detail={"code": "ROLE_NOT_ALLOWED"})
    if not ObjectId.is_valid(report_id):
        raise HTTPException(422, detail={"code": "INVALID_REPORT_ID"})
    row = await db.clinical_reports.find_one({"_id": ObjectId(report_id)})
    if not row:
        raise HTTPException(404, detail={"code": "REPORT_NOT_FOUND"})
    await _patient_for(db, actor, row["patient_id"])
    note = (note or "").strip()
    if not note:
        raise HTTPException(422, detail={"code": "REVIEW_NOTE_REQUIRED"})
    status = "reviewed" if accepted else "rejected"
    await db.clinical_reports.update_one(
        {"_id": row["_id"]}, {"$set": {"review_status": status, "review_note": note,
                                       "reviewer_id": str(actor.id), "reviewed_at": _now()}})
    row.update(review_status=status, review_note=note)
    return _report_public(row, include_findings=True)


async def add_finding(db, actor, report_id, label, value, unit):
    if actor.role not in CLINICAL_ROLES:
        raise HTTPException(403, detail={"code": "ROLE_NOT_ALLOWED"})
    if not ObjectId.is_valid(report_id):
        raise HTTPException(422, detail={"code": "INVALID_REPORT_ID"})
    row = await db.clinical_reports.find_one({"_id": ObjectId(report_id)})
    if not row:
        raise HTTPException(404, detail={"code": "REPORT_NOT_FOUND"})
    await _patient_for(db, actor, row["patient_id"])
    label, value, unit = label.strip(), value.strip(), (unit or "").strip()
    if not label or not value or len(label) > 80 or len(value) > 120 or len(unit) > 40:
        raise HTTPException(422, detail={"code": "INVALID_FINDING"})
    finding = {"label": label, "value": value, "unit": unit, "author_id": str(actor.id), "at": _now()}
    findings = list(row.get("findings") or []) + [finding]
    await db.clinical_reports.update_one({"_id": row["_id"]}, {"$set": {"findings": findings, "parse_status": "not_parsed"}})
    row["findings"] = findings
    return _report_public(row, include_findings=True)


async def report_content(db, actor, report_id):
    if not ObjectId.is_valid(report_id):
        raise HTTPException(422, detail={"code": "INVALID_REPORT_ID"})
    row = await db.clinical_reports.find_one({"_id": ObjectId(report_id)})
    if not row:
        raise HTTPException(404, detail={"code": "REPORT_NOT_FOUND"})
    await _patient_for(db, actor, row["patient_id"])
    return row


async def add_voice(db, actor, patient_id, *, content_type, content, consent):
    await _patient_for(db, actor, patient_id)
    if consent is not True:
        raise HTTPException(422, detail={"code": "VOICE_CONSENT_REQUIRED"})
    stored = _store_file("voice", content_type, content, VOICE_TYPES, 2 * 1024 * 1024)
    document = {"_id": ObjectId(), "patient_id": str(patient_id), "recorded_by": str(actor.id),
                "consent": True, "transcription_status": "not_transcribed", "transcript": None,
                "created_at": _now(), **stored}
    await db.voice_notes.insert_one(document)
    return _voice_public(document)


def _voice_public(row):
    return {"id": str(row["_id"]), "patient_id": row["patient_id"], "content_type": row["content_type"],
            "size": row["size"], "transcription_status": row.get("transcription_status") or "not_transcribed",
            "transcript": row.get("transcript")}


async def write_transcript(db, actor, voice_id, text):
    """Store words a person typed after listening. This is not automatic speech recognition."""
    if not ObjectId.is_valid(voice_id):
        raise HTTPException(422, detail={"code": "INVALID_VOICE_ID"})
    row = await db.voice_notes.find_one({"_id": ObjectId(voice_id)})
    if not row:
        raise HTTPException(404, detail={"code": "VOICE_NOT_FOUND"})
    await _patient_for(db, actor, row["patient_id"])
    text = text.strip()
    if not text or len(text) > 2000:
        raise HTTPException(422, detail={"code": "INVALID_TRANSCRIPT"})
    await db.voice_notes.update_one(
        {"_id": row["_id"]},
        {"$set": {"transcript": text, "transcription_status": "manual", "transcript_by": str(actor.id),
                  "transcribed_at": _now()}})
    row.update(transcript=text, transcription_status="manual")
    return _voice_public(row)


async def list_voice(db, actor, patient_id):
    await _patient_for(db, actor, patient_id)
    notes = [_voice_public(row) async for row in db.voice_notes.find({"patient_id": str(patient_id)})]
    events = [{"id": str(row["_id"]), "kind": row["kind"], "at": row["created_at"]}
              async for row in db.voice_events.find({"patient_id": str(patient_id)})]
    return {"notes": notes, "events": events}


async def record_voice_event(db, actor, patient_id, kind):
    await _patient_for(db, actor, patient_id)
    if kind != "permission_denied":
        raise HTTPException(422, detail={"code": "UNSUPPORTED_VOICE_EVENT"})
    document = {"_id": ObjectId(), "patient_id": str(patient_id), "actor_id": str(actor.id),
                "kind": kind, "created_at": _now()}
    await db.voice_events.insert_one(document)
    return {"id": str(document["_id"]), "kind": kind}


async def request_share(db, actor, patient_id, target_project_id, reason):
    if actor.role not in CLINICAL_ROLES:
        raise HTTPException(403, detail={"code": "ROLE_NOT_ALLOWED"})
    patient = await _patient_for(db, actor, patient_id)
    if patient.get("source_project_id") == target_project_id:
        raise HTTPException(422, detail={"code": "SAME_PROJECT"})
    reason = reason.strip()
    if not reason:
        raise HTTPException(422, detail={"code": "REASON_REQUIRED"})
    document = {"_id": ObjectId(), "patient_id": str(patient["_id"]), "source_project_id": patient.get("source_project_id"),
                "target_project_id": target_project_id, "reason": reason, "requested_by": str(actor.id),
                "status": "pending_source_authorization", "created_at": _now()}
    await db.share_requests.insert_one(document)
    return _share_public(document)


def _share_public(row):
    return {"id": str(row["_id"]), "patient_id": row["patient_id"], "target_project_id": row["target_project_id"],
            "status": row["status"], "reason": row["reason"], "access_granted": False}


async def list_shares(db, actor, patient_id):
    await _patient_for(db, actor, patient_id)
    return [_share_public(row) async for row in db.share_requests.find({"patient_id": str(patient_id)})]


async def withdraw_share(db, actor, request_id):
    if not ObjectId.is_valid(request_id):
        raise HTTPException(422, detail={"code": "INVALID_SHARE_ID"})
    row = await db.share_requests.find_one({"_id": ObjectId(request_id), "status": "pending_source_authorization"})
    if not row:
        raise HTTPException(404, detail={"code": "SHARE_NOT_PENDING"})
    if actor.role != "admin" and row.get("requested_by") != str(actor.id):
        raise HTTPException(403, detail={"code": "ROLE_NOT_ALLOWED"})
    await _patient_for(db, actor, row["patient_id"])
    await db.share_requests.update_one({"_id": row["_id"]}, {"$set": {"status": "withdrawn", "withdrawn_at": _now()}})
    row["status"] = "withdrawn"
    return _share_public(row)


async def voice_content(db, actor, voice_id):
    if not ObjectId.is_valid(voice_id):
        raise HTTPException(422, detail={"code": "INVALID_VOICE_ID"})
    row = await db.voice_notes.find_one({"_id": ObjectId(voice_id)})
    if not row:
        raise HTTPException(404, detail={"code": "VOICE_NOT_FOUND"})
    await _patient_for(db, actor, row["patient_id"])
    return row


def indicator_status():
    return {"configured": False, "indicators": [],
            "message": "临床指标字典尚未确认，这里不计算达标率、ICF 评分或正式质控报告。"}

from fastapi import APIRouter, Depends, File, Form, Response, UploadFile
from fastapi.responses import PlainTextResponse, Response as BinaryResponse
from pydantic import BaseModel, ConfigDict, Field

from app.core.auth import get_current_active_user
from app.db.mongodb import get_database
from . import workspace

router = APIRouter(prefix="/clinical", tags=["clinical-workspace"])


class MaterialRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    title: str
    body: str


class AssignmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    material_id: str = Field(min_length=24, max_length=24)
    patient_id: str = Field(min_length=1, max_length=32)


class FeedbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    feedback: str = ""


class GuidanceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    guidance: str = Field(min_length=1, max_length=1000)


class FindingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    label: str = Field(min_length=1, max_length=80)
    value: str = Field(min_length=1, max_length=120)
    unit: str = ""


class ShareRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target_project_id: int = Field(gt=0)
    reason: str = Field(min_length=1, max_length=500)


class IndicatorRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    label: str = Field(min_length=1, max_length=80)
    source_label: str = Field(min_length=1, max_length=80)
    unit: str = ""
    low: float | None = None
    high: float | None = None
    icf_code: str = ""


class VoiceEventRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: str


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    accepted: bool
    note: str = Field(min_length=1, max_length=2000)


def _file(response: Response):
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"


@router.get("/indicators")
async def indicators(response: Response, _=Depends(get_current_active_user), db=Depends(get_database)):
    _file(response)
    return await workspace.dictionary_status(db)


@router.post("/indicators", status_code=201)
async def add_indicator(payload: IndicatorRequest, response: Response, actor=Depends(get_current_active_user),
                        db=Depends(get_database)):
    _file(response)
    return await workspace.create_indicator(db, actor, label=payload.label, source_label=payload.source_label,
                                           unit=payload.unit, low=payload.low, high=payload.high,
                                           icf_code=payload.icf_code)


@router.post("/indicators/{rule_id}/retire")
async def retire_indicator(rule_id: str, response: Response, actor=Depends(get_current_active_user),
                           db=Depends(get_database)):
    _file(response)
    return await workspace.retire_indicator(db, actor, rule_id)


@router.get("/patients/{patient_id}/indicators")
async def patient_indicators(patient_id: str, response: Response, actor=Depends(get_current_active_user),
                             db=Depends(get_database)):
    _file(response)
    return await workspace.evaluate_indicators(db, actor, patient_id)


@router.get("/patients/{patient_id}/indicators.csv")
async def patient_indicators_csv(patient_id: str, actor=Depends(get_current_active_user), db=Depends(get_database)):
    result = await workspace.evaluate_indicators(db, actor, patient_id)
    return PlainTextResponse(workspace.indicators_csv(result), media_type="text/csv; charset=utf-8",
                             headers={"Cache-Control": "no-store", "Content-Disposition": "attachment; filename=indicators.csv"})


@router.get("/patients/{patient_id}/recorded-plan")
async def recorded_plan(patient_id: str, response: Response, actor=Depends(get_current_active_user),
                        db=Depends(get_database)):
    _file(response)
    return await workspace.recorded_plan_sources(db, actor, patient_id)


@router.get("/patients/{patient_id}/scope")
async def patient_scope(patient_id: str, response: Response, actor=Depends(get_current_active_user),
                        db=Depends(get_database)):
    _file(response)
    return await workspace.scope_status(db, actor, patient_id)


@router.get("/patients/{patient_id}/portrait")
async def patient_portrait(patient_id: str, response: Response, actor=Depends(get_current_active_user),
                           db=Depends(get_database)):
    _file(response)
    return await workspace.portrait(db, actor, patient_id)


@router.get("/education")
async def education(response: Response, patient_id: str | None = None, actor=Depends(get_current_active_user),
                    db=Depends(get_database)):
    _file(response)
    return {"materials": await workspace.list_materials(db, actor, patient_id)}


@router.post("/education", status_code=201)
async def create_education(payload: MaterialRequest, response: Response, actor=Depends(get_current_active_user),
                           db=Depends(get_database)):
    _file(response)
    return await workspace.create_material(db, actor, payload.title, payload.body)


@router.post("/education/assignments", status_code=201)
async def create_assignment(payload: AssignmentRequest, response: Response, actor=Depends(get_current_active_user),
                            db=Depends(get_database)):
    _file(response)
    return await workspace.assign_material(db, actor, payload.material_id, payload.patient_id)


@router.post("/education/assignments/{assignment_id}/read")
async def read_assignment(assignment_id: str, payload: FeedbackRequest, response: Response,
                          actor=Depends(get_current_active_user), db=Depends(get_database)):
    _file(response)
    return await workspace.acknowledge_material(db, actor, assignment_id, payload.feedback)


@router.post("/education/assignments/{assignment_id}/guidance")
async def assignment_guidance(assignment_id: str, payload: GuidanceRequest, response: Response,
                              actor=Depends(get_current_active_user), db=Depends(get_database)):
    _file(response)
    return await workspace.guide_material(db, actor, assignment_id, payload.guidance)


@router.get("/patients/{patient_id}/reports")
async def reports(patient_id: str, response: Response, actor=Depends(get_current_active_user),
                  db=Depends(get_database)):
    _file(response)
    return {"reports": await workspace.list_reports(db, actor, patient_id)}


@router.post("/patients/{patient_id}/reports", status_code=201)
async def upload_report(patient_id: str, response: Response, report_date: str = Form(...),
                        stated_patient_id: str = Form(...), file: UploadFile = File(...),
                        actor=Depends(get_current_active_user), db=Depends(get_database)):
    _file(response)
    content = await file.read()
    return await workspace.add_report(db, actor, patient_id, filename=file.filename or "report",
                                      content_type=file.content_type or "", content=content,
                                      report_date=report_date, stated_patient_id=stated_patient_id)


@router.post("/reports/{report_id}/review")
async def report_review(report_id: str, payload: ReviewRequest, response: Response,
                        actor=Depends(get_current_active_user), db=Depends(get_database)):
    _file(response)
    return await workspace.review_report(db, actor, report_id, accepted=payload.accepted, note=payload.note)


@router.post("/reports/{report_id}/findings", status_code=201)
async def report_finding(report_id: str, payload: FindingRequest, response: Response,
                         actor=Depends(get_current_active_user), db=Depends(get_database)):
    _file(response)
    return await workspace.add_finding(db, actor, report_id, payload.label, payload.value, payload.unit)


@router.get("/reports/{report_id}/content")
async def download_report(report_id: str, actor=Depends(get_current_active_user), db=Depends(get_database)):
    row = await workspace.report_content(db, actor, report_id)
    return BinaryResponse(row["content"], media_type=row["content_type"],
                          headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


@router.get("/patients/{patient_id}/voice")
async def voice_notes(patient_id: str, response: Response, actor=Depends(get_current_active_user),
                      db=Depends(get_database)):
    _file(response)
    return await workspace.list_voice(db, actor, patient_id)


@router.post("/patients/{patient_id}/voice-events", status_code=201)
async def voice_event(patient_id: str, payload: VoiceEventRequest, response: Response,
                      actor=Depends(get_current_active_user), db=Depends(get_database)):
    _file(response)
    return await workspace.record_voice_event(db, actor, patient_id, payload.kind)


@router.post("/patients/{patient_id}/voice", status_code=201)
async def upload_voice(patient_id: str, response: Response, file: UploadFile = File(...),
                       consent: str = Form(""), browser_transcript: str = Form(""),
                       actor=Depends(get_current_active_user), db=Depends(get_database)):
    _file(response)
    return await workspace.add_voice(db, actor, patient_id, content_type=file.content_type or "",
                                     content=await file.read(), consent=consent == "true",
                                     browser_transcript=browser_transcript)


@router.get("/patients/{patient_id}/shares")
async def shares(patient_id: str, response: Response, actor=Depends(get_current_active_user),
                 db=Depends(get_database)):
    _file(response)
    return {"requests": await workspace.list_shares(db, actor, patient_id)}


@router.post("/patients/{patient_id}/shares", status_code=201)
async def create_share(patient_id: str, payload: ShareRequest, response: Response,
                       actor=Depends(get_current_active_user), db=Depends(get_database)):
    _file(response)
    return await workspace.request_share(db, actor, patient_id, payload.target_project_id, payload.reason)


@router.post("/shares/{request_id}/withdraw")
async def withdraw(request_id: str, response: Response, actor=Depends(get_current_active_user),
                   db=Depends(get_database)):
    _file(response)
    return await workspace.withdraw_share(db, actor, request_id)


class TranscriptWrite(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    text: str = Field(min_length=1, max_length=2000)


@router.post("/voice/{voice_id}/transcript")
async def transcript(voice_id: str, payload: TranscriptWrite, response: Response,
                     actor=Depends(get_current_active_user), db=Depends(get_database)):
    _file(response)
    return await workspace.write_transcript(db, actor, voice_id, payload.text)


@router.get("/voice/{voice_id}/content")
async def download_voice(voice_id: str, actor=Depends(get_current_active_user), db=Depends(get_database)):
    row = await workspace.voice_content(db, actor, voice_id)
    return BinaryResponse(row["content"], media_type=row["content_type"],
                          headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})

from fastapi import APIRouter, Depends, Response
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, ConfigDict, Field

from app.core.auth import get_current_active_user
from app.db.mongodb import get_database
from .records import (
    create_template, issue_consent, list_consents, list_templates, read_consent, read_preferences,
    save_preferences, sign_consent,
)

router = APIRouter(tags=["directory"])


class TemplateWrite(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    title: str = Field(min_length=1, max_length=120)
    body: str = Field(min_length=1, max_length=20000)


class IssueWrite(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    template_id: str = Field(min_length=24, max_length=24)
    patient_id: str = Field(min_length=1, max_length=32)


class SignatureWrite(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    signed_name: str = ""
    accepted: bool


class PreferenceWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ui: dict | None = None
    notifications: dict | None = None


def _private(response: Response):
    response.headers["Cache-Control"] = "no-store"


@router.get("/consent/templates")
async def templates(response: Response, actor=Depends(get_current_active_user), db=Depends(get_database)):
    _private(response)
    return {"templates": await list_templates(db)}


@router.post("/consent/templates", status_code=201)
async def add_template(payload: TemplateWrite, response: Response, actor=Depends(get_current_active_user),
                       db=Depends(get_database)):
    _private(response)
    return await create_template(db, actor, payload.title, payload.body)


@router.get("/consent/documents")
async def documents(response: Response, patient_id: str | None = None, actor=Depends(get_current_active_user),
                    db=Depends(get_database)):
    _private(response)
    return {"documents": await list_consents(db, actor, patient_id)}


@router.post("/consent/documents", status_code=201)
async def add_document(payload: IssueWrite, response: Response, actor=Depends(get_current_active_user),
                       db=Depends(get_database)):
    _private(response)
    return await issue_consent(db, actor, payload.template_id, payload.patient_id)


@router.get("/consent/documents/{document_id}")
async def document(document_id: str, response: Response, actor=Depends(get_current_active_user),
                   db=Depends(get_database)):
    _private(response)
    row = await read_consent(db, actor, document_id)
    return {"id": str(row["_id"]), "title": row["title"], "body": row["body"], "status": row["status"],
            "patient_id": row["patient_id"], "signed_name": row.get("signed_name") or ""}


@router.post("/consent/documents/{document_id}/signature")
async def signature(document_id: str, payload: SignatureWrite, response: Response,
                    actor=Depends(get_current_active_user), db=Depends(get_database)):
    _private(response)
    return await sign_consent(db, actor, document_id, payload.signed_name, payload.accepted)


@router.get("/consent/documents/{document_id}/text")
async def document_text(document_id: str, actor=Depends(get_current_active_user), db=Depends(get_database)):
    row = await read_consent(db, actor, document_id)
    signed = row.get("signed_name") or "未签署"
    text = f"{row['title']}\n\n{row['body']}\n\n状态：{row['status']}\n签署姓名：{signed}\n"
    return PlainTextResponse(text, headers={"Cache-Control": "no-store"})


@router.get("/settings/me")
async def my_settings(response: Response, actor=Depends(get_current_active_user), db=Depends(get_database)):
    _private(response)
    return await read_preferences(db, actor.id)


@router.put("/settings/me")
async def update_my_settings(payload: PreferenceWrite, response: Response, actor=Depends(get_current_active_user),
                             db=Depends(get_database)):
    _private(response)
    return await save_preferences(db, actor.id, ui=payload.ui, notifications=payload.notifications)

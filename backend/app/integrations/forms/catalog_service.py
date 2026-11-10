"""Read-only machine-granted catalog for reviewed local administrators.

This is not a delegation mechanism for clinicians. No patient, account or
binding is created here; every response is reduced to its documented fields.
"""
from typing import Annotated, Literal, Optional

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .client import AuthorizationRejected, FormPlatformClient, FormPlatformError, FormPlatformUnavailable

PositiveId = Annotated[int, Field(strict=True, gt=0, le=9223372036854775807)]
ShortText = Annotated[str, Field(strict=True, max_length=512)]


class RemoteModel(BaseModel):
    model_config = ConfigDict(extra="ignore")


class Source(RemoteModel):
    system: Literal["form-platform-11344"]
    environment: Literal["pilot", "production"]


class Page(RemoteModel):
    limit: Annotated[int, Field(strict=True, ge=1, le=200)]
    has_more: Annotated[bool, Field(strict=True)]
    next_cursor: Optional[Annotated[str, Field(strict=True, min_length=1, max_length=2048,
                                               pattern=r"^[A-Za-z0-9_-]+={0,2}$")]] = None


class Project(RemoteModel):
    project_id: PositiveId
    name: ShortText
    status: ShortText
    source: Source


class Center(RemoteModel):
    center_id: PositiveId
    project_id: PositiveId
    name: ShortText
    center_code: ShortText
    status: ShortText


class Subject(RemoteModel):
    subject_id: PositiveId
    project_id: PositiveId
    center_id: Optional[PositiveId]
    code: ShortText
    status: Literal["screening", "enrolled", "completed", "withdrawn"]


class FormVersion(RemoteModel):
    form_id: PositiveId
    family_id: PositiveId
    version: Annotated[int, Field(strict=True, ge=1)]
    version_state: ShortText
    definition_sha256: Optional[Annotated[str, Field(strict=True, pattern=r"^[0-9a-f]{64}$")]] = None
    crf_code: Optional[ShortText] = None
    crf_version: Optional[ShortText] = None


class Form(RemoteModel):
    form_id: PositiveId
    project_id: Optional[PositiveId]
    title: ShortText
    status: Literal["draft", "active", "closed"]
    current_version: Optional[FormVersion]


class RosterPerson(RemoteModel):
    person_key: Annotated[str, Field(strict=True, pattern=r"^(patient|user):[1-9][0-9]{0,18}$")]
    kind: Literal["subject", "member"]
    display_name: Annotated[str, Field(strict=True, max_length=100)]
    project_id: PositiveId
    source: Source
    subject_id: Optional[PositiveId] = None
    center_id: Optional[PositiveId] = None
    subject_code: Optional[ShortText] = None
    subject_status: Optional[Literal["screening", "enrolled", "completed", "withdrawn"]] = None
    source_patient_id: Optional[PositiveId] = None
    source_user_id: Optional[PositiveId] = None
    oidc_subject: Optional[Annotated[str, Field(strict=True, min_length=1, max_length=64)]] = None
    source_roles: list[Annotated[str, Field(strict=True, max_length=50)]] = Field(default_factory=list, max_length=20)


class PatientReference(RemoteModel):
    source: Source
    project_id: PositiveId
    center_id: PositiveId
    subject_id: PositiveId
    patient_id: PositiveId
    patient_archive_id: PositiveId


def _invalid_response():
    return HTTPException(502, detail={"error": "FORM_PLATFORM_INVALID_RESPONSE",
                                      "message": "表单平台目录响应不符合约定"})


async def _fetch(call):
    try:
        return await call
    except AuthorizationRejected:
        raise HTTPException(502, detail={"error": "FORM_PLATFORM_AUTH_REJECTED",
                                         "message": "表单平台拒绝了集成授权"}) from None
    except FormPlatformUnavailable:
        raise HTTPException(502, detail={"error": "FORM_PLATFORM_UNAVAILABLE",
                                         "message": "表单平台暂时不可用"}) from None
    except FormPlatformError as exc:
        status = exc.status_code if exc.status_code in {400, 404, 409, 422, 429} else 502
        raise HTTPException(status, detail={"error": "FORM_PLATFORM_CATALOG_REJECTED",
                                            "message": "表单平台未能返回该目录资源"}) from None


def _page(body, model, *, limit, project_id=None, center_id=None):
    try:
        if not isinstance(body, dict) or not isinstance(body.get("data"), list) or len(body["data"]) > limit:
            raise ValueError()
        page = Page.model_validate(body["page"])
        if page.limit != limit or page.has_more != bool(page.next_cursor):
            raise ValueError()
        rows = [model.model_validate(item) for item in body["data"]]
        for row in rows:
            if project_id is not None and row.project_id != project_id:
                raise ValueError()
            if center_id is not None and row.center_id != center_id:
                raise ValueError()
            if isinstance(row, Form) and row.current_version and row.current_version.form_id != row.form_id:
                raise ValueError()
        return {"data": [row.model_dump() for row in rows], "page": page.model_dump()}
    except (ValidationError, ValueError, KeyError, TypeError):
        raise _invalid_response() from None


async def projects(client: FormPlatformClient, *, limit=50, cursor=None):
    return _page(await _fetch(client.list_projects(limit=limit, cursor=cursor)), Project, limit=limit)


async def centers(client: FormPlatformClient, project_id: int, *, limit=50, cursor=None):
    return _page(await _fetch(client.list_centers(project_id, limit=limit, cursor=cursor)), Center,
                 limit=limit, project_id=project_id)


async def subjects(client: FormPlatformClient, project_id: int, *, center_id=None, status="all", limit=50, cursor=None):
    return _page(await _fetch(client.list_subjects(project_id, center_id=center_id, status=status,
                                                  limit=limit, cursor=cursor)), Subject,
                 limit=limit, project_id=project_id, center_id=center_id)


def _check_person(row: RosterPerson, project_id: int):
    prefix, number = row.person_key.split(":", 1)
    if row.project_id != project_id:
        raise ValueError()
    if row.kind == "subject":
        if prefix != "patient" or row.source_patient_id != int(number) or row.subject_id is None:
            raise ValueError()
        if row.source_user_id is not None or row.source_roles:
            raise ValueError()
    elif prefix != "user" or row.source_user_id != int(number) or row.subject_id is not None:
        raise ValueError()


async def people(client: FormPlatformClient, project_id: int, *, limit=50, cursor=None):
    body = await _fetch(client.list_people(project_id, limit=limit, cursor=cursor))
    try:
        if not isinstance(body, dict) or not isinstance(body.get("data"), list) or len(body["data"]) > limit:
            raise ValueError()
        page = Page.model_validate(body["page"])
        if page.limit != limit or page.has_more != bool(page.next_cursor):
            raise ValueError()
        rows = [RosterPerson.model_validate(item) for item in body["data"]]
        for row in rows:
            _check_person(row, project_id)
        return {"data": [row.model_dump() for row in rows], "page": page.model_dump()}
    except (ValidationError, ValueError, KeyError, TypeError):
        raise _invalid_response() from None


async def forms(client: FormPlatformClient, project_id: int, *, status="active", limit=50, cursor=None):
    return _page(await _fetch(client.list_forms(project_id, status=status, limit=limit, cursor=cursor)), Form,
                 limit=limit, project_id=project_id)


async def patient_reference(client: FormPlatformClient, project_id: int, center_id: int, subject_id: int):
    body = await _fetch(client.get_patient_reference(project_id, center_id, subject_id))
    try:
        result = PatientReference.model_validate(body)
        if (result.project_id, result.center_id, result.subject_id) != (project_id, center_id, subject_id):
            raise ValueError()
        return result.model_dump()
    except (ValidationError, ValueError, TypeError):
        raise _invalid_response() from None


async def form_version(client: FormPlatformClient, project_id: int, form_id: int, *, version=None):
    try:
        body = await _fetch(client.get_form_definition(form_id, version=version))
    except HTTPException as exc:
        if exc.status_code == 409:
            raise HTTPException(409, detail={"error": "FORM_DEFINITION_NOT_PUBLISHED",
                                             "message": "该问卷尚无可绑定的已发布定义版本"}) from None
        raise
    try:
        if not isinstance(body, dict):
            raise ValueError()
        source = Source.model_validate(body["source"])
        form = Form.model_validate(body["form"])
        published = FormVersion.model_validate(body["version"])
        if (form.form_id != form_id or form.project_id != project_id
                or published.form_id != form_id or form.current_version != published
                or (version is not None and published.version != version)):
            raise ValueError()
        if form.status != "active" or published.version_state != "current" or not published.definition_sha256:
            raise HTTPException(409, detail={"error": "FORM_DEFINITION_NOT_PUBLISHED",
                                             "message": "该问卷尚无可绑定的已发布定义版本"})
        return {"source": source.model_dump(), "form": form.model_dump(), "version": published.model_dump()}
    except (ValidationError, ValueError, KeyError, TypeError):
        raise _invalid_response() from None

"""Administrator-only directory reader; no mutation or frontend actor claims."""
from datetime import datetime, timezone
from typing import Literal, Optional
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, Response

from pydantic import BaseModel, ConfigDict, Field, StrictBool

from app.core.auth import get_current_active_user
from app.db.mongodb import get_database
from .client import FormPlatformClient, FormPlatformError
from . import catalog_service as service
from .people_import import assign_imported_role, import_project_people, list_imported_people, set_imported_care
from .sync_runs import list_runs, load_failed_import, record_run, summarize_runs

router = APIRouter(prefix="/integrations/forms/catalog", tags=["form-catalog"])
MAX_ID = 9223372036854775807


async def require_catalog_admin(current_user=Depends(get_current_active_user)):
    if current_user.role != "admin":
        raise HTTPException(403, detail={"error": "FORM_CATALOG_ADMIN_REQUIRED",
                                         "message": "源目录仅供管理员核实关联"})
    return current_user


def get_catalog_client():
    try:
        client = FormPlatformClient.from_settings()
        origin = urlsplit(client.source_origin)
    except FormPlatformError:
        raise HTTPException(503, detail={"error": "FORM_PLATFORM_NOT_CONFIGURED",
                                         "message": "表单平台目录集成尚未配置"}) from None
    # Administrative patient references require real TLS; never inherit the
    # old pilot transport override or follow a configured HTTP endpoint.
    if (not client._client_id or not client._client_secret
            or origin.scheme != "https" or not origin.hostname or origin.username or origin.password
            or origin.query or origin.fragment or not client._verify_tls):
        raise HTTPException(503, detail={"error": "FORM_PLATFORM_CONFIGURATION_INVALID",
                                         "message": "表单平台目录需要受信任的 HTTPS 配置"})
    return client


def _query(request, response, allowed):
    if any(key not in allowed or len(request.query_params.getlist(key)) != 1 for key in request.query_params):
        raise HTTPException(422, detail={"error": "INVALID_CATALOG_PARAMETERS",
                                         "message": "目录查询含未知或重复参数"})
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"


@router.get("/projects")
async def projects(request: Request, response: Response,
                   limit: int = Query(50, ge=1, le=200),
                   cursor: Optional[str] = Query(None, min_length=1, max_length=2048, pattern=r"^[A-Za-z0-9_-]+={0,2}$"),
                   _=Depends(require_catalog_admin), client=Depends(get_catalog_client)):
    _query(request, response, {"limit", "cursor"})
    return await service.projects(client, limit=limit, cursor=cursor)


@router.get("/projects/{project_id}/centers")
async def centers(request: Request, response: Response, project_id: int = Path(gt=0, le=MAX_ID),
                  limit: int = Query(50, ge=1, le=200),
                  cursor: Optional[str] = Query(None, min_length=1, max_length=2048, pattern=r"^[A-Za-z0-9_-]+={0,2}$"),
                  _=Depends(require_catalog_admin), client=Depends(get_catalog_client)):
    _query(request, response, {"limit", "cursor"})
    return await service.centers(client, project_id, limit=limit, cursor=cursor)


@router.get("/projects/{project_id}/subjects")
async def subjects(request: Request, response: Response, project_id: int = Path(gt=0, le=MAX_ID),
                   center_id: Optional[int] = Query(None, gt=0, le=MAX_ID),
                   status: Literal["all", "screening", "enrolled", "completed", "withdrawn"] = "all",
                   limit: int = Query(50, ge=1, le=200),
                   cursor: Optional[str] = Query(None, min_length=1, max_length=2048, pattern=r"^[A-Za-z0-9_-]+={0,2}$"),
                   _=Depends(require_catalog_admin), client=Depends(get_catalog_client)):
    _query(request, response, {"limit", "cursor", "center_id", "status"})
    return await service.subjects(client, project_id, center_id=center_id, status=status, limit=limit, cursor=cursor)


@router.get("/projects/{project_id}/forms")
async def forms(request: Request, response: Response, project_id: int = Path(gt=0, le=MAX_ID),
                status: Literal["active", "closed", "all"] = "active",
                limit: int = Query(50, ge=1, le=200),
                cursor: Optional[str] = Query(None, min_length=1, max_length=2048, pattern=r"^[A-Za-z0-9_-]+={0,2}$"),
                _=Depends(require_catalog_admin), client=Depends(get_catalog_client)):
    _query(request, response, {"limit", "cursor", "status"})
    return await service.forms(client, project_id, status=status, limit=limit, cursor=cursor)


@router.get("/projects/{project_id}/centers/{center_id}/subjects/{subject_id}/patient-reference")
async def patient_reference(request: Request, response: Response,
                            project_id: int = Path(gt=0, le=MAX_ID), center_id: int = Path(gt=0, le=MAX_ID),
                            subject_id: int = Path(gt=0, le=MAX_ID),
                            _=Depends(require_catalog_admin), client=Depends(get_catalog_client)):
    _query(request, response, set())
    return await service.patient_reference(client, project_id, center_id, subject_id)


@router.get("/projects/{project_id}/forms/{form_id}/version")
async def form_version(request: Request, response: Response,
                       project_id: int = Path(gt=0, le=MAX_ID), form_id: int = Path(gt=0, le=MAX_ID),
                       version: Optional[int] = Query(None, gt=0, le=MAX_ID),
                       _=Depends(require_catalog_admin), client=Depends(get_catalog_client)):
    _query(request, response, {"version"})
    return await service.form_version(client, project_id, form_id, version=version)


class ImportedRoleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    role: str = Field(pattern=r"^(unassigned|patient|doctor|health_manager)$")
    evidence_reference: str = Field(min_length=1, max_length=256)


class ImportedCareRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    practitioner_id: str = Field(min_length=24, max_length=24)
    assigned: StrictBool
    evidence_reference: str = Field(min_length=1, max_length=256)


@router.get("/projects/{project_id}/people")
async def imported_people(request: Request, response: Response, project_id: int = Path(gt=0, le=MAX_ID),
                          _=Depends(require_catalog_admin), client=Depends(get_catalog_client),
                          db=Depends(get_database)):
    _query(request, response, set())
    return {"people": await list_imported_people(db, client.source_origin, project_id)}


async def _import_and_record(db, client, actor, project_id):
    started = datetime.now(timezone.utc)
    try:
        result = await import_project_people(db, client, actor, project_id)
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, dict) else {}
        await record_run(db, kind="people_import", project_id=project_id, actor_id=str(actor.id),
                         status="failed", started_at=started, error_code=detail.get("code") or "IMPORT_FAILED",
                         message=detail.get("message") or "")
        raise
    run = await record_run(db, kind="people_import", project_id=project_id, actor_id=str(actor.id),
                           status="succeeded", started_at=started, created=result["created"],
                           existing=result["existing"])
    return {**result, "run": run}


@router.post("/projects/{project_id}/people/import")
async def import_people(request: Request, response: Response, project_id: int = Path(gt=0, le=MAX_ID),
                        actor=Depends(require_catalog_admin), client=Depends(get_catalog_client),
                        db=Depends(get_database)):
    _query(request, response, set())
    return await _import_and_record(db, client, actor, project_id)


@router.get("/runs/summary")
async def integration_summary(request: Request, response: Response, _=Depends(require_catalog_admin),
                              db=Depends(get_database)):
    _query(request, response, set())
    return {"projects": await summarize_runs(db)}


@router.get("/runs")
async def integration_runs(request: Request, response: Response, _=Depends(require_catalog_admin),
                           db=Depends(get_database)):
    _query(request, response, set())
    return {"runs": await list_runs(db)}


@router.post("/runs/{run_id}/retry")
async def retry_integration_run(request: Request, response: Response, run_id: str,
                                actor=Depends(require_catalog_admin), client=Depends(get_catalog_client),
                                db=Depends(get_database)):
    _query(request, response, set())
    failed = await load_failed_import(db, run_id)
    return await _import_and_record(db, client, actor, failed["project_id"])


@router.post("/people/{user_id}/role")
async def imported_role(request: Request, response: Response, payload: ImportedRoleRequest, user_id: str,
                        actor=Depends(require_catalog_admin), db=Depends(get_database)):
    _query(request, response, set())
    return await assign_imported_role(db, actor, user_id, payload.role, payload.evidence_reference)


@router.post("/people/{user_id}/care")
async def imported_care(request: Request, response: Response, payload: ImportedCareRequest, user_id: str,
                        actor=Depends(require_catalog_admin), db=Depends(get_database)):
    _query(request, response, set())
    return await set_imported_care(db, actor, user_id, payload.practitioner_id,
                                   assigned=payload.assigned, evidence_reference=payload.evidence_reference)

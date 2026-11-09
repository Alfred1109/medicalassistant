"""Administrator-only directory reader; no mutation or frontend actor claims."""
from typing import Literal, Optional
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, Response

from app.core.auth import get_current_active_user
from .client import FormPlatformClient, FormPlatformError
from . import catalog_service as service

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

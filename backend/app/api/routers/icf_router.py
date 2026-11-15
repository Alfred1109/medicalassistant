"""ICF 评估域路由（T71）：类目字典、结构化评估、指标与预警、正式报告。

授权：写入/计算/审核仅限临床角色（admin/doctor/health_manager）；患者角色
仅可读取本人已审核数据；对象级授权在 icf_service 经内核 ensure_patient_access。
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Response
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, ConfigDict, Field

from app.core.auth import get_current_active_user
from app.db.mongodb import get_database
from app.services import icf_service

router = APIRouter(prefix="/icf", tags=["icf"])


def _no_store(response: Response):
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"


# ---------------- 类目字典 ----------------

class IcfCategoryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    code: str = Field(min_length=1, max_length=20)
    name: str = Field(min_length=1, max_length=80)
    domain: str
    description: str = Field(default="", max_length=500)


class IcfCategoryUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: Optional[str] = Field(default=None, max_length=80)
    domain: Optional[str] = None
    description: Optional[str] = Field(default=None, max_length=500)
    enabled: Optional[bool] = None


@router.get("/categories")
async def categories(response: Response, _=Depends(get_current_active_user),
                     db=Depends(get_database)):
    _no_store(response)
    return await icf_service.list_categories(db, _)


@router.post("/categories", status_code=201)
async def create_category(payload: IcfCategoryCreate, response: Response,
                          actor=Depends(get_current_active_user), db=Depends(get_database)):
    _no_store(response)
    return await icf_service.create_category(db, actor, code=payload.code, name=payload.name,
                                             domain=payload.domain, description=payload.description)


@router.put("/categories/{category_id}")
async def update_category(category_id: str, payload: IcfCategoryUpdate, response: Response,
                          actor=Depends(get_current_active_user), db=Depends(get_database)):
    _no_store(response)
    return await icf_service.update_category(db, actor, category_id, name=payload.name,
                                             domain=payload.domain,
                                             description=payload.description,
                                             enabled=payload.enabled)


# ---------------- 结构化评估 ----------------

class IcfItemPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(min_length=1, max_length=20)
    qualifier: Any
    note: str = Field(default="", max_length=500)


class IcfAssessmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    items: List[IcfItemPayload] = Field(min_length=1)
    source: str = "manual"
    source_ref: str = Field(default="", max_length=120)
    assessed_at: Optional[datetime] = None
    note: str = Field(default="", max_length=2000)


class IcfAssessmentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    items: List[IcfItemPayload] = Field(min_length=1)
    note: str = Field(default="", max_length=2000)
    expected_version: int = Field(ge=0, strict=True)


class IcfAssessmentReview(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    accepted: bool
    note: str = Field(min_length=1, max_length=2000)
    expected_version: int = Field(ge=0, strict=True)


@router.post("/patients/{patient_id}/assessments", status_code=201)
async def create_assessment(patient_id: str, payload: IcfAssessmentCreate, response: Response,
                            actor=Depends(get_current_active_user), db=Depends(get_database)):
    _no_store(response)
    return await icf_service.create_assessment(
        db, actor, patient_id, items=[item.model_dump() for item in payload.items],
        source=payload.source, source_ref=payload.source_ref,
        assessed_at=payload.assessed_at, note=payload.note)


@router.get("/patients/{patient_id}/assessments")
async def list_assessments(patient_id: str, response: Response,
                           actor=Depends(get_current_active_user), db=Depends(get_database)):
    _no_store(response)
    return await icf_service.list_assessments(db, actor, patient_id)


@router.get("/assessments/{assessment_id}")
async def get_assessment(assessment_id: str, response: Response,
                         actor=Depends(get_current_active_user), db=Depends(get_database)):
    _no_store(response)
    return await icf_service.get_assessment(db, actor, assessment_id)


@router.put("/assessments/{assessment_id}")
async def update_assessment(assessment_id: str, payload: IcfAssessmentUpdate, response: Response,
                            actor=Depends(get_current_active_user), db=Depends(get_database)):
    _no_store(response)
    return await icf_service.update_assessment(
        db, actor, assessment_id, items=[item.model_dump() for item in payload.items],
        note=payload.note, expected_version=payload.expected_version)


@router.post("/assessments/{assessment_id}/review")
async def review_assessment(assessment_id: str, payload: IcfAssessmentReview, response: Response,
                            actor=Depends(get_current_active_user), db=Depends(get_database)):
    _no_store(response)
    return await icf_service.review_assessment(db, actor, assessment_id,
                                               accepted=payload.accepted, note=payload.note,
                                               expected_version=payload.expected_version)


# ---------------- 指标定义与计算 ----------------

class IcfMetricConfigUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: Optional[bool] = None
    params: Optional[Dict[str, Any]] = None


@router.get("/metric-configs")
async def metric_configs(response: Response, _=Depends(get_current_active_user),
                         db=Depends(get_database)):
    _no_store(response)
    return await icf_service.list_metric_configs(db)


@router.put("/metric-configs/{metric_key}")
async def update_metric_config(metric_key: str, payload: IcfMetricConfigUpdate, response: Response,
                               actor=Depends(get_current_active_user), db=Depends(get_database)):
    _no_store(response)
    return await icf_service.update_metric_config(db, actor, metric_key,
                                                  enabled=payload.enabled, params=payload.params)


@router.get("/patients/{patient_id}/metrics")
async def patient_metrics(patient_id: str, response: Response,
                          actor=Depends(get_current_active_user), db=Depends(get_database)):
    _no_store(response)
    return await icf_service.compute_patient_metrics(db, actor, patient_id)


@router.post("/patients/{patient_id}/metrics/evaluate")
async def evaluate_metrics(patient_id: str, response: Response,
                           actor=Depends(get_current_active_user), db=Depends(get_database)):
    _no_store(response)
    return await icf_service.evaluate_metrics_and_alert(db, actor, patient_id)


# ---------------- 正式报告 ----------------

class IcfReportGenerate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    assessment_id: str = Field(min_length=24, max_length=24)


class IcfReportReview(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    accepted: bool
    note: str = Field(min_length=1, max_length=2000)
    expected_version: int = Field(ge=0, strict=True)


@router.post("/patients/{patient_id}/reports", status_code=201)
async def generate_report(patient_id: str, payload: IcfReportGenerate, response: Response,
                          actor=Depends(get_current_active_user), db=Depends(get_database)):
    _no_store(response)
    return await icf_service.generate_report(db, actor, patient_id, payload.assessment_id)


@router.get("/patients/{patient_id}/reports")
async def list_reports(patient_id: str, response: Response,
                       actor=Depends(get_current_active_user), db=Depends(get_database)):
    _no_store(response)
    return await icf_service.list_reports(db, actor, patient_id)


@router.get("/reports/{report_id}")
async def get_report(report_id: str, response: Response,
                     actor=Depends(get_current_active_user), db=Depends(get_database)):
    _no_store(response)
    return await icf_service.get_report(db, actor, report_id)


@router.post("/reports/{report_id}/review")
async def review_report(report_id: str, payload: IcfReportReview, response: Response,
                        actor=Depends(get_current_active_user), db=Depends(get_database)):
    _no_store(response)
    return await icf_service.review_icf_report(db, actor, report_id, accepted=payload.accepted,
                                               note=payload.note,
                                               expected_version=payload.expected_version)


@router.get("/reports/{report_id}/export.json")
async def export_report_json(report_id: str, actor=Depends(get_current_active_user),
                             db=Depends(get_database)):
    row = await icf_service.load_report_for_export(db, actor, report_id)
    export = icf_service.export_report_json(row)
    return JSONResponse(export, headers={"Cache-Control": "no-store",
                                         "Content-Disposition": f'attachment; filename="icf-report-{report_id}.json"'})


@router.get("/reports/{report_id}/export.html")
async def export_report_html(report_id: str, actor=Depends(get_current_active_user),
                             db=Depends(get_database)):
    row = await icf_service.load_report_for_export(db, actor, report_id)
    html = icf_service.export_report_html(row)
    return PlainTextResponse(html, media_type="text/html; charset=utf-8",
                             headers={"Cache-Control": "no-store",
                                      "Content-Disposition": f'inline; filename="icf-report-{report_id}.html"',
                                      "X-Content-Type-Options": "nosniff"})

"""显式账号绑定管理端点（T64，canonical 患者域波次 6）。

为「无账号临床患者」提供人工核实后的登录账号绑定/解绑工作流：
管理员核实账号与临床患者的真实对应关系后，建立带独立
`explicit_binding` origin 的 verified `patient_account_links` 链接
（reviewer + evidence + 时间审计齐全）；患者以该账号登录后
`resolve_self` 打通自助通路。

权限形态与 system_admin_router 的账号管理一致：仅 admin（管理端点，
操作对象是全局账号关系，非归属范围语义）。仓储语义（互斥、停用状态机、
fail-closed 校验）全部委托 patients/repository，本文件不建立第二套写路径。

注意：本路由尚未挂载到 app.main（挂载属于接线批次，需在 main.py 增加
include_router(prefix="/api")）；端点契约由
tests/test_patient_account_binding_api.py 以独立 FastAPI 应用覆盖。
"""
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.auth import get_current_active_user
from app.db.mongodb import get_database
from app.patients.repository import ClinicalPatientRepository, PatientDomainError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/patients/account-bindings", tags=["patient-account-bindings"])


def _private_response(response: Response):
    # 绑定关系属敏感管理数据：禁止缓存/落 Referer。
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"


class AccountBindingCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    patient_id: str = Field(min_length=1, max_length=64)
    account_id: str = Field(min_length=24, max_length=24)
    reviewer: str = Field(min_length=1, max_length=200)
    evidence_reference: str = Field(min_length=1, max_length=1024)

    @field_validator("patient_id")
    @classmethod
    def require_patient_id(cls, value):
        if not value.strip():
            raise ValueError("patient_id is required")
        return value


class AccountBindingDisable(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    reviewer: str = Field(min_length=1, max_length=200)
    evidence_reference: str = Field(min_length=1, max_length=1024)


class AccountBindingResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    patient_id: str
    account_id: str
    status: str
    source: str
    reviewer: str | None = None
    evidence_reference: str | None = None
    bound_at: datetime | None = None
    disabled_at: datetime | None = None


def _binding_response(document) -> AccountBindingResponse:
    # audit 为创建时的单条审计 dict；停用后为追加式 list（最近一条在末尾）。
    audit = document.get("audit") or {}
    if isinstance(audit, list):
        audit = audit[-1] if audit else {}
    return AccountBindingResponse(
        patient_id=document["patient_id"], account_id=document["account_id"],
        status=document["status"], source=document["source"],
        reviewer=audit.get("reviewer"), evidence_reference=audit.get("evidence_reference"),
        bound_at=document.get("bound_at"), disabled_at=document.get("disabled_at"))


# PatientDomainError → HTTP：与仓储错误语义一一对应，fail-closed 错误
# （域状态不可用/索引缺失）如实 503，不降级为 500 或静默空响应。
_BINDING_ERROR_STATUS = {
    "PATIENT_REVIEW_REQUIRED": 422,
    "INVALID_PATIENT_REVIEW_REFERENCE": 422,
    "INVALID_PATIENT_ACCOUNT": 422,
    "PATIENT_NOT_FOUND": 404,
    "PATIENT_ACCOUNT_LINK_NOT_FOUND": 404,
    "PATIENT_ACCOUNT_LINK_CONFLICT": 409,
    "PATIENT_DOMAIN_NOT_MIGRATED": 503,
    "PATIENT_DOMAIN_STATE_UNAVAILABLE": 503,
    "PATIENT_DOMAIN_INDEX_MISSING": 503,
    "PATIENT_DOMAIN_INDEX_CHECK_FAILED": 503,
}


def _require_admin(current_user) -> None:
    if getattr(current_user, "role", None) != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")


def _map_domain_error(error: PatientDomainError) -> HTTPException:
    code = getattr(error, "code", "PATIENT_DOMAIN_ERROR")
    return HTTPException(status_code=_BINDING_ERROR_STATUS.get(code, 500),
                         detail={"error": code, "message": str(error)})


@router.post("", status_code=status.HTTP_201_CREATED,
             response_model=AccountBindingResponse,
             dependencies=[Depends(_private_response)])
async def create_account_binding(payload: AccountBindingCreate,
                                 current_user=Depends(get_current_active_user),
                                 db=Depends(get_database)):
    """为临床患者显式绑定登录账号（人工核实后；审计必填）。

    互斥语义：患者或账号已有任意 origin 的链接（含已停用）一律 409，
    不做隐式替换；停用链接为终态文档，重新绑定走人工核实对账流程。
    """
    _require_admin(current_user)
    try:
        link = await ClinicalPatientRepository(db).bind_account(
            payload.patient_id, account_id=payload.account_id,
            reviewer=payload.reviewer, evidence_reference=payload.evidence_reference)
    except PatientDomainError as error:
        raise _map_domain_error(error) from None
    except Exception as e:
        logger.error(f"创建患者账号绑定失败: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail={"error": "PATIENT_ACCOUNT_BINDING_FAILED",
                                    "message": "创建患者账号绑定失败"}) from None
    return _binding_response(link)


@router.post("/{patient_id}/disable", response_model=AccountBindingResponse,
             dependencies=[Depends(_private_response)])
async def disable_account_binding(patient_id: str, payload: AccountBindingDisable,
                                  current_user=Depends(get_current_active_user),
                                  db=Depends(get_database)):
    """停用患者的显式账号链接（复用 verified→disabled 状态机；不删除、不复活）。"""
    _require_admin(current_user)
    try:
        link = await ClinicalPatientRepository(db).disable_account_link(
            patient_id, reviewer=payload.reviewer,
            evidence_reference=payload.evidence_reference)
    except PatientDomainError as error:
        raise _map_domain_error(error) from None
    except Exception as e:
        logger.error(f"停用患者账号绑定失败: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail={"error": "PATIENT_ACCOUNT_BINDING_FAILED",
                                    "message": "停用患者账号绑定失败"}) from None
    return _binding_response(link)

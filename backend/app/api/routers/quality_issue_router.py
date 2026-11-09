"""Manual quality issue lifecycle; every object is patient-scoped."""
from bson import ObjectId
from fastapi import APIRouter, Depends, Query, Response

from app.core.auth import get_current_active_user
from app.db.mongodb import get_database
from app.schemas.quality_issue import (AssignQualityIssue, ConfirmQualityIssue, IssueStatus,
    QualityIssueCreate, ResolveQualityIssue, ReviewQualityIssue)
from app.services.quality_issue_service import QualityIssueService


def private(response: Response):
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"


router = APIRouter(prefix="/quality/issues", tags=["人工质控问题"], dependencies=[Depends(private)])


def service(db=Depends(get_database)):
    return QualityIssueService(db)


@router.get("/assignees")
async def assignees(patient_id: str = Query(pattern=r"^[a-fA-F0-9]{24}$"),
                    actor=Depends(get_current_active_user), svc=Depends(service)):
    return await svc.assignees(str(ObjectId(patient_id)), actor)


@router.get("")
async def list_issues(patient_id: str | None = Query(None, pattern=r"^[a-fA-F0-9]{24}$"),
                      status: IssueStatus | None = Query(None),
                      assignee_id: str | None = Query(None, pattern=r"^[a-fA-F0-9]{24}$"),
                      skip: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100),
                      actor=Depends(get_current_active_user), svc=Depends(service)):
    return await svc.list(actor, patient_id=str(ObjectId(patient_id)) if patient_id else None,
        status=status, assignee_id=str(ObjectId(assignee_id)) if assignee_id else None, skip=skip, limit=limit)


@router.post("")
async def create_issue(payload: QualityIssueCreate, response: Response,
                       actor=Depends(get_current_active_user), svc=Depends(service)):
    result, created = await svc.create(payload, actor)
    response.status_code = 201 if created else 200
    return result


@router.get("/{issue_id}")
async def issue_detail(issue_id: str, actor=Depends(get_current_active_user), svc=Depends(service)):
    return await svc.detail(issue_id, actor)


@router.post("/{issue_id}/assign")
async def assign_issue(issue_id: str, payload: AssignQualityIssue,
                       actor=Depends(get_current_active_user), svc=Depends(service)):
    return await svc.mutate(issue_id, "assign", payload, actor)


@router.post("/{issue_id}/confirm")
async def confirm_issue(issue_id: str, payload: ConfirmQualityIssue,
                        actor=Depends(get_current_active_user), svc=Depends(service)):
    return await svc.mutate(issue_id, "confirm", payload, actor)


@router.post("/{issue_id}/resolve")
async def resolve_issue(issue_id: str, payload: ResolveQualityIssue,
                        actor=Depends(get_current_active_user), svc=Depends(service)):
    return await svc.mutate(issue_id, "resolve", payload, actor)


@router.post("/{issue_id}/review")
async def review_issue(issue_id: str, payload: ReviewQualityIssue,
                       actor=Depends(get_current_active_user), svc=Depends(service)):
    return await svc.mutate(issue_id, "review", payload, actor)

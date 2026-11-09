"""Explicit clinical publication and strictly projected patient reads."""
from fastapi import APIRouter, Depends, Query, Response
from app.core.auth import get_current_active_user
from app.db.mongodb import get_database
from app.schemas.rehab_publication import SavePublicationDraft, PublishDraft, WithdrawPublication
from app.services.rehab_publication_service import RehabPublicationService


def private(response: Response):
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"


router = APIRouter(prefix="/rehabilitation/publications", tags=["康复方案发布"],
                   dependencies=[Depends(private)])


def service(db=Depends(get_database)):
    return RehabPublicationService(db)


@router.get("/my-plans")
async def my_plans(skip: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100),
                   actor=Depends(get_current_active_user), svc=Depends(service)):
    return await svc.patient_list(actor, skip=skip, limit=limit)


@router.get("/my-plans/{plan_id}")
async def patient_plan(plan_id: str, actor=Depends(get_current_active_user), svc=Depends(service)):
    return await svc.patient_detail(plan_id, actor)


@router.get("/plans/{plan_id}/draft")
async def draft(plan_id: str, actor=Depends(get_current_active_user), svc=Depends(service)):
    return await svc.draft(plan_id, actor)


@router.put("/plans/{plan_id}/draft")
async def save_draft(plan_id: str, payload: SavePublicationDraft,
                     actor=Depends(get_current_active_user), svc=Depends(service)):
    return await svc.save_draft(plan_id, actor, payload)


@router.post("/plans/{plan_id}/publish")
async def publish(plan_id: str, payload: PublishDraft,
                  actor=Depends(get_current_active_user), svc=Depends(service)):
    return await svc.publish(plan_id, actor, payload)


@router.post("/plans/{plan_id}/withdraw")
async def withdraw(plan_id: str, payload: WithdrawPublication,
                   actor=Depends(get_current_active_user), svc=Depends(service)):
    return await svc.withdraw(plan_id, actor, payload)

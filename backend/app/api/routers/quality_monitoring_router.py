"""Authorized current process facts and honest CSV reports."""
from datetime import datetime
from fastapi import APIRouter, Depends, Query, Response
from app.core.auth import get_current_active_user
from app.db.mongodb import get_database
from app.schemas.quality_monitoring import QualityProcessOverview, QualityProcessPage
from app.services.quality_monitoring_service import QualityMonitoringService, process_csv


def private(response: Response):
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"


router = APIRouter(prefix="/quality-monitoring", tags=["康复过程质控"], dependencies=[Depends(private)])


def service(db=Depends(get_database)):
    return QualityMonitoringService(db)


@router.get("/overview", response_model=QualityProcessOverview)
async def overview(patient_id: str | None = Query(None, min_length=1, max_length=128),
                   start_date: datetime | None = None, end_date: datetime | None = None,
                   actor=Depends(get_current_active_user), svc=Depends(service)):
    return await svc.overview(actor, patient_id=patient_id, start_date=start_date, end_date=end_date)


@router.get("/followups", response_model=QualityProcessPage)
async def followups(patient_id: str | None = Query(None, min_length=1, max_length=128),
                    start_date: datetime | None = None, end_date: datetime | None = None,
                    skip: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100),
                    actor=Depends(get_current_active_user), svc=Depends(service)):
    return await svc.details("followup", actor, patient_id=patient_id,
        start_date=start_date, end_date=end_date, skip=skip, limit=limit)


@router.get("/plans", response_model=QualityProcessPage)
async def plans(patient_id: str | None = Query(None, min_length=1, max_length=128),
                start_date: datetime | None = None, end_date: datetime | None = None,
                skip: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100),
                actor=Depends(get_current_active_user), svc=Depends(service)):
    return await svc.details("rehab_plan", actor, patient_id=patient_id,
        start_date=start_date, end_date=end_date, skip=skip, limit=limit)


@router.get("/report.csv")
async def report(patient_id: str | None = Query(None, min_length=1, max_length=128),
                 start_date: datetime | None = None, end_date: datetime | None = None,
                 actor=Depends(get_current_active_user), svc=Depends(service)):
    result = await svc.overview(actor, patient_id=patient_id, start_date=start_date, end_date=end_date)
    return Response(process_csv(result, patient_id), media_type="text/csv; charset=utf-8",
        headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer",
                 "Content-Disposition": 'attachment; filename="quality-process-report.csv"'})

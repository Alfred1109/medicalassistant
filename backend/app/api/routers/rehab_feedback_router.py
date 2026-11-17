"""Patient feedback is separate from editing or publishing clinical plans."""
from fastapi import APIRouter, Depends, File, Query, Response, UploadFile
from fastapi.responses import FileResponse

from app.core.auth import get_current_active_user
from app.db.mongodb import get_database
from app.schemas.rehab_feedback import (ClinicalFeedbackReview, FeedbackAttachment,
    PatientFeedbackCreate, PatientFeedbackPage, PatientFeedbackResult, PatientFeedbackSupplement)
from app.schemas.rehab_training_cycle import (TrainingCycleAcceptance, TrainingCycleCreate,
    TrainingCycleUpdate)
from app.services.rehab_feedback_service import RehabFeedbackService
from app.services.rehab_training_cycle_service import RehabTrainingCycleService

router = APIRouter(prefix="/rehabilitation/plans", tags=["康复执行反馈"])


def private(response):
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"


@router.post("/{plan_id}/patient-feedback", response_model=PatientFeedbackResult)
async def submit_patient_feedback(plan_id: str, payload: PatientFeedbackCreate, response: Response,
                                  actor=Depends(get_current_active_user), db=Depends(get_database)):
    result = await RehabFeedbackService(db).submit(plan_id, payload, actor)
    private(response)
    response.status_code = 201 if result.created else 200
    return result


@router.get("/{plan_id}/patient-feedback", response_model=PatientFeedbackPage)
async def list_patient_feedback(plan_id: str, response: Response,
                               version_id: str | None = Query(None, pattern=r"^[0-9a-fA-F]{24}$"),
                               prescription_item_id: str | None = Query(None, pattern=r"^[0-9a-fA-F]{24}$"),
                               skip: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100),
                               actor=Depends(get_current_active_user), db=Depends(get_database)):
    result = await RehabFeedbackService(db).list(plan_id, actor, version_id=version_id,
        prescription_item_id=prescription_item_id, skip=skip, limit=limit)
    private(response)
    return result


@router.post("/{plan_id}/patient-feedback/media", response_model=FeedbackAttachment)
async def upload_feedback_media(plan_id: str, response: Response, file: UploadFile = File(...),
                                actor=Depends(get_current_active_user), db=Depends(get_database)):
    saved = await RehabFeedbackService(db).save_media(
        plan_id, actor, await file.read(), file.content_type or "", file.filename or "附件")
    private(response)
    return saved


@router.get("/{plan_id}/patient-feedback/media/{media_id}")
async def read_feedback_media(plan_id: str, media_id: str,
                              actor=Depends(get_current_active_user), db=Depends(get_database)):
    path, content_type = await RehabFeedbackService(db).open_media(plan_id, media_id, actor)
    result = FileResponse(path, media_type=content_type)
    result.headers["Cache-Control"] = "no-store"
    result.headers["Referrer-Policy"] = "no-referrer"
    return result


@router.post("/{plan_id}/patient-feedback/{feedback_id}/review")
async def review_patient_feedback(plan_id: str, feedback_id: str, payload: ClinicalFeedbackReview,
                                  response: Response, actor=Depends(get_current_active_user),
                                  db=Depends(get_database)):
    result = await RehabFeedbackService(db).review(plan_id, feedback_id, payload, actor)
    private(response)
    return result


@router.post("/{plan_id}/patient-feedback/{feedback_id}/supplements")
async def supplement_patient_feedback(plan_id: str, feedback_id: str, payload: PatientFeedbackSupplement,
                                      response: Response, actor=Depends(get_current_active_user),
                                      db=Depends(get_database)):
    result = await RehabFeedbackService(db).supplement(plan_id, feedback_id, payload, actor)
    private(response)
    response.status_code = 201 if result["created"] else 200
    return result


@router.get("/{plan_id}/training-cycles")
async def list_training_cycles(plan_id: str, response: Response,
                               actor=Depends(get_current_active_user), db=Depends(get_database)):
    result = await RehabTrainingCycleService(db).list(plan_id, actor)
    private(response)
    return result


@router.post("/{plan_id}/training-cycles")
async def create_training_cycle(plan_id: str, payload: TrainingCycleCreate, response: Response,
                               actor=Depends(get_current_active_user), db=Depends(get_database)):
    result = await RehabTrainingCycleService(db).create(plan_id, actor, payload)
    private(response)
    response.status_code = 201 if result["created"] else 200
    return result


@router.put("/{plan_id}/training-cycles/{cycle_id}")
async def update_training_cycle(plan_id: str, cycle_id: str, payload: TrainingCycleUpdate,
                                response: Response, actor=Depends(get_current_active_user),
                                db=Depends(get_database)):
    result = await RehabTrainingCycleService(db).update(plan_id, cycle_id, actor, payload)
    private(response)
    return result


@router.post("/{plan_id}/training-cycles/{cycle_id}/acceptance")
async def accept_training_cycle(plan_id: str, cycle_id: str, payload: TrainingCycleAcceptance,
                                response: Response, actor=Depends(get_current_active_user),
                                db=Depends(get_database)):
    result = await RehabTrainingCycleService(db).accept(plan_id, cycle_id, actor, payload)
    private(response)
    return result

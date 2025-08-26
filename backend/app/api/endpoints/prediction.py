from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Body
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.db.mongodb import get_database
from app.services.prediction_service import PredictionService
from app.services.multimodal_service import MultimodalAnalysisService
from app.core.dependencies import get_current_user
from app.models.user import User

router = APIRouter()

@router.post("/rehab/predict")
async def predict_rehab_outcome(
    patient_id: str = Body(...),
    plan_id: str = Body(...),
    prediction_days: int = Body(30),
    method: str = Body("ensemble"),
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: User = Depends(get_current_user)
):
    """
    预测康复效果
    
    根据患者的历史评估数据预测未来康复效果
    """
    prediction_service = PredictionService(db)
    result = await prediction_service.predict_rehab_outcome(
        patient_id, 
        plan_id, 
        prediction_days, 
        method
    )
    
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("message", "预测失败"))
    
    return result

@router.get("/rehab/predictions/{prediction_id}")
async def get_prediction(
    prediction_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: User = Depends(get_current_user)
):
    """获取预测结果详情"""
    prediction_service = PredictionService(db)
    prediction = await prediction_service.get_prediction_by_id(prediction_id)
    
    if not prediction:
        raise HTTPException(status_code=404, detail="预测结果不存在")
    
    return prediction

@router.get("/rehab/predictions/patient/{patient_id}")
async def list_patient_predictions(
    patient_id: str,
    plan_id: Optional[str] = None,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: User = Depends(get_current_user)
):
    """获取患者的所有预测结果"""
    prediction_service = PredictionService(db)
    predictions = await prediction_service.list_patient_predictions(patient_id, plan_id)
    
    return predictions

@router.post("/rehab/predictions/compare")
async def compare_predicted_vs_actual(
    prediction_id: str = Body(...),
    assessment_id: str = Body(...),
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: User = Depends(get_current_user)
):
    """比较预测结果和实际评估结果"""
    prediction_service = PredictionService(db)
    result = await prediction_service.compare_predicted_vs_actual(prediction_id, assessment_id)
    
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("message", "比较失败"))
    
    return result

@router.post("/analysis/multimodal")
async def analyze_multimodal_data(
    patient_id: str = Body(...),
    analysis_type: str = Body("comprehensive"),
    start_date: Optional[str] = Body(None),
    end_date: Optional[str] = Body(None),
    data_sources: Optional[List[str]] = Body(None),
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: User = Depends(get_current_user)
):
    """
    执行多模态数据分析
    
    analysis_type 可选值: comprehensive, correlation, trend, pattern
    data_sources 可选值: devices, assessments, exercises, health_records
    """
    from datetime import datetime, timedelta
    
    # 处理日期
    if end_date:
        end_date_obj = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
    else:
        end_date_obj = datetime.utcnow()
        
    if start_date:
        start_date_obj = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
    else:
        start_date_obj = end_date_obj - timedelta(days=90)  # 默认90天
    
    multimodal_service = MultimodalAnalysisService(db)
    result = await multimodal_service.analyze_multimodal_data(
        patient_id,
        analysis_type,
        start_date_obj,
        end_date_obj,
        data_sources
    )
    
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("message", "分析失败"))
    
    return result

@router.get("/analysis/multimodal/{analysis_id}")
async def get_multimodal_analysis(
    analysis_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: User = Depends(get_current_user)
):
    """获取多模态分析结果详情"""
    multimodal_service = MultimodalAnalysisService(db)
    analysis = await multimodal_service.get_analysis_by_id(analysis_id)
    
    if not analysis:
        raise HTTPException(status_code=404, detail="分析结果不存在")
    
    return analysis

@router.get("/analysis/multimodal/patient/{patient_id}")
async def list_patient_analyses(
    patient_id: str,
    analysis_type: Optional[str] = None,
    limit: int = 10,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: User = Depends(get_current_user)
):
    """获取患者的分析历史"""
    multimodal_service = MultimodalAnalysisService(db)
    analyses = await multimodal_service.list_patient_analyses(patient_id, analysis_type, limit)
    
    return analyses

@router.post("/analysis/multimodal/{analysis_id}/integrate")
async def integrate_medical_records(
    analysis_id: str,
    medical_records: List[dict] = Body(...),
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: User = Depends(get_current_user)
):
    """整合医疗记录到现有分析中"""
    multimodal_service = MultimodalAnalysisService(db)
    result = await multimodal_service.integrate_medical_records(
        current_user.id, 
        analysis_id, 
        medical_records
    )
    
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("message", "整合失败"))
    
    return result 
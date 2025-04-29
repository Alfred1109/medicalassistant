from fastapi import APIRouter, Depends, HTTPException, status, Body, Path, Query
from typing import List, Dict, Any, Optional
from datetime import datetime

from app.schemas.rehabilitation import (
    RehabPlanCreate, 
    RehabPlanUpdate, 
    RehabPlanResponse,
    ExerciseCreate,
    ExerciseResponse,
    AssessmentCreate,
    AssessmentUpdate,
    AssessmentResponse
)
from app.services.rehabilitation_service import RehabilitationService
from app.core.dependencies import get_rehabilitation_service

router = APIRouter()

# LLM生成相关路由
@router.post("/plans/generate", response_model=Dict[str, Any])
async def generate_rehab_plan(
    data: Dict[str, Any],
    rehab_service: RehabilitationService = Depends(get_rehabilitation_service)
):
    """使用LLM生成康复计划"""
    required_fields = ["patient_id", "patient_name", "condition", "goal"]
    for field in required_fields:
        if field not in data:
            raise HTTPException(
                status_code=400, 
                detail=f"Missing required field: {field}"
            )
    
    plan = await rehab_service.generate_rehab_plan_with_llm(
        patient_id=data["patient_id"],
        patient_name=data["patient_name"],
        condition=data["condition"],
        goal=data["goal"]
    )
    
    if "error" in plan:
        raise HTTPException(status_code=500, detail=plan["error"])
        
    return plan

@router.post("/plans/{plan_id}/approve", response_model=Dict[str, Any])
async def approve_generated_plan(
    plan_id: str,
    modifications: Optional[Dict[str, Any]] = None,
    rehab_service: RehabilitationService = Depends(get_rehabilitation_service)
):
    """审核并确认LLM生成的康复计划"""
    approved_plan = await rehab_service.approve_generated_plan(plan_id, modifications)
    
    if not approved_plan:
        raise HTTPException(
            status_code=404,
            detail="Plan not found or approval failed"
        )
        
    return approved_plan

# 康复计划相关路由
@router.post("/plans", response_model=Dict[str, Any])
async def create_rehab_plan(
    plan_data: RehabPlanCreate,
    rehab_service: RehabilitationService = Depends(get_rehabilitation_service)
):
    """Create a new rehabilitation plan"""
    return await rehab_service.create_rehab_plan(plan_data)

@router.get("/plans/{plan_id}", response_model=Dict[str, Any])
async def get_rehab_plan(
    plan_id: str = Path(..., description="The ID of the rehabilitation plan"),
    rehab_service: RehabilitationService = Depends(get_rehabilitation_service)
):
    """Get a specific rehabilitation plan by ID"""
    plan = await rehab_service.get_rehab_plan(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Rehabilitation plan not found")
    return plan

@router.put("/plans/{plan_id}", response_model=Dict[str, Any])
async def update_rehab_plan(
    plan_data: RehabPlanUpdate,
    plan_id: str = Path(..., description="The ID of the rehabilitation plan"),
    rehab_service: RehabilitationService = Depends(get_rehabilitation_service)
):
    """Update an existing rehabilitation plan"""
    updated_plan = await rehab_service.update_rehab_plan(plan_id, plan_data)
    if not updated_plan:
        raise HTTPException(status_code=404, detail="Rehabilitation plan not found")
    return updated_plan

@router.delete("/plans/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rehab_plan(
    plan_id: str = Path(..., description="The ID of the rehabilitation plan"),
    rehab_service: RehabilitationService = Depends(get_rehabilitation_service)
):
    """Delete a rehabilitation plan"""
    success = await rehab_service.delete_rehab_plan(plan_id)
    if not success:
        raise HTTPException(status_code=404, detail="Rehabilitation plan not found")

@router.get("/plans", response_model=List[Dict[str, Any]])
async def list_rehab_plans(
    patient_id: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    rehab_service: RehabilitationService = Depends(get_rehabilitation_service)
):
    """List all rehabilitation plans with optional filtering by patient"""
    return await rehab_service.list_rehab_plans(patient_id, skip, limit)

@router.post("/plans/{plan_id}/exercises", response_model=Dict[str, Any])
async def add_exercises_to_plan(
    plan_id: str,
    exercise_data: Dict[str, List[str]],
    rehab_service: RehabilitationService = Depends(get_rehabilitation_service)
):
    """Add exercises to a rehabilitation plan"""
    exercise_ids = exercise_data.get("exercise_ids", [])
    updated_plan = await rehab_service.add_exercises_to_plan(plan_id, exercise_ids)
    
    if not updated_plan:
        raise HTTPException(status_code=404, detail="Rehabilitation plan not found")
    
    return updated_plan

# 运动相关路由
@router.post("/exercises", response_model=Dict[str, Any])
async def create_exercise(
    exercise_data: ExerciseCreate,
    rehab_service: RehabilitationService = Depends(get_rehabilitation_service)
):
    """Create a new rehabilitation exercise"""
    return await rehab_service.create_exercise(exercise_data)

@router.get("/exercises/recommendations", response_model=List[Dict[str, Any]])
async def get_exercise_recommendations(
    patient_id: str,
    condition: Optional[str] = None,
    goal: Optional[str] = None,
    agent_id: Optional[str] = None,
    rehab_service: RehabilitationService = Depends(get_rehabilitation_service)
):
    """Get personalized rehabilitation exercise recommendations"""
    return await rehab_service.get_recommendations(patient_id, condition, goal, agent_id)

# 康复评估相关路由
@router.post("/assessments", response_model=Dict[str, Any])
async def create_assessment(
    assessment_data: AssessmentCreate,
    rehab_service: RehabilitationService = Depends(get_rehabilitation_service)
):
    """创建新的康复评估记录"""
    return await rehab_service.create_assessment(assessment_data)

@router.get("/assessments/{assessment_id}", response_model=Dict[str, Any])
async def get_assessment(
    assessment_id: str = Path(..., description="康复评估记录ID"),
    rehab_service: RehabilitationService = Depends(get_rehabilitation_service)
):
    """获取康复评估记录详情"""
    assessment = await rehab_service.get_assessment(assessment_id)
    if not assessment:
        raise HTTPException(status_code=404, detail="康复评估记录不存在")
    return assessment

@router.put("/assessments/{assessment_id}", response_model=Dict[str, Any])
async def update_assessment(
    assessment_data: AssessmentUpdate,
    assessment_id: str = Path(..., description="康复评估记录ID"),
    rehab_service: RehabilitationService = Depends(get_rehabilitation_service)
):
    """更新康复评估记录"""
    updated_assessment = await rehab_service.update_assessment(assessment_id, assessment_data)
    if not updated_assessment:
        raise HTTPException(status_code=404, detail="康复评估记录不存在")
    return updated_assessment

@router.get("/patients/{patient_id}/assessments", response_model=List[Dict[str, Any]])
async def list_patient_assessments(
    patient_id: str = Path(..., description="患者ID"),
    plan_id: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    skip: int = 0,
    limit: int = 100,
    rehab_service: RehabilitationService = Depends(get_rehabilitation_service)
):
    """获取患者的康复评估记录列表"""
    return await rehab_service.list_patient_assessments(
        patient_id=patient_id,
        plan_id=plan_id,
        start_date=start_date,
        end_date=end_date,
        skip=skip,
        limit=limit
    )

@router.get("/assessments/{assessment_id}/comparison", response_model=Dict[str, Any])
async def get_assessment_comparison(
    assessment_id: str = Path(..., description="康复评估记录ID"),
    patient_id: str = Query(..., description="患者ID"),
    rehab_service: RehabilitationService = Depends(get_rehabilitation_service)
):
    """比较当前评估与前一次评估的差异"""
    comparison = await rehab_service.get_assessment_comparison(patient_id, assessment_id)
    if "error" in comparison:
        raise HTTPException(status_code=404, detail=comparison["error"])
    return comparison

@router.post("/assessments/{assessment_id}/analyze", response_model=Dict[str, Any])
async def generate_assessment_analysis(
    assessment_id: str = Path(..., description="康复评估记录ID"),
    patient_id: str = Query(..., description="患者ID"),
    plan_id: Optional[str] = None,
    rehab_service: RehabilitationService = Depends(get_rehabilitation_service)
):
    """使用LLM解释康复评估结果并提供建议"""
    analysis = await rehab_service.generate_assessment_with_llm(
        patient_id=patient_id,
        plan_id=plan_id,
        previous_assessment_id=assessment_id
    )
    
    if "error" in analysis:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=analysis["error"]
        )
        
    return analysis

# 分阶段康复计划相关路由
@router.put("/plans/{plan_id}/phase", response_model=Dict[str, Any])
async def update_plan_phase(
    plan_id: str = Path(..., description="康复计划ID"),
    phase_data: Dict[str, str] = Body(..., example={"phase": "进步期"}),
    rehab_service: RehabilitationService = Depends(get_rehabilitation_service)
):
    """更新康复计划的当前阶段"""
    if "phase" not in phase_data:
        raise HTTPException(status_code=400, detail="Missing 'phase' field")
        
    updated_plan = await rehab_service.update_rehab_plan_phase(plan_id, phase_data["phase"])
    
    if not updated_plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    
    if "error" in updated_plan:
        raise HTTPException(status_code=400, detail=updated_plan["error"])
        
    return updated_plan

# 运动进度记录相关路由
@router.post("/plans/{plan_id}/exercises/{exercise_id}/progress", response_model=Dict[str, Any])
async def log_exercise_progress(
    plan_id: str = Path(..., description="康复计划ID"),
    exercise_id: str = Path(..., description="运动ID或名称"),
    progress_data: Dict[str, Any] = Body(..., example={
        "completed": True,
        "difficulty_rating": 5,
        "pain_level": 2,
        "notes": "完成得很好，但感觉有点困难"
    }),
    rehab_service: RehabilitationService = Depends(get_rehabilitation_service)
):
    """记录康复运动的完成情况和反馈"""
    if "completed" not in progress_data:
        raise HTTPException(status_code=400, detail="Missing 'completed' field")
        
    updated_plan = await rehab_service.log_exercise_progress(
        plan_id=plan_id,
        exercise_id=exercise_id,
        completed=progress_data["completed"],
        difficulty_rating=progress_data.get("difficulty_rating"),
        pain_level=progress_data.get("pain_level"),
        notes=progress_data.get("notes")
    )
    
    if not updated_plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    
    if "error" in updated_plan:
        raise HTTPException(status_code=400, detail=updated_plan["error"])
        
    return updated_plan

# 计划调整相关路由
@router.put("/plans/{plan_id}/adjustments/{adjustment_id}", response_model=Dict[str, Any])
async def apply_plan_adjustment(
    plan_id: str = Path(..., description="康复计划ID"),
    adjustment_id: str = Path(..., description="调整ID或时间戳"),
    adjustment_data: Dict[str, bool] = Body(..., example={"apply": True}),
    rehab_service: RehabilitationService = Depends(get_rehabilitation_service)
):
    """应用或拒绝康复计划的调整建议"""
    if "apply" not in adjustment_data:
        raise HTTPException(status_code=400, detail="Missing 'apply' field")
        
    updated_plan = await rehab_service.apply_plan_adjustment(
        plan_id=plan_id,
        adjustment_id=adjustment_id,
        apply=adjustment_data["apply"]
    )
    
    if not updated_plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    
    if "error" in updated_plan:
        raise HTTPException(status_code=400, detail=updated_plan["error"])
        
    return updated_plan

# 增强的康复计划详情接口
@router.get("/plans/{plan_id}/detailed", response_model=Dict[str, Any])
async def get_detailed_rehab_plan(
    plan_id: str = Path(..., description="康复计划ID"),
    include_statistics: bool = Query(False, description="是否包含统计数据"),
    rehab_service: RehabilitationService = Depends(get_rehabilitation_service)
):
    """获取康复计划详细信息，包括执行状态和调整历史"""
    plan = await rehab_service.get_rehab_plan(plan_id)
    
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    
    if include_statistics:
        # 计算进度统计信息
        statistics = await rehab_service.calculate_plan_statistics(plan_id)
        plan["statistics"] = statistics
    
    return plan

# 获取康复计划进度统计
@router.get("/plans/{plan_id}/statistics", response_model=Dict[str, Any])
async def get_plan_statistics(
    plan_id: str = Path(..., description="康复计划ID"),
    time_range: str = Query("all", description="时间范围：all/week/month"),
    rehab_service: RehabilitationService = Depends(get_rehabilitation_service)
):
    """获取康复计划的进度统计信息"""
    statistics = await rehab_service.calculate_plan_statistics(plan_id, time_range)
    
    if not statistics:
        raise HTTPException(status_code=404, detail="Plan statistics not found")
    
    return statistics

# 获取运动完成趋势
@router.get("/plans/{plan_id}/trends", response_model=Dict[str, Any])
async def get_exercise_trends(
    plan_id: str = Path(..., description="康复计划ID"),
    exercise_id: Optional[str] = Query(None, description="特定运动ID，不提供则返回所有运动"),
    metric: str = Query("difficulty", description="趋势指标：difficulty/pain/completion"),
    days: int = Query(30, description="查看天数"),
    rehab_service: RehabilitationService = Depends(get_rehabilitation_service)
):
    """获取康复运动的完成趋势数据"""
    trends = await rehab_service.get_exercise_trends(
        plan_id=plan_id,
        exercise_id=exercise_id,
        metric=metric,
        days=days
    )
    
    if not trends:
        raise HTTPException(status_code=404, detail="Trend data not found")
    
    return trends 
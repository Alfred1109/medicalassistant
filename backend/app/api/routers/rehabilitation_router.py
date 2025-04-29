from fastapi import APIRouter, Depends, HTTPException, status, Body, Path, Query
from typing import List, Dict, Any, Optional

from app.schemas.rehabilitation import (
    RehabPlanCreate, 
    RehabPlanUpdate, 
    RehabPlanResponse,
    ExerciseCreate,
    ExerciseResponse
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
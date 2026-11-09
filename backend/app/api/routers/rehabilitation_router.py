from fastapi import APIRouter, Depends, HTTPException, status, Body, Path, Query
from typing import List, Dict, Any, Optional
from datetime import datetime

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.schemas.rehabilitation import (
    RehabPlanCreate,
    RehabPlanUpdate,
    RehabPlanResponse,
    GeneratedPlanApprovalRequest,
    ExerciseCreate,
    ExerciseUpdate,
    ExerciseResponse,
    AssessmentCreate,
    AssessmentUpdate,
    AssessmentResponse
)
from app.schemas.rehab_plan_structure import (
    ExecutionEventCreate,
    PlanVersionCreate,
    PrescriptionItemCreate,
)
from app.services.rehabilitation_service import RehabilitationService
from app.core.dependencies import (
    get_rehabilitation_service,
    get_rehab_plan_structure_service,
    get_database,
    verify_patient_access,
)
from app.core.patient_access import ensure_patient_access
from app.core.auth import get_current_active_user

router = APIRouter()

# AUTH01 对象级授权第一层：带患者标识的端点校验操作者与患者的归属关系
# （操作者须在患者档案 practitioners 列表中，admin 豁免，否则 403 PATIENT_NOT_ASSIGNED）
_verify_patient_query = verify_patient_access("query")
_verify_patient_path = verify_patient_access("path")
_verify_patient_query_optional = verify_patient_access("query", required=False)


# ── AUTH01 对象级授权第二层：仅持 plan_id/assessment_id 的端点 ─────────────
# 先加载计划/评估文档取 patient_id（文档不存在 → 404，不暴露存在性；
# 缺少 patient_id 字段的畸形文档同样按 404 处置），
# 再复用第一层共享校验 ensure_patient_access（非归属医生 403 PATIENT_NOT_ASSIGNED，
# admin 豁免）。读写端点使用同一归属规则，不因只读放宽。

async def _check_plan_access(
    plan_id: str,
    current_user: Any,
    rehab_service: RehabilitationService,
    db: AsyncIOMotorDatabase,
) -> Dict[str, Any]:
    """加载康复计划文档并校验操作者与计划所属患者的归属关系。"""
    plan = await rehab_service.get_rehab_plan(plan_id)
    if not plan or not plan.get("patient_id"):
        raise HTTPException(status_code=404, detail="Rehabilitation plan not found")
    await ensure_patient_access(db, str(plan["patient_id"]),
                                str(current_user.id), current_user.role)
    return plan


async def _check_assessment_access(
    assessment_id: str,
    current_user: Any,
    rehab_service: RehabilitationService,
    db: AsyncIOMotorDatabase,
) -> Dict[str, Any]:
    """加载康复评估文档并校验操作者与评估所属患者的归属关系。"""
    assessment = await rehab_service.get_assessment(assessment_id)
    if not assessment or not assessment.get("patient_id"):
        raise HTTPException(status_code=404, detail="康复评估记录不存在")
    await ensure_patient_access(db, str(assessment["patient_id"]),
                                str(current_user.id), current_user.role)
    return assessment

# LLM生成相关路由
@router.post("/plans/generate", response_model=Dict[str, Any])
async def generate_rehab_plan(
    data: Dict[str, Any],
    current_user: Any = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
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

    # AUTH01：patient_id 来自请求体，校验操作者与患者归属
    await ensure_patient_access(db, data["patient_id"],
                                str(current_user.id), current_user.role)

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
    data: Optional[GeneratedPlanApprovalRequest] = Body(default=None),
    current_user: Any = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
    rehab_service: RehabilitationService = Depends(get_rehabilitation_service)
):
    """审核并确认LLM生成的康复计划"""
    # AUTH01：先加载计划文档取 patient_id，再校验归属（404 优先于 403）
    if current_user.role not in {"doctor", "health_manager", "admin"}:
        raise HTTPException(status_code=403, detail="需要医疗人员审核权限")
    plan = await _check_plan_access(plan_id, current_user, rehab_service, db)
    data = data or GeneratedPlanApprovalRequest()

    approved_plan = await rehab_service.approve_generated_plan(
        plan_id, data.modifications, approved_by=str(current_user.id),
        patient_id=str(plan["patient_id"]), expected_updated_at=data.expected_updated_at,
        expected_revision=data.expected_revision)
    
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
    current_user: Any = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
    rehab_service: RehabilitationService = Depends(get_rehabilitation_service)
):
    """Create a new rehabilitation plan"""
    # AUTH01：patient_id 来自请求体，校验操作者与患者归属
    await ensure_patient_access(db, plan_data.patient_id,
                                str(current_user.id), current_user.role)
    return await rehab_service.create_rehab_plan(plan_data)

@router.get("/plans/{plan_id}", response_model=Dict[str, Any])
async def get_rehab_plan(
    plan_id: str = Path(..., description="The ID of the rehabilitation plan"),
    current_user: Any = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
    rehab_service: RehabilitationService = Depends(get_rehabilitation_service)
):
    """Get a specific rehabilitation plan by ID"""
    # AUTH01：对象级归属校验（加载文档 404 → 归属校验 403）
    plan = await _check_plan_access(plan_id, current_user, rehab_service, db)
    return plan

@router.put("/plans/{plan_id}", response_model=Dict[str, Any])
async def update_rehab_plan(
    plan_data: RehabPlanUpdate,
    plan_id: str = Path(..., description="The ID of the rehabilitation plan"),
    current_user: Any = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
    rehab_service: RehabilitationService = Depends(get_rehabilitation_service)
):
    """Update an existing rehabilitation plan"""
    # AUTH01：对象级归属校验（变更端点与只读端点同一归属规则）
    await _check_plan_access(plan_id, current_user, rehab_service, db)

    updated_plan = await rehab_service.update_rehab_plan(plan_id, plan_data)
    if not updated_plan:
        raise HTTPException(status_code=404, detail="Rehabilitation plan not found")
    return updated_plan

@router.delete("/plans/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rehab_plan(
    plan_id: str = Path(..., description="The ID of the rehabilitation plan"),
    current_user: Any = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
    rehab_service: RehabilitationService = Depends(get_rehabilitation_service)
):
    """Delete a rehabilitation plan"""
    # AUTH01：对象级归属校验（变更端点与只读端点同一归属规则）
    await _check_plan_access(plan_id, current_user, rehab_service, db)

    success = await rehab_service.delete_rehab_plan(plan_id)
    if not success:
        raise HTTPException(status_code=404, detail="Rehabilitation plan not found")

# AUTH01：携带 patient_id 过滤时校验归属；无过滤条件的全量枚举待 AUTH01 服务层按主治医生收敛
@router.get("/plans", response_model=List[Dict[str, Any]])
async def list_rehab_plans(
    patient_id: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    current_user: Any = Depends(_verify_patient_query_optional),
    rehab_service: RehabilitationService = Depends(get_rehabilitation_service)
):
    """List all rehabilitation plans with optional filtering by patient"""
    return await rehab_service.list_rehab_plans(patient_id, skip, limit)

@router.post("/plans/{plan_id}/exercises", response_model=Dict[str, Any])
async def add_exercises_to_plan(
    plan_id: str,
    exercise_data: Dict[str, List[str]],
    current_user: Any = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
    rehab_service: RehabilitationService = Depends(get_rehabilitation_service)
):
    """Add exercises to a rehabilitation plan"""
    # AUTH01：对象级归属校验
    await _check_plan_access(plan_id, current_user, rehab_service, db)

    exercise_ids = exercise_data.get("exercise_ids", [])
    updated_plan = await rehab_service.add_exercises_to_plan(plan_id, exercise_ids)
    
    if not updated_plan:
        raise HTTPException(status_code=404, detail="Rehabilitation plan not found")
    
    return updated_plan

# 运动相关路由
@router.post("/exercises", response_model=Dict[str, Any])
async def create_exercise(
    exercise_data: ExerciseCreate,
    current_user: Any = Depends(get_current_active_user),
    rehab_service: RehabilitationService = Depends(get_rehabilitation_service)
):
    """Create a new rehabilitation exercise"""
    return await rehab_service.create_exercise(exercise_data)

@router.post("/exercises/list", response_model=List[Dict[str, Any]])
async def list_exercises(
    filter_data: Dict[str, Any] = Body(default={}),
    current_user: Any = Depends(get_current_active_user),
    rehab_service: RehabilitationService = Depends(get_rehabilitation_service)
):
    """获取康复运动列表，支持按类别、难度和身体部位筛选"""
    try:
        category = filter_data.get("category")
        difficulty = filter_data.get("difficulty")
        body_parts = filter_data.get("body_parts", [])
        skip = filter_data.get("skip", 0)
        limit = filter_data.get("limit", 100)
        
        return await rehab_service.list_exercises(
            category=category, 
            difficulty=difficulty,
            body_parts=body_parts,
            skip=skip,
            limit=limit
        )
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Error fetching exercises: {str(e)}"
        )

# AUTH01：按查询参数 patient_id 校验归属
@router.get("/exercises/recommendations", response_model=List[Dict[str, Any]])
async def get_exercise_recommendations(
    patient_id: str,
    condition: Optional[str] = None,
    goal: Optional[str] = None,
    agent_id: Optional[str] = None,
    current_user: Any = Depends(_verify_patient_query),
    rehab_service: RehabilitationService = Depends(get_rehabilitation_service)
):
    """Get personalized rehabilitation exercise recommendations"""
    return await rehab_service.get_recommendations(patient_id, condition, goal, agent_id)

# 注意:下面带路径参数的路由必须声明在 /exercises/list、/exercises/recommendations 之后,
# 否则 FastAPI 会先匹配到 "/exercises/{exercise_id}"
@router.get("/exercises/{exercise_id}", response_model=Dict[str, Any])
async def get_exercise(
    exercise_id: str,
    current_user: Any = Depends(get_current_active_user),
    rehab_service: RehabilitationService = Depends(get_rehabilitation_service)
):
    """Get a single rehabilitation exercise by ID"""
    exercise = await rehab_service.get_exercise(exercise_id)
    if not exercise:
        raise HTTPException(status_code=404, detail="Exercise not found")
    return exercise


@router.put("/exercises/{exercise_id}", response_model=Dict[str, Any])
async def update_exercise(
    exercise_id: str,
    exercise_data: ExerciseUpdate,
    current_user: Any = Depends(get_current_active_user),
    rehab_service: RehabilitationService = Depends(get_rehabilitation_service)
):
    """Update a rehabilitation exercise"""
    updated = await rehab_service.update_exercise(
        exercise_id, exercise_data.dict(exclude_unset=True)
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Exercise not found")
    return updated


@router.delete("/exercises/{exercise_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_exercise(
    exercise_id: str,
    current_user: Any = Depends(get_current_active_user),
    rehab_service: RehabilitationService = Depends(get_rehabilitation_service)
):
    """Delete a rehabilitation exercise"""
    success = await rehab_service.delete_exercise(exercise_id)
    if not success:
        raise HTTPException(status_code=404, detail="Exercise not found")

# 康复评估相关路由
@router.post("/assessments", response_model=Dict[str, Any])
async def create_assessment(
    assessment_data: AssessmentCreate,
    current_user: Any = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
    rehab_service: RehabilitationService = Depends(get_rehabilitation_service)
):
    """创建新的康复评估记录"""
    # AUTH01：patient_id 来自请求体，校验操作者与患者归属
    await ensure_patient_access(db, assessment_data.patient_id,
                                str(current_user.id), current_user.role)
    return await rehab_service.create_assessment(assessment_data)

@router.get("/assessments/{assessment_id}", response_model=Dict[str, Any])
async def get_assessment(
    assessment_id: str = Path(..., description="康复评估记录ID"),
    current_user: Any = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
    rehab_service: RehabilitationService = Depends(get_rehabilitation_service)
):
    """获取康复评估记录详情"""
    # AUTH01：对象级归属校验（加载文档 404 → 归属校验 403）
    assessment = await _check_assessment_access(assessment_id, current_user,
                                                rehab_service, db)
    return assessment

@router.put("/assessments/{assessment_id}", response_model=Dict[str, Any])
async def update_assessment(
    assessment_data: AssessmentUpdate,
    assessment_id: str = Path(..., description="康复评估记录ID"),
    current_user: Any = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
    rehab_service: RehabilitationService = Depends(get_rehabilitation_service)
):
    """更新康复评估记录"""
    # AUTH01：对象级归属校验（变更端点与只读端点同一归属规则）
    await _check_assessment_access(assessment_id, current_user, rehab_service, db)

    updated_assessment = await rehab_service.update_assessment(assessment_id, assessment_data)
    if not updated_assessment:
        raise HTTPException(status_code=404, detail="康复评估记录不存在")
    return updated_assessment

# AUTH01：按路径参数 patient_id 校验归属
@router.get("/patients/{patient_id}/assessments", response_model=List[Dict[str, Any]])
async def list_patient_assessments(
    patient_id: str = Path(..., description="患者ID"),
    plan_id: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    skip: int = 0,
    limit: int = 100,
    current_user: Any = Depends(_verify_patient_path),
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

# AUTH01：按查询参数 patient_id 校验归属
@router.get("/assessments/{assessment_id}/comparison", response_model=Dict[str, Any])
async def get_assessment_comparison(
    assessment_id: str = Path(..., description="康复评估记录ID"),
    patient_id: str = Query(..., description="患者ID"),
    current_user: Any = Depends(_verify_patient_query),
    rehab_service: RehabilitationService = Depends(get_rehabilitation_service)
):
    """比较当前评估与前一次评估的差异"""
    comparison = await rehab_service.get_assessment_comparison(patient_id, assessment_id)
    if "error" in comparison:
        raise HTTPException(status_code=404, detail=comparison["error"])
    return comparison

# AUTH01：按查询参数 patient_id 校验归属
@router.post("/assessments/{assessment_id}/analyze", response_model=Dict[str, Any])
async def generate_assessment_analysis(
    assessment_id: str = Path(..., description="康复评估记录ID"),
    patient_id: str = Query(..., description="患者ID"),
    plan_id: Optional[str] = None,
    current_user: Any = Depends(_verify_patient_query),
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
    current_user: Any = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
    rehab_service: RehabilitationService = Depends(get_rehabilitation_service)
):
    """更新康复计划的当前阶段"""
    # AUTH01：对象级归属校验
    await _check_plan_access(plan_id, current_user, rehab_service, db)

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
    current_user: Any = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
    rehab_service: RehabilitationService = Depends(get_rehabilitation_service)
):
    """记录康复运动的完成情况和反馈"""
    # AUTH01：对象级归属校验
    await _check_plan_access(plan_id, current_user, rehab_service, db)

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
    current_user: Any = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
    rehab_service: RehabilitationService = Depends(get_rehabilitation_service)
):
    """应用或拒绝康复计划的调整建议"""
    # AUTH01：对象级归属校验
    await _check_plan_access(plan_id, current_user, rehab_service, db)

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
    current_user: Any = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
    rehab_service: RehabilitationService = Depends(get_rehabilitation_service)
):
    """获取康复计划详细信息，包括执行状态和调整历史"""
    # AUTH01：对象级归属校验（复用加载出的计划文档，避免重复取文档）
    plan = await _check_plan_access(plan_id, current_user, rehab_service, db)

    if include_statistics:
        # 计算进度统计信息
        statistics = await rehab_service.calculate_plan_statistics(plan_id)
        plan["statistics"] = statistics
    
    return plan

# 获取康复计划进度统计
@router.get("/plans/{plan_id}/statistics", response_model=Dict[str, Any])
async def get_plan_statistics(
    plan_id: str = Path(..., description="康复计划ID"),
    time_range: str = Query("all", pattern="^(all|week|month)$",
                            description="时间范围：all/week/month"),
    current_user: Any = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
    rehab_service: RehabilitationService = Depends(get_rehabilitation_service)
):
    """获取康复计划的进度统计信息"""
    # AUTH01：对象级归属校验
    await _check_plan_access(plan_id, current_user, rehab_service, db)

    statistics = await rehab_service.calculate_plan_statistics(plan_id, time_range)
    
    if not statistics:
        raise HTTPException(status_code=404, detail="Plan statistics not found")
    
    return statistics

# 获取运动完成趋势
@router.get("/plans/{plan_id}/trends", response_model=Dict[str, Any])
async def get_exercise_trends(
    plan_id: str = Path(..., description="康复计划ID"),
    exercise_id: Optional[str] = Query(None, description="特定运动ID，不提供则返回所有运动"),
    metric: str = Query("difficulty", pattern="^(difficulty|pain|completion)$",
                        description="趋势指标：difficulty/pain/completion"),
    days: int = Query(30, ge=1, le=730, description="查看天数"),
    current_user: Any = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
    rehab_service: RehabilitationService = Depends(get_rehabilitation_service)
):
    """获取康复运动的完成趋势数据"""
    # AUTH01：对象级归属校验
    await _check_plan_access(plan_id, current_user, rehab_service, db)

    trends = await rehab_service.get_exercise_trends(
        plan_id=plan_id,
        exercise_id=exercise_id,
        metric=metric,
        days=days
    )
    
    if not trends:
        raise HTTPException(status_code=404, detail="Trend data not found")

    return trends


# ── REH01 方案结构化：方案版本 / 处方项 / 执行事件 ─────────────────────────
# 授权契约与既有对象级端点一致：先加载方案文档取 patient_id
# （文档不存在 → 404，不暴露存在性），再复用 patient_access 内核
# ensure_patient_access（非归属医生 403 PATIENT_NOT_ASSIGNED，admin 豁免）。
# 中心/项目维度授权的字段位随文档透传，跨中心规则待 D02 确认后在此追加。
# 服务层抛出的 AppBaseException 由全局异常处理器统一转响应。

@router.post("/plans/{plan_id}/versions", response_model=Dict[str, Any])
async def create_plan_version(
    plan_id: str = Path(..., description="康复计划ID"),
    version_data: Optional[PlanVersionCreate] = Body(default=None),
    current_user: Any = Depends(get_current_active_user),
    rehab_service: RehabilitationService = Depends(get_rehabilitation_service),
    db: AsyncIOMotorDatabase = Depends(get_database),
    structure_service: Any = Depends(get_rehab_plan_structure_service),
):
    """为方案创建新版本（对当前内容做一次白名单快照）"""
    # 授权与其他对象级端点同一规则；服务层 _ensure_plan_access 二次校验兜底
    await _check_plan_access(plan_id, current_user, rehab_service, db)
    return await structure_service.create_plan_version(
        plan_id, version_data or PlanVersionCreate(),
        operator_id=str(current_user.id), operator_role=current_user.role)


@router.get("/plans/{plan_id}/versions", response_model=List[Dict[str, Any]])
async def list_plan_versions(
    plan_id: str = Path(..., description="康复计划ID"),
    skip: int = 0,
    limit: int = Query(100, ge=1, le=500),
    current_user: Any = Depends(get_current_active_user),
    rehab_service: RehabilitationService = Depends(get_rehabilitation_service),
    db: AsyncIOMotorDatabase = Depends(get_database),
    structure_service: Any = Depends(get_rehab_plan_structure_service),
):
    """列出方案的全部版本"""
    # 授权与详情端点同一规则：加载方案文档 → 患者归属校验
    await _check_plan_access(plan_id, current_user, rehab_service, db)
    return await structure_service.list_plan_versions(
        plan_id, operator_id=str(current_user.id), operator_role=current_user.role,
        skip=skip, limit=limit)


@router.get("/plans/{plan_id}/versions/{version_id}", response_model=Dict[str, Any])
async def get_plan_version(
    plan_id: str = Path(..., description="康复计划ID"),
    version_id: str = Path(..., description="方案版本ID"),
    current_user: Any = Depends(get_current_active_user),
    rehab_service: RehabilitationService = Depends(get_rehabilitation_service),
    db: AsyncIOMotorDatabase = Depends(get_database),
    structure_service: Any = Depends(get_rehab_plan_structure_service),
):
    """读取单个方案版本"""
    await _check_plan_access(plan_id, current_user, rehab_service, db)
    return await structure_service.get_plan_version(
        plan_id, version_id,
        operator_id=str(current_user.id), operator_role=current_user.role)


@router.post("/plans/{plan_id}/versions/{version_id}/items", response_model=Dict[str, Any])
async def add_prescription_item(
    item_data: PrescriptionItemCreate,
    plan_id: str = Path(..., description="康复计划ID"),
    version_id: str = Path(..., description="方案版本ID"),
    current_user: Any = Depends(get_current_active_user),
    rehab_service: RehabilitationService = Depends(get_rehabilitation_service),
    db: AsyncIOMotorDatabase = Depends(get_database),
    structure_service: Any = Depends(get_rehab_plan_structure_service),
):
    """向方案版本添加处方项（服务端分配稳定 item_id）"""
    await _check_plan_access(plan_id, current_user, rehab_service, db)
    return await structure_service.add_prescription_item(
        plan_id, version_id, item_data,
        operator_id=str(current_user.id), operator_role=current_user.role)


@router.get("/plans/{plan_id}/items", response_model=List[Dict[str, Any]])
async def list_prescription_items(
    plan_id: str = Path(..., description="康复计划ID"),
    version_id: Optional[str] = Query(None, description="按方案版本过滤"),
    skip: int = 0,
    limit: int = Query(100, ge=1, le=500),
    current_user: Any = Depends(get_current_active_user),
    rehab_service: RehabilitationService = Depends(get_rehabilitation_service),
    db: AsyncIOMotorDatabase = Depends(get_database),
    structure_service: Any = Depends(get_rehab_plan_structure_service),
):
    """列出方案的处方项"""
    await _check_plan_access(plan_id, current_user, rehab_service, db)
    return await structure_service.list_prescription_items(
        plan_id, version_id=version_id,
        operator_id=str(current_user.id), operator_role=current_user.role,
        skip=skip, limit=limit)


@router.post("/plans/{plan_id}/items/{item_id}/events", response_model=Dict[str, Any])
async def record_execution_event(
    event_data: ExecutionEventCreate,
    plan_id: str = Path(..., description="康复计划ID"),
    item_id: str = Path(..., description="处方项ID（稳定 item_id）"),
    current_user: Any = Depends(get_current_active_user),
    rehab_service: RehabilitationService = Depends(get_rehabilitation_service),
    db: AsyncIOMotorDatabase = Depends(get_database),
    structure_service: Any = Depends(get_rehab_plan_structure_service),
):
    """记录一次训练执行事件；(plan_id, event_id) 幂等，重复提交返回既有事件"""
    await _check_plan_access(plan_id, current_user, rehab_service, db)
    return await structure_service.record_execution_event(
        plan_id, item_id, event_data,
        operator_id=str(current_user.id), operator_role=current_user.role)


@router.get("/plans/{plan_id}/items/{item_id}/events", response_model=List[Dict[str, Any]])
async def list_execution_events(
    plan_id: str = Path(..., description="康复计划ID"),
    item_id: str = Path(..., description="处方项ID（稳定 item_id）"),
    skip: int = 0,
    limit: int = Query(100, ge=1, le=500),
    current_user: Any = Depends(get_current_active_user),
    rehab_service: RehabilitationService = Depends(get_rehabilitation_service),
    db: AsyncIOMotorDatabase = Depends(get_database),
    structure_service: Any = Depends(get_rehab_plan_structure_service),
):
    """列出处方项的执行事件"""
    await _check_plan_access(plan_id, current_user, rehab_service, db)
    return await structure_service.list_execution_events(
        plan_id, item_id=item_id,
        operator_id=str(current_user.id), operator_role=current_user.role,
        skip=skip, limit=limit)

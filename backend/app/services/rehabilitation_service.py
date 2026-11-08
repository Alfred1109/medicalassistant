from app.core.llm import LLMConfigurationError
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from motor.motor_asyncio import AsyncIOMotorDatabase
from bson.objectid import ObjectId
from pymongo import ReturnDocument
from pymongo.errors import PyMongoError
from copy import deepcopy
from app.core.exceptions import AppBaseException
import numpy as np

from app.schemas.rehabilitation import (
    RehabPlanCreate, 
    RehabPlanUpdate,
    GeneratedPlanEdits,
    ExerciseCreate,
    AssessmentCreate,
    AssessmentUpdate,
)
from app.services.agent_service import AgentService

class RehabilitationService:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.plans_collection = db.rehab_plans
        self.exercises_collection = db.exercises
        self.assessments_collection = db.rehab_assessments
        self.agent_service = AgentService(db)
        
    # Rehabilitation Plans
    async def create_rehab_plan(self, plan_data: RehabPlanCreate) -> Dict[str, Any]:
        """Create a new rehabilitation plan"""
        plan = plan_data.dict()
        plan["created_at"] = datetime.utcnow()
        plan["updated_at"] = plan["created_at"]
        
        result = await self.plans_collection.insert_one(plan)
        plan["_id"] = str(result.inserted_id)
        
        return plan
        
    async def get_rehab_plan(self, plan_id: str) -> Optional[Dict[str, Any]]:
        """Get rehabilitation plan by ID"""
        if not ObjectId.is_valid(plan_id):
            return None
        try:
            plan = await self.plans_collection.find_one({"_id": ObjectId(plan_id)})
            if plan:
                plan["_id"] = str(plan["_id"])
                return plan
        except PyMongoError as exc:
            raise AppBaseException("康复计划读取失败，请稍后重试", status_code=503,
                                   error_code="REHAB_PLAN_READ_FAILED") from exc
        return None
        
    @staticmethod
    def _is_generated_plan(plan: Dict[str, Any]) -> bool:
        metadata = plan.get("metadata")
        return (plan.get("generation_source") == "llm" or
                isinstance(metadata, dict) and metadata.get("generated_by") == "llm")

    async def update_rehab_plan(self, plan_id: str, plan_data: RehabPlanUpdate) -> Optional[Dict[str, Any]]:
        """普通计划保留既有编辑能力，生成计划的审核状态与证据由审核入口拥有。"""
        if not ObjectId.is_valid(plan_id):
            return None
        try:
            plan = await self.plans_collection.find_one({"_id": ObjectId(plan_id)})
            if plan is None:
                return None
            update_data = plan_data.model_dump(exclude_unset=True)
            update_data["updated_at"] = datetime.utcnow()
            if self._is_generated_plan(plan):
                if "status" in update_data and update_data["status"] != plan.get("status"):
                    raise AppBaseException("生成计划的状态须经对应审核操作变更", status_code=409,
                                           error_code="REHAB_PLAN_APPROVAL_REQUIRED")
                if "metadata" in update_data:
                    original = plan.get("metadata") or {}
                    if not isinstance(original, dict):
                        raise AppBaseException("计划审核元数据结构异常，请核查原记录", status_code=409,
                                               error_code="REHAB_PLAN_INVALID_HISTORY")
                    incoming = update_data["metadata"]
                    if incoming is None:
                        raise AppBaseException("不能清除生成计划审核元数据", status_code=409,
                                               error_code="REHAB_PLAN_APPROVAL_REQUIRED")
                    owned = {key for key in original if key.startswith("approval_")}
                    owned.update({"generated_by", "generation_timestamp", "is_approved",
                                  "approved_by", "version", "last_updated"})
                    for key in incoming:
                        if ((key in owned or key.startswith("approval_")) and
                                (key not in original or incoming[key] != original[key])):
                            raise AppBaseException("不能通过普通编辑修改生成或审核证据", status_code=409,
                                                   error_code="REHAB_PLAN_APPROVAL_REQUIRED")
                    update_data["metadata"] = {**incoming,
                        **{key: deepcopy(value) for key, value in original.items() if key in owned}}
                # 保留旧标识，防止普通编辑先去除generated_by再绕过审核保护。
                query = {"_id": ObjectId(plan_id), "patient_id": plan.get("patient_id"),
                         "status": plan.get("status"), "metadata": plan.get("metadata"),
                         "generation_source": plan.get("generation_source"),
                         "content_revision": plan.get("content_revision"),
                         "updated_at": plan.get("updated_at")}
                updated = await self.plans_collection.find_one_and_update(
                    query, {"$set": update_data, "$inc": {"content_revision": 1}},
                    return_document=ReturnDocument.AFTER)
                if updated is None:
                    raise AppBaseException("计划已被其他请求修改，请重新读取", status_code=409,
                                           error_code="REHAB_PLAN_CONFLICT")
                updated["_id"] = str(updated["_id"])
                return updated
            result = await self.plans_collection.update_one(
                {"_id": ObjectId(plan_id)}, {"$inc": {"content_revision": 1}, "$set": update_data})
            if result.modified_count:
                return await self.get_rehab_plan(plan_id)
        except PyMongoError as exc:
            raise AppBaseException("康复计划更新失败，请稍后重试", status_code=503,
                                   error_code="REHAB_PLAN_UPDATE_FAILED") from exc
        return None

    async def delete_rehab_plan(self, plan_id: str) -> bool:
        """Delete a rehabilitation plan"""
        try:
            result = await self.plans_collection.delete_one({"_id": ObjectId(plan_id)})
            return result.deleted_count > 0
        except Exception:
            return False
            
    async def list_rehab_plans(
        self, patient_id: Optional[str] = None, skip: int = 0, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """List rehabilitation plans with optional patient filtering"""
        filter_dict = {}
        if patient_id:
            filter_dict["patient_id"] = patient_id
            
        cursor = self.plans_collection.find(filter_dict).skip(skip).limit(limit)
        plans = []
        
        async for plan in cursor:
            plan["_id"] = str(plan["_id"])
            plans.append(plan)
            
        return plans
    
    async def generate_rehab_plan_with_llm(
        self, 
        patient_id: str, 
        patient_name: str,
        condition: str,
        goal: str
    ) -> Dict[str, Any]:
        """使用LLM生成康复计划"""
        # 准备患者数据
        patient_data = {
            "patient_id": patient_id,
            "patient_name": patient_name,
            "condition": condition,
            "goal": goal
        }
        
        try:
            # 调用代理服务的LLM生成方法
            # （agent_service.generate_rehab_plan 失败时抛出异常，不再返回 None，
            #   因此这里不存在"生成失败则使用模拟数据"的回退分支——REH02）
            generated_plan = await self.agent_service.generate_rehab_plan(patient_data)

            # 将生成的计划保存为草稿状态
            generated_plan["status"] = "draft"  # 标记为草稿状态
            generated_plan["patient_id"] = patient_id
            generated_plan["generation_source"] = "llm"
            generated_plan["content_revision"] = 0
            
            # 持久化成功才有可审核的计划；保存失败不能产生临时业务ID。
            now = datetime.utcnow()
            generated_plan["created_at"] = now
            generated_plan["updated_at"] = now
            try:
                result = await self.plans_collection.insert_one(generated_plan)
            except PyMongoError as exc:
                raise AppBaseException(
                    "康复计划保存失败，请稍后重试", status_code=503,
                    error_code="REHAB_PLAN_SAVE_FAILED") from exc
            generated_plan["_id"] = str(result.inserted_id)

            return generated_plan

        except LLMConfigurationError:
            raise
        # LLM 生成失败必须显式暴露，不得返回应急模拟计划冒充成功（REH02）；
        # 异常（含 LLMConfigurationError / ExternalServiceException）直接向上传播，
        # 由全局异常处理器返回明确的失败响应。
    
    async def approve_generated_plan(
        self, plan_id: str, modifications: GeneratedPlanEdits,
        *, approved_by: str, patient_id: str, expected_updated_at: Optional[datetime] = None,
        expected_revision: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """在一个原子写中应用审核内容、证据和既有 active 状态流转。

        active 沿用现有行为，不代表新增的临床签署或发布验收。
        """
        if not ObjectId.is_valid(plan_id):
            return None
        try:
            plan = await self.plans_collection.find_one({"_id": ObjectId(plan_id)})
            if not plan:
                return None
            if str(plan.get("patient_id")) != str(patient_id):
                raise AppBaseException("计划归属已改变，请重新读取", status_code=409,
                                       error_code="REHAB_PLAN_CONFLICT")
            if plan.get("status") != "draft":
                raise AppBaseException("仅草稿计划可审核", status_code=409,
                                       error_code="REHAB_PLAN_CONFLICT")
            now = datetime.utcnow()
            metadata = deepcopy(plan.get("metadata") or {})
            if not isinstance(metadata, dict):
                raise AppBaseException("计划审核元数据结构异常，请核查原记录", status_code=409,
                                       error_code="REHAB_PLAN_INVALID_HISTORY")
            history = metadata.get("approval_history") or []
            if not isinstance(history, list):
                raise AppBaseException("计划审核历史结构异常，请核查原记录", status_code=409,
                                       error_code="REHAB_PLAN_INVALID_HISTORY")
            changes = modifications.model_dump(exclude_unset=True, exclude_none=True)
            metadata.update(is_approved=True, approval_timestamp=now.isoformat(),
                            approved_by=approved_by,
                            approval_history=[*history, {"timestamp": now.isoformat(),
                                "status": "approved", "approved_by": approved_by,
                                "modifications": bool(changes)}])
            # Mongo将日期比较值编码为毫秒，与前端JSON往返及BSON存储精度一致。
            expected = expected_updated_at if expected_updated_at is not None else plan.get("updated_at")
            query = {"_id": ObjectId(plan_id), "patient_id": plan["patient_id"],
                     "status": "draft", "updated_at": expected,
                     "content_revision": (expected_revision if expected_revision is not None
                                          else plan.get("content_revision")),
                     "metadata": plan.get("metadata")}
            updated = await self.plans_collection.find_one_and_update(
                query, {"$set": {**changes, "metadata": metadata, "status": "active", "updated_at": now},
                        "$inc": {"content_revision": 1}},
                return_document=ReturnDocument.AFTER)
            if updated is None:
                raise AppBaseException("计划已被其他请求修改，请重新读取后审核", status_code=409,
                                       error_code="REHAB_PLAN_CONFLICT")
            updated["_id"] = str(updated["_id"])
            return updated
        except PyMongoError as exc:
            raise AppBaseException("康复计划审核写入失败，请重新读取后重试", status_code=503,
                                   error_code="REHAB_PLAN_APPROVAL_FAILED") from exc

    async def add_exercises_to_plan(self, plan_id: str, exercise_ids: List[str]) -> Optional[Dict[str, Any]]:
        """Add existing exercises to a rehabilitation plan"""
        plan = await self.get_rehab_plan(plan_id)
        if not plan:
            return None
            
        # Get current exercises in the plan
        current_exercises = plan.get("exercises", [])
        current_exercise_ids = [ex.get("exercise_id") for ex in current_exercises]
        
        # Add only new exercises that aren't already in the plan
        exercises_to_add = []
        for ex_id in exercise_ids:
            if ex_id not in current_exercise_ids:
                # Get the exercise to validate it exists
                exercise = await self.get_exercise(ex_id)
                if exercise:
                    exercises_to_add.append({
                        "exercise_id": ex_id,
                        "added_at": datetime.utcnow(),
                        "schedule": {"days_per_week": 3, "sets": 3, "reps": 10},
                        "progress": []
                    })
        
        if not exercises_to_add:
            return plan
            
        # Update the plan with new exercises
        try:
            result = await self.plans_collection.update_one(
                {"_id": ObjectId(plan_id)},
                {"$inc": {"content_revision": 1},
                    "$push": {"exercises": {"$each": exercises_to_add}},
                    "$set": {"updated_at": datetime.utcnow()}
                }
            )
            
            if result.modified_count:
                return await self.get_rehab_plan(plan_id)
        except Exception:
            return None
        return plan
        
    # Exercises
    async def create_exercise(self, exercise_data: ExerciseCreate) -> Dict[str, Any]:
        """Create a new rehabilitation exercise"""
        exercise = exercise_data.dict()
        exercise["created_at"] = datetime.utcnow()
        exercise["updated_at"] = exercise["created_at"]
        
        result = await self.exercises_collection.insert_one(exercise)
        exercise["_id"] = str(result.inserted_id)
        
        return exercise
        
    async def list_exercises(
        self, 
        category: Optional[str] = None,
        difficulty: Optional[str] = None,
        body_parts: Optional[List[str]] = None,
        skip: int = 0, 
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """获取康复运动列表，支持按类别、难度和身体部位筛选"""
        try:
            filter_dict = {}
            
            if category:
                filter_dict["category"] = category
                
            if difficulty:
                filter_dict["difficulty"] = difficulty
                
            if body_parts and len(body_parts) > 0:
                filter_dict["body_part"] = {"$in": body_parts}

            print(f"Exercise list query: {filter_dict}, skip: {skip}, limit: {limit}")
                
            cursor = self.exercises_collection.find(filter_dict).skip(skip).limit(limit)
            exercises = []
            
            async for exercise in cursor:
                exercise["_id"] = str(exercise["_id"])
                exercises.append(exercise)
                
            print(f"Found {len(exercises)} exercises")
            return exercises
        except Exception as e:
            print(f"Error in list_exercises: {str(e)}")
            # 出错时返回空列表
            return []
        
    async def get_exercise(self, exercise_id: str) -> Optional[Dict[str, Any]]:
        """Get exercise by ID"""
        try:
            exercise = await self.exercises_collection.find_one({"_id": ObjectId(exercise_id)})
            if exercise:
                exercise["_id"] = str(exercise["_id"])
                return exercise
        except Exception:
            return None
        return None

    async def update_exercise(
        self, exercise_id: str, exercise_data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Update an exercise. Only the fields present in exercise_data are changed."""
        try:
            updates = {k: v for k, v in exercise_data.items() if v is not None}
            if not updates:
                return await self.get_exercise(exercise_id)

            updates["updated_at"] = datetime.utcnow()
            result = await self.exercises_collection.update_one(
                {"_id": ObjectId(exercise_id)}, {"$set": updates}
            )
            if result.matched_count == 0:
                return None
            return await self.get_exercise(exercise_id)
        except Exception:
            return None

    async def delete_exercise(self, exercise_id: str) -> bool:
        """Delete an exercise by ID"""
        try:
            result = await self.exercises_collection.delete_one({"_id": ObjectId(exercise_id)})
            return result.deleted_count > 0
        except Exception:
            return False

    async def get_recommendations(
        self, patient_id: str, condition: Optional[str] = None, 
        goal: Optional[str] = None, agent_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get personalized exercise recommendations using the dynamic agent system"""
        # Use the default recommendation agent if none specified
        if not agent_id:
            # In a real implementation, we would query for a suitable agent
            # For now, we'll assume there's a specific agent for recommendations
            # This would need to be replaced with actual agent discovery logic
            agent_cursor = await self.db.agents.find_one({"name": "RehabRecommender"})
            if agent_cursor:
                agent_id = str(agent_cursor["_id"])
            else:
                # No suitable agent found
                return []
                
        # Build the query for the agent
        query = {
            "query": "Recommend exercises",
            "parameters": {
                "patient_id": patient_id,
                "condition": condition,
                "goal": goal
            }
        }
        
        # Process the query with the agent
        agent_response = await self.agent_service.process_query(agent_id, query)
        if not agent_response:
            return []
            
        # In a real implementation, the agent would return exercise IDs or details
        # For now, we'll just return some sample exercises
        cursor = self.exercises_collection.find({"body_part": condition}).limit(5)
        recommendations = []
        
        async for exercise in cursor:
            exercise["_id"] = str(exercise["_id"])
            recommendations.append(exercise)
            
        return recommendations 

    # 新增 - 康复评估相关功能
    async def create_assessment(self, assessment_data: AssessmentCreate) -> Dict[str, Any]:
        """创建新的康复评估记录"""
        assessment = assessment_data.dict()
        assessment["created_at"] = datetime.utcnow()
        assessment["updated_at"] = assessment["created_at"]
        
        # 生成评估分数
        assessment["scores"] = self._calculate_assessment_scores(assessment)
        
        result = await self.assessments_collection.insert_one(assessment)
        assessment["_id"] = str(result.inserted_id)
        
        # 关联到康复计划（如果指定了计划ID）
        if "plan_id" in assessment and assessment["plan_id"]:
            await self.plans_collection.update_one(
                {"_id": ObjectId(assessment["plan_id"])},
                {"$inc": {"content_revision": 1},
                    "$push": {"assessments": str(result.inserted_id)},
                    "$set": {"updated_at": datetime.utcnow()}
                }
            )
        
        return assessment
    
    async def get_assessment(self, assessment_id: str) -> Optional[Dict[str, Any]]:
        """获取康复评估记录详情"""
        try:
            assessment = await self.assessments_collection.find_one({"_id": ObjectId(assessment_id)})
            if assessment:
                assessment["_id"] = str(assessment["_id"])
                return assessment
        except Exception:
            return None
        return None
    
    async def update_assessment(self, assessment_id: str, assessment_data: AssessmentUpdate) -> Optional[Dict[str, Any]]:
        """更新康复评估记录"""
        try:
            update_data = assessment_data.dict(exclude_unset=True)
            update_data["updated_at"] = datetime.utcnow()
            
            # 如果更新了评估指标，重新计算评分
            if any(k in update_data for k in ["range_of_motion", "muscle_strength", "pain_level", "functional_status"]):
                assessment = await self.get_assessment(assessment_id)
                if assessment:
                    # 更新评估数据
                    for k, v in update_data.items():
                        assessment[k] = v
                    # 重新计算评分
                    update_data["scores"] = self._calculate_assessment_scores(assessment)
            
            result = await self.assessments_collection.update_one(
                {"_id": ObjectId(assessment_id)},
                {"$set": update_data}
            )
            
            if result.modified_count:
                return await self.get_assessment(assessment_id)
        except Exception:
            return None
        return None
    
    async def list_patient_assessments(
        self, patient_id: str, plan_id: Optional[str] = None, 
        start_date: Optional[datetime] = None, end_date: Optional[datetime] = None,
        skip: int = 0, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """获取患者的康复评估记录列表"""
        filter_dict = {"patient_id": patient_id}
        
        if plan_id:
            filter_dict["plan_id"] = plan_id
            
        if start_date or end_date:
            date_filter = {}
            if start_date:
                date_filter["$gte"] = start_date
            if end_date:
                date_filter["$lte"] = end_date
            filter_dict["created_at"] = date_filter
            
        cursor = self.assessments_collection.find(filter_dict).sort("created_at", -1).skip(skip).limit(limit)
        assessments = []
        
        async for assessment in cursor:
            assessment["_id"] = str(assessment["_id"])
            assessments.append(assessment)
            
        return assessments
    
    async def get_assessment_comparison(self, patient_id: str, assessment_id: str) -> Dict[str, Any]:
        """比较当前评估与前一次评估的差异"""
        current = await self.get_assessment(assessment_id)
        if not current:
            return {"error": "Assessment not found"}
            
        # 获取之前的评估
        previous_cursor = self.assessments_collection.find({
            "patient_id": patient_id,
            "created_at": {"$lt": current["created_at"]}
        }).sort("created_at", -1).limit(1)
        
        previous = None
        async for doc in previous_cursor:
            doc["_id"] = str(doc["_id"])
            previous = doc
            break
            
        if not previous:
            return {
                "current": current,
                "previous": None,
                "differences": {"message": "No previous assessment for comparison"}
            }
            
        # 计算关键指标的差异
        differences = {}
        for category in ["range_of_motion", "muscle_strength", "pain_level", "functional_status"]:
            if category in current and category in previous:
                diff = {}
                for key in current[category]:
                    if key in previous[category]:
                        curr_val = current[category][key]
                        prev_val = previous[category][key]
                        
                        if isinstance(curr_val, (int, float)) and isinstance(prev_val, (int, float)):
                            absolute_diff = curr_val - prev_val
                            if prev_val != 0:
                                percent_diff = (absolute_diff / abs(prev_val)) * 100
                            else:
                                percent_diff = None
                                
                            diff[key] = {
                                "absolute": absolute_diff,
                                "percent": percent_diff,
                                "trend": "improved" if self._is_improvement(category, absolute_diff) else "declined"
                            }
                differences[category] = diff
                
        # 计算总体评分差异
        if "scores" in current and "scores" in previous:
            score_diff = {
                "overall": current["scores"]["overall"] - previous["scores"]["overall"],
                "percent_change": ((current["scores"]["overall"] - previous["scores"]["overall"]) / 
                                  max(1, previous["scores"]["overall"])) * 100
            }
            differences["scores"] = score_diff
        
        return {
            "current": current,
            "previous": previous,
            "differences": differences
        }
    
    def _calculate_assessment_scores(self, assessment: Dict[str, Any]) -> Dict[str, float]:
        """计算康复评估得分"""
        scores = {}
        
        # 计算关节活动度得分 (range_of_motion)
        if "range_of_motion" in assessment:
            rom_values = [v for v in assessment["range_of_motion"].values() if isinstance(v, (int, float))]
            if rom_values:
                # 假设正常关节活动度为100，计算平均活动度恢复比例
                scores["range_of_motion"] = sum(rom_values) / len(rom_values)
            else:
                scores["range_of_motion"] = 0
        else:
            scores["range_of_motion"] = 0
            
        # 计算肌肉力量得分 (muscle_strength)
        if "muscle_strength" in assessment:
            # 假设肌肉力量使用0-5量表评分
            strength_values = [v for v in assessment["muscle_strength"].values() if isinstance(v, (int, float))]
            if strength_values:
                # 将0-5转换为0-100的百分比
                scores["muscle_strength"] = (sum(strength_values) / len(strength_values)) * 20  # 5分转为100分
            else:
                scores["muscle_strength"] = 0
        else:
            scores["muscle_strength"] = 0
            
        # 计算疼痛水平得分 (pain_level)
        if "pain_level" in assessment:
            # 假设疼痛使用0-10量表，0表示无痛，10表示剧痛
            pain_values = [v for v in assessment["pain_level"].values() if isinstance(v, (int, float))]
            if pain_values:
                # 反向计算得分，疼痛越低分数越高
                avg_pain = sum(pain_values) / len(pain_values)
                scores["pain_level"] = 100 - (avg_pain * 10)  # 0分痛反转为100分，10分痛反转为0分
            else:
                scores["pain_level"] = 100  # 无疼痛记录假设为满分
        else:
            scores["pain_level"] = 100
            
        # 计算功能状态得分 (functional_status)
        if "functional_status" in assessment:
            func_values = [v for v in assessment["functional_status"].values() if isinstance(v, (int, float))]
            if func_values:
                # 假设功能状态使用0-100评分
                scores["functional_status"] = sum(func_values) / len(func_values)
            else:
                scores["functional_status"] = 0
        else:
            scores["functional_status"] = 0
            
        # 计算总体评分，加权平均
        weights = {
            "range_of_motion": 0.3,
            "muscle_strength": 0.3,
            "pain_level": 0.2,
            "functional_status": 0.2
        }
        
        scores["overall"] = sum(score * weights[category] for category, score in scores.items())
        
        return scores
    
    def _is_improvement(self, category: str, difference: float) -> bool:
        """判断变化是否为改进"""
        # 对于疼痛，减少是改进；对于其他指标，增加是改进
        return (category == "pain_level" and difference < 0) or (category != "pain_level" and difference > 0)
        
    async def generate_assessment_with_llm(
        self, 
        patient_id: str,
        plan_id: Optional[str] = None,
        previous_assessment_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """使用LLM解释康复评估结果并提供建议"""
        # 获取当前评估
        if previous_assessment_id:
            comparison = await self.get_assessment_comparison(patient_id, previous_assessment_id)
            
            if "error" in comparison:
                return comparison
                
            # 准备提示词数据
            prompt_data = {
                "patient_id": patient_id,
                "plan_id": plan_id,
                "current_assessment": comparison["current"],
                "previous_assessment": comparison["previous"],
                "differences": comparison["differences"]
            }
            
            # 调用代理服务生成评估解释
            assessment_analysis = await self.agent_service.generate_assessment_analysis(prompt_data)
            
            if assessment_analysis:
                # 更新当前评估，添加AI分析结果
                await self.assessments_collection.update_one(
                    {"_id": ObjectId(previous_assessment_id)},
                    {
                        "$set": {
                            "ai_analysis": assessment_analysis,
                            "updated_at": datetime.utcnow()
                        }
                    }
                )
                
                # 获取更新后的评估
                updated_assessment = await self.get_assessment(previous_assessment_id)
                return updated_assessment or {"error": "Failed to update assessment with AI analysis"}
            else:
                return {"error": "Failed to generate assessment analysis"}
        else:
            return {"error": "No assessment ID provided"}
    
    async def update_rehab_plan_phase(self, plan_id: str, new_phase: str) -> Optional[Dict[str, Any]]:
        """更新康复计划的当前阶段"""
        plan = await self.get_rehab_plan(plan_id)
        if not plan:
            return None
            
        # 验证新阶段是否有效
        valid_phases = [phase.get("name") for phase in plan.get("phases", [])]
        if not valid_phases or new_phase not in valid_phases:
            return {"error": f"Invalid phase. Valid phases are: {', '.join(valid_phases)}"}
            
        # 记录阶段变更
        current_phase = plan.get("execution_status", {}).get("current_phase", "")
        
        # 更新执行状态
        execution_status = plan.get("execution_status", {})
        execution_status["current_phase"] = new_phase
        execution_status["last_updated"] = datetime.utcnow().isoformat()
        
        # 添加到调整历史
        adjustment = {
            "type": "phase_change",
            "from": current_phase,
            "to": new_phase,
            "timestamp": datetime.utcnow().isoformat(),
            "reason": "Manual phase change"  # 手动阶段变更
        }
        
        try:
            # 更新数据库
            await self.plans_collection.update_one(
                {"_id": ObjectId(plan_id)},
                {"$inc": {"content_revision": 1},
                    "$set": {
                        "execution_status": execution_status,
                        "updated_at": datetime.utcnow()
                    },
                    "$push": {"adjustment_history": adjustment}
                }
            )
            
            # 获取更新后的计划
            return await self.get_rehab_plan(plan_id)
        except Exception as e:
            print(f"Error updating plan phase: {str(e)}")
            return None
    
    async def log_exercise_progress(
        self, plan_id: str, exercise_id: str, completed: bool, 
        difficulty_rating: Optional[int] = None, 
        pain_level: Optional[int] = None,
        notes: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """记录康复运动的完成情况和反馈"""
        plan = await self.get_rehab_plan(plan_id)
        if not plan:
            return None
            
        # 找到对应的运动
        exercise_found = False
        exercises = plan.get("exercises", [])
        for i, exercise in enumerate(exercises):
            if exercise.get("id") == exercise_id or exercise.get("name") == exercise_id:
                exercise_found = True
                
                # 创建进度记录
                progress_entry = {
                    "date": datetime.utcnow().isoformat(),
                    "completed": completed,
                    "difficulty_rating": difficulty_rating,
                    "pain_level": pain_level,
                    "notes": notes
                }
                
                # 如果运动没有进度记录列表，添加一个
                if "progress" not in exercise:
                    exercise["progress"] = []
                    
                # 添加进度记录
                exercise["progress"].append(progress_entry)
                
                # 更新运动状态
                if completed:
                    exercise["status"] = "completed"
                    
                # 更新执行状态统计
                execution_status = plan.get("execution_status", {})
                if completed:
                    execution_status["completed_exercises"] = execution_status.get("completed_exercises", 0) + 1
                
                # 计算坚持率
                total = execution_status.get("total_exercises", 1)  # 避免除零错误
                completed = execution_status.get("completed_exercises", 0)
                execution_status["adherence_rate"] = min(100, int((completed / total) * 100))
                
                execution_status["last_updated"] = datetime.utcnow().isoformat()
                
                try:
                    # 更新数据库
                    await self.plans_collection.update_one(
                        {"_id": ObjectId(plan_id)},
                        {"$inc": {"content_revision": 1},
                            "$set": {
                                f"exercises.{i}": exercise,
                                "execution_status": execution_status,
                                "updated_at": datetime.utcnow()
                            }
                        }
                    )
                    
                    # 如果有足够的进度数据，检查是否需要调整计划
                    if len(exercise["progress"]) >= 3:
                        await self._check_plan_adjustment_needed(plan_id, exercise, i)
                    
                    # 获取更新后的计划
                    return await self.get_rehab_plan(plan_id)
                except Exception as e:
                    print(f"Error logging exercise progress: {str(e)}")
                    return None
                    
        if not exercise_found:
            return {"error": "Exercise not found in plan"}
    
    async def _check_plan_adjustment_needed(
        self, plan_id: str, exercise: Dict[str, Any], exercise_index: int
    ) -> None:
        """检查是否需要根据运动进度调整计划难度"""
        progress = exercise.get("progress", [])
        if len(progress) < 3:
            return  # 数据不足，不进行调整
            
        # 获取最近3次进度记录
        recent_progress = sorted(progress, key=lambda x: x.get("date", ""), reverse=True)[:3]
        
        # 计算平均难度评分和疼痛水平
        avg_difficulty = sum(p.get("difficulty_rating", 0) for p in recent_progress if p.get("difficulty_rating") is not None) / len([p for p in recent_progress if p.get("difficulty_rating") is not None] or [0])
        avg_pain = sum(p.get("pain_level", 0) for p in recent_progress if p.get("pain_level") is not None) / len([p for p in recent_progress if p.get("pain_level") is not None] or [0])
        
        # 根据平均难度和疼痛水平决定是否调整
        adjustment = None
        adjustment_type = None
        
        # 如果最近3次评价都完成了，且难度评分过低，增加难度
        if all(p.get("completed", False) for p in recent_progress) and avg_difficulty < 3 and avg_pain < 3:
            adjustment_type = "increase_difficulty"
            # 获取难度增加的调整方案
            adjustment = exercise.get("adjustments", {}).get("harder", "")
        
        # 如果疼痛水平过高或难度评分过高，降低难度
        elif avg_pain > 6 or avg_difficulty > 8:
            adjustment_type = "decrease_difficulty"
            # 获取难度降低的调整方案
            adjustment = exercise.get("adjustments", {}).get("easier", "")
            
        if adjustment and adjustment_type:
            # 记录调整建议
            adjustment_record = {
                "type": adjustment_type,
                "exercise_name": exercise.get("name", ""),
                "exercise_id": exercise.get("id", ""),
                "reason": f"自动调整: 平均难度评分={avg_difficulty:.1f}, 平均疼痛水平={avg_pain:.1f}",
                "suggestion": adjustment,
                "timestamp": datetime.utcnow().isoformat(),
                "applied": False  # 标记为未应用
            }
            
            # 更新调整历史
            await self.plans_collection.update_one(
                {"_id": ObjectId(plan_id)},
                {"$inc": {"content_revision": 1}, "$push": {"adjustment_history": adjustment_record}}
            )
    
    async def apply_plan_adjustment(
        self, plan_id: str, adjustment_id: str, apply: bool = True
    ) -> Optional[Dict[str, Any]]:
        """应用或拒绝康复计划的调整建议"""
        plan = await self.get_rehab_plan(plan_id)
        if not plan:
            return None
            
        # 查找对应的调整建议
        adjustment_history = plan.get("adjustment_history", [])
        
        for i, adj in enumerate(adjustment_history):
            if adj.get("id") == adjustment_id or adj.get("timestamp") == adjustment_id:
                # 标记调整为已应用/已拒绝
                adj["applied"] = apply
                adj["applied_date"] = datetime.utcnow().isoformat()
                
                if apply:
                    # 如果是应用调整，执行实际调整
                    exercise_name = adj.get("exercise_name", "")
                    adjustment_type = adj.get("type", "")
                    
                    # 查找对应运动
                    for j, ex in enumerate(plan.get("exercises", [])):
                        if ex.get("name") == exercise_name:
                            # 根据调整类型修改运动
                            if adjustment_type == "increase_difficulty":
                                # 增加难度：增加重复次数或组数
                                ex["repetitions"] = min(30, ex.get("repetitions", 10) + 2)
                                ex["sets"] = min(5, ex.get("sets", 3) + 1)
                                # 更新难度级别
                                difficulty_map = {"简单": "中等", "中等": "困难", "困难": "困难"}
                                ex["difficulty"] = difficulty_map.get(ex.get("difficulty", "简单"), "中等")
                            
                            elif adjustment_type == "decrease_difficulty":
                                # 减少难度：减少重复次数或组数
                                ex["repetitions"] = max(5, ex.get("repetitions", 10) - 2)
                                ex["sets"] = max(1, ex.get("sets", 3) - 1)
                                # 更新难度级别
                                difficulty_map = {"困难": "中等", "中等": "简单", "简单": "简单"}
                                ex["difficulty"] = difficulty_map.get(ex.get("difficulty", "中等"), "简单")
                            
                            # 更新数据库中的运动信息
                            await self.plans_collection.update_one(
                                {"_id": ObjectId(plan_id)},
                                {"$inc": {"content_revision": 1}, "$set": {f"exercises.{j}": ex}}
                            )
                            break
                
                # 更新调整历史
                await self.plans_collection.update_one(
                    {"_id": ObjectId(plan_id)},
                    {"$inc": {"content_revision": 1},
                        "$set": {
                            f"adjustment_history.{i}": adj,
                            "updated_at": datetime.utcnow()
                        }
                    }
                )

                # 获取更新后的计划
                return await self.get_rehab_plan(plan_id)

        return {"error": "Adjustment not found"}

    # ── 计划统计与趋势（statistics/trends 端点服务层实现）───────────────────
    # 数据来源：rehab_plans 文档内嵌的 exercises[].progress[]。这是生产代码中
    # 唯一的真实进度写入路径（log_exercise_progress，见本文件上方），字段为
    # date（ISO 字符串或 datetime）/ completed / pain_level / difficulty_rating / notes。
    # rehab_progress 集合在生产代码中无写入方（仅 mock 数据脚本与迁移脚本），
    # 读取它只会混入模拟数据，故统计与趋势不读该集合。
    # 无对应字段的指标（关节活动度、肌肉力量）如实返回 null，并在
    # unsupported_metrics 中标注，不猜测、不模拟。
    STATISTICS_DATA_SOURCE = "rehab_plans.exercises[].progress"
    UNSUPPORTED_METRICS = ["range_of_motion", "muscle_strength"]

    @staticmethod
    def _parse_progress_date(value: Any) -> Optional[datetime]:
        """解析进度记录的 date 字段（兼容 ISO 字符串与 datetime）。"""
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value)
            except ValueError:
                return None
        return None

    def _iter_plan_progress(self, plan: Dict[str, Any]) -> List[Dict[str, Any]]:
        """展平计划文档内嵌的运动进度记录，附运动标识。"""
        entries = []
        for exercise in plan.get("exercises") or []:
            exercise_id = exercise.get("id") or exercise.get("exercise_id") \
                or exercise.get("name")
            for entry in exercise.get("progress") or []:
                entries.append({
                    "exercise_id": exercise_id,
                    "exercise_name": exercise.get("name", ""),
                    "date": self._parse_progress_date(entry.get("date")),
                    "completed": bool(entry.get("completed", False)),
                    "pain_level": entry.get("pain_level"),
                    "difficulty_rating": entry.get("difficulty_rating"),
                })
        return entries

    @staticmethod
    def _mean(values: List[float]) -> Optional[float]:
        """非空数值列表均值（保留 1 位小数），空列表返回 None。"""
        if not values:
            return None
        return round(sum(values) / len(values), 1)

    async def calculate_plan_statistics(
        self, plan_id: str, time_range: str = "all"
    ) -> Optional[Dict[str, Any]]:
        """计算康复计划的进度统计（从内嵌 exercises[].progress 聚合）。

        time_range：all / week（近 7 天）/ month（近 30 天），
        其他取值按 all 处理并在响应 data_notes 中标注。
        """
        plan = await self.get_rehab_plan(plan_id)
        if not plan:
            return None

        range_days = {"all": None, "week": 7, "month": 30}.get(time_range)
        data_notes = []
        if range_days is None and time_range != "all":
            data_notes.append(f"未知 time_range={time_range}，按 all 处理")

        entries = self._iter_plan_progress(plan)
        if range_days is not None:
            cutoff = datetime.utcnow() - timedelta(days=range_days)
            entries = [e for e in entries if e["date"] and e["date"] >= cutoff]

        total_records = len(entries)
        completed_records = sum(1 for e in entries if e["completed"])
        completion_rate = (
            round(completed_records / total_records * 100, 1)
            if total_records else None
        )
        avg_pain_level = self._mean([
            e["pain_level"] for e in entries if e["pain_level"] is not None])
        avg_difficulty_rating = self._mean([
            e["difficulty_rating"] for e in entries
            if e["difficulty_rating"] is not None])

        # 周完成率：按自然周（周一为周起点）分桶，仅统计可解析日期的记录
        weekly: Dict[str, Dict[str, Any]] = {}
        for entry in entries:
            if not entry["date"]:
                continue
            day = entry["date"].date()
            week_start = day - timedelta(days=day.weekday())
            bucket = weekly.setdefault(week_start.isoformat(),
                                       {"total": 0, "completed": 0})
            bucket["total"] += 1
            if entry["completed"]:
                bucket["completed"] += 1
        weekly_completion = [
            {
                "week_start": week_start,
                "total": bucket["total"],
                "completed": bucket["completed"],
                "completion_rate": round(
                    bucket["completed"] / bucket["total"] * 100, 1),
            }
            for week_start, bucket in sorted(weekly.items())
        ]

        # 按运动拆分
        per_exercise_map: Dict[Any, Dict[str, Any]] = {}
        for entry in entries:
            key = entry["exercise_id"]
            bucket = per_exercise_map.setdefault(key, {
                "exercise_id": entry["exercise_id"],
                "exercise_name": entry["exercise_name"],
                "total": 0, "completed": 0,
                "pain_levels": [], "difficulty_ratings": [],
            })
            bucket["total"] += 1
            if entry["completed"]:
                bucket["completed"] += 1
            if entry["pain_level"] is not None:
                bucket["pain_levels"].append(entry["pain_level"])
            if entry["difficulty_rating"] is not None:
                bucket["difficulty_ratings"].append(entry["difficulty_rating"])
        per_exercise = []
        for bucket in per_exercise_map.values():
            per_exercise.append({
                "exercise_id": bucket["exercise_id"],
                "exercise_name": bucket["exercise_name"],
                "total": bucket["total"],
                "completed": bucket["completed"],
                "completion_rate": round(
                    bucket["completed"] / bucket["total"] * 100, 1)
                if bucket["total"] else None,
                "avg_pain_level": self._mean(bucket["pain_levels"]),
                "avg_difficulty_rating": self._mean(bucket["difficulty_ratings"]),
            })

        if not entries:
            data_notes.append("计划内暂无进度记录，统计字段为空/null")

        return {
            "plan_id": plan_id,
            "time_range": time_range,
            "total_records": total_records,
            "completed_records": completed_records,
            "completion_rate": completion_rate,
            "avg_pain_level": avg_pain_level,
            "avg_difficulty_rating": avg_difficulty_rating,
            # 无对应字段的指标（关节活动度/肌肉力量）如实为 null
            "range_of_motion": None,
            "muscle_strength": None,
            "weekly_completion": weekly_completion,
            "per_exercise": per_exercise,
            "unsupported_metrics": list(self.UNSUPPORTED_METRICS),
            "data_source": self.STATISTICS_DATA_SOURCE,
            "data_notes": data_notes,
        }

    async def get_exercise_trends(
        self, plan_id: str, exercise_id: Optional[str] = None,
        metric: str = "difficulty", days: int = 30
    ) -> Optional[Dict[str, Any]]:
        """获取康复运动的趋势数据（从内嵌 exercises[].progress 按天聚合）。

        metric=difficulty/pain：当日该指标非空值的均值；
        metric=completion：当日完成率（completed/total）。
        """
        if metric not in ("difficulty", "pain", "completion"):
            return {"error": f"Unsupported metric: {metric}"}

        plan = await self.get_rehab_plan(plan_id)
        if not plan:
            return None

        entries = self._iter_plan_progress(plan)
        if exercise_id:
            # 与 log_exercise_progress 的匹配口径一致：运动 id 或名称
            entries = [
                e for e in entries
                if e["exercise_id"] == exercise_id
                or e["exercise_name"] == exercise_id
            ]

        if days is not None and days > 0:
            cutoff = datetime.utcnow() - timedelta(days=days)
            entries = [e for e in entries if e["date"] and e["date"] >= cutoff]

        # 按天分桶
        daily: Dict[str, Dict[str, Any]] = {}
        for entry in entries:
            if not entry["date"]:
                continue
            day_key = entry["date"].date().isoformat()
            bucket = daily.setdefault(day_key, {
                "total": 0, "completed": 0, "values": []})
            bucket["total"] += 1
            if entry["completed"]:
                bucket["completed"] += 1
            if metric == "pain" and entry["pain_level"] is not None:
                bucket["values"].append(entry["pain_level"])
            elif metric == "difficulty" and entry["difficulty_rating"] is not None:
                bucket["values"].append(entry["difficulty_rating"])

        series = []
        for day_key, bucket in sorted(daily.items()):
            point: Dict[str, Any] = {"date": day_key}
            if metric == "completion":
                point["total"] = bucket["total"]
                point["completed"] = bucket["completed"]
                point["completion_rate"] = round(
                    bucket["completed"] / bucket["total"] * 100, 1)
            else:
                point["value"] = self._mean(bucket["values"])
            series.append(point)

        return {
            "plan_id": plan_id,
            "exercise_id": exercise_id,
            "metric": metric,
            "days": days,
            "total_records": len(entries),
            "series": series,
            "data_source": self.STATISTICS_DATA_SOURCE,
            "data_notes": ["计划内暂无进度记录，series 为空"] if not entries else [],
        }

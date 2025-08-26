from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from motor.motor_asyncio import AsyncIOMotorDatabase
from bson.objectid import ObjectId
import numpy as np

from app.schemas.rehabilitation import (
    RehabPlanCreate, 
    RehabPlanUpdate,
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
        try:
            plan = await self.plans_collection.find_one({"_id": ObjectId(plan_id)})
            if plan:
                plan["_id"] = str(plan["_id"])
                return plan
        except Exception:
            return None
        return None
        
    async def update_rehab_plan(self, plan_id: str, plan_data: RehabPlanUpdate) -> Optional[Dict[str, Any]]:
        """Update an existing rehabilitation plan"""
        try:
            update_data = plan_data.dict(exclude_unset=True)
            update_data["updated_at"] = datetime.utcnow()
            
            result = await self.plans_collection.update_one(
                {"_id": ObjectId(plan_id)},
                {"$set": update_data}
            )
            
            if result.modified_count:
                return await self.get_rehab_plan(plan_id)
        except Exception:
            return None
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
            generated_plan = await self.agent_service.generate_rehab_plan(patient_data)
            
            if not generated_plan:
                # 如果没有生成计划，使用默认模拟数据
                print("生成计划失败，使用备用模拟数据")
                current_date = datetime.utcnow().strftime('%Y-%m-%d')
                generated_plan = {
                    "name": f"{patient_name}的康复计划 - {current_date}",
                    "description": f"针对{condition}问题的定制康复计划，目标是{goal}",
                    "patient_id": patient_id,
                    "patient_name": patient_name,
                    "condition": condition,
                    "goal": goal,
                    "duration_weeks": 6,
                    "frequency": "每周3次",
                    "exercises": [
                        {
                            "name": "基础拉伸",
                            "description": "改善关节活动范围的基础拉伸",
                            "body_part": condition,
                            "difficulty": "简单",
                            "duration_minutes": 5,
                            "repetitions": 10,
                            "sets": 2,
                            "instructions": ["保持正确姿势", "缓慢进行动作", "不要过度拉伸"],
                            "contraindications": ["急性疼痛"],
                            "benefits": ["改善灵活性", "减轻肌肉紧张"]
                        },
                        {
                            "name": "肌肉强化",
                            "description": "增强相关肌群力量",
                            "body_part": condition,
                            "difficulty": "中等",
                            "duration_minutes": 10,
                            "repetitions": 12,
                            "sets": 3,
                            "instructions": ["使用适当重量", "控制动作速度", "注意呼吸"],
                            "contraindications": ["不适当疼痛"],
                            "benefits": ["增强肌肉力量", "改善稳定性"]
                        }
                    ],
                    "phases": [
                        {
                            "name": "初始期",
                            "duration": "2周",
                            "focus": "适应与基础能力建立",
                            "description": "初步适应康复训练，建立基础能力"
                        },
                        {
                            "name": "进步期",
                            "duration": "4周",
                            "focus": "能力提升",
                            "description": "提升康复训练强度和复杂度，增强能力"
                        }
                    ],
                    "notes": "请根据自身感受调整运动强度，如有不适请立即停止并咨询医生。",
                    "status": "draft"
                }
                
            # 将生成的计划保存为草稿状态
            generated_plan["status"] = "draft"  # 标记为草稿状态
            
            # 保存到数据库
            try:
                result = await self.plans_collection.insert_one(generated_plan)
                generated_plan["_id"] = str(result.inserted_id)
            except Exception as e:
                print(f"保存到数据库失败: {str(e)}")
                # 如果数据库保存失败，仍然返回计划但添加错误标记
                if "_id" not in generated_plan:
                    generated_plan["_id"] = f"temp_{datetime.utcnow().timestamp()}"
                generated_plan["db_error"] = "保存到数据库失败，此计划为临时数据"
            
            return generated_plan
            
        except Exception as e:
            print(f"生成康复计划时发生错误: {str(e)}")
            # 返回错误信息和基本模拟数据
            fallback_plan = {
                "name": f"{patient_name}的应急康复计划",
                "description": f"针对{condition}的基础康复指导",
                "patient_id": patient_id,
                "patient_name": patient_name,
                "condition": condition,
                "goal": goal,
                "duration_weeks": 4,
                "frequency": "每周2-3次",
                "exercises": [
                    {
                        "name": "基础活动",
                        "description": "基础康复活动",
                        "body_part": condition,
                        "difficulty": "简单",
                        "duration_minutes": 5,
                        "repetitions": 10,
                        "sets": 2,
                        "instructions": ["遵医嘱进行", "循序渐进"],
                        "contraindications": ["急性疼痛"],
                        "benefits": ["维持功能", "预防并发症"]
                    }
                ],
                "notes": "这是系统生成的应急计划，请咨询专业医生获取完整康复方案。",
                "status": "draft",
                "error_info": f"生成计划时发生错误: {str(e)}"
            }
            
            try:
                # 尝试保存到数据库
                result = await self.plans_collection.insert_one(fallback_plan)
                fallback_plan["_id"] = str(result.inserted_id)
            except Exception:
                # 如果数据库保存失败，添加临时ID
                fallback_plan["_id"] = f"temp_{datetime.utcnow().timestamp()}"
                
            return fallback_plan
    
    async def approve_generated_plan(self, plan_id: str, modifications: Dict[str, Any] = None) -> Optional[Dict[str, Any]]:
        """审核并确认生成的康复计划"""
        # 使用代理服务的审核方法
        approved_plan = await self.agent_service.approve_generated_plan(plan_id, modifications)
        
        if approved_plan:
            # 将计划状态从草稿改为活跃
            approved_plan["status"] = "active"
            
            # 更新数据库
            await self.plans_collection.update_one(
                {"_id": ObjectId(plan_id)},
                {"$set": {"status": "active"}}
            )
            
        return approved_plan
        
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
                {
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
                {
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
                {
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
                        {
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
                {"$push": {"adjustment_history": adjustment_record}}
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
                                {"$set": {f"exercises.{j}": ex}}
                            )
                            break
                
                # 更新调整历史
                await self.plans_collection.update_one(
                    {"_id": ObjectId(plan_id)},
                    {
                        "$set": {
                            f"adjustment_history.{i}": adj,
                            "updated_at": datetime.utcnow()
                        }
                    }
                )
                
                # 获取更新后的计划
                return await self.get_rehab_plan(plan_id)
                
        return {"error": "Adjustment not found"} 
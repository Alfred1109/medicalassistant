from typing import List, Dict, Any, Optional
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorDatabase
from bson.objectid import ObjectId

from app.schemas.rehabilitation import (
    RehabPlanCreate, 
    RehabPlanUpdate,
    ExerciseCreate,
)
from app.services.agent_service import AgentService

class RehabilitationService:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.plans_collection = db.rehab_plans
        self.exercises_collection = db.exercises
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
        
        # 调用代理服务的LLM生成方法
        generated_plan = await self.agent_service.generate_rehab_plan(patient_data)
        
        if not generated_plan:
            return {"error": "Failed to generate rehabilitation plan"}
            
        # 将生成的计划保存为草稿状态
        generated_plan["status"] = "draft"  # 标记为草稿状态
        
        # 保存到数据库
        result = await self.plans_collection.insert_one(generated_plan)
        generated_plan["_id"] = str(result.inserted_id)
        
        return generated_plan
    
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
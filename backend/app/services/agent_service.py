from typing import List, Dict, Any, Optional
from datetime import datetime
import uuid
from motor.motor_asyncio import AsyncIOMotorDatabase
from bson.objectid import ObjectId
import os
import json
import requests

from app.core.config import settings
from app.schemas.agent import AgentCreate, AgentUpdate, AgentQuery

class AgentService:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.collection = db.agents
        
    async def create_agent(self, agent_data: AgentCreate) -> Dict[str, Any]:
        """Create a new agent with specified configuration"""
        agent = agent_data.dict()
        agent["created_at"] = datetime.utcnow()
        agent["updated_at"] = agent["created_at"]
        
        result = await self.collection.insert_one(agent)
        agent["_id"] = str(result.inserted_id)
        
        return agent
        
    async def get_agent_by_id(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Get agent by ID"""
        try:
            agent = await self.collection.find_one({"_id": ObjectId(agent_id)})
            if agent:
                agent["_id"] = str(agent["_id"])
                return agent
        except Exception:
            return None
        return None
        
    async def update_agent(self, agent_id: str, agent_data: AgentUpdate) -> Optional[Dict[str, Any]]:
        """Update an existing agent"""
        try:
            update_data = agent_data.dict(exclude_unset=True)
            update_data["updated_at"] = datetime.utcnow()
            
            result = await self.collection.update_one(
                {"_id": ObjectId(agent_id)},
                {"$set": update_data}
            )
            
            if result.modified_count:
                return await self.get_agent_by_id(agent_id)
        except Exception:
            return None
        return None
        
    async def delete_agent(self, agent_id: str) -> bool:
        """Delete an agent by ID"""
        try:
            result = await self.collection.delete_one({"_id": ObjectId(agent_id)})
            return result.deleted_count > 0
        except Exception:
            return False
            
    async def list_agents(self, skip: int = 0, limit: int = 100) -> List[Dict[str, Any]]:
        """List all agents with pagination"""
        cursor = self.collection.find().skip(skip).limit(limit)
        agents = []
        
        async for agent in cursor:
            agent["_id"] = str(agent["_id"])
            agents.append(agent)
            
        return agents
            
    async def add_tool(self, agent_id: str, tool_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Add a new tool to an existing agent"""
        try:
            agent = await self.get_agent_by_id(agent_id)
            if not agent:
                return None
                
            # Add new tool to the agent's tools list
            result = await self.collection.update_one(
                {"_id": ObjectId(agent_id)},
                {
                    "$push": {"tools": tool_data},
                    "$set": {"updated_at": datetime.utcnow()}
                }
            )
            
            if result.modified_count:
                return await self.get_agent_by_id(agent_id)
        except Exception:
            return None
        return None
        
    async def process_query(self, agent_id: str, query_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Process a query with the specified agent"""
        agent = await self.get_agent_by_id(agent_id)
        if not agent:
            return None
        
        try:
            from openai import OpenAI
            
            # 获取用户查询文本
            user_query = query_data.get("query", "")
            
            # 从代理配置获取系统提示词
            system_prompt = agent.get("system_prompt", "你是一个医疗康复助手，可以帮助患者回答康复相关的问题。")
            
            # 初始化OpenAI客户端
            client = OpenAI(
                base_url=settings.LLM_API_BASE_URL,
                api_key=settings.LLM_API_KEY,
            )
            
            # 准备消息
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_query}
            ]
            
            # 调用API
            completion = client.chat.completions.create(
                model=settings.LLM_API_MODEL,
                messages=messages,
                temperature=0.7,
                max_tokens=1500,
                top_p=0.95,
            )
            
            # 获取响应内容
            ai_response = completion.choices[0].message.content
            
            # 构建响应对象
            response = {
                "response": ai_response,
                "thinking": f"处理查询: '{user_query}' 使用代理ID: {agent_id}",
                "metadata": {
                    "model": settings.LLM_API_MODEL,
                    "agent_id": agent_id,
                    "timestamp": datetime.utcnow().isoformat()
                }
            }
            
            # 记录交互
            await self.db.agent_interactions.insert_one({
                "agent_id": agent_id,
                "query": user_query,
                "response": ai_response,
                "timestamp": datetime.utcnow()
            })
            
            return response
        
        except Exception as e:
            # 记录错误
            print(f"处理查询时出错: {str(e)}")
            
            # 返回错误响应
            return {
                "response": f"抱歉，我在处理您的问题时遇到了技术问题。请稍后再试。错误信息: {str(e)}",
                "thinking": f"处理查询时发生错误: {str(e)}",
                "metadata": {
                    "error": True,
                    "timestamp": datetime.utcnow().isoformat()
                }
            }
            
    async def generate_agent_parameters(self, config_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Generate agent parameters configuration using LLM"""
        try:
            # 获取配置信息
            agent_type = config_data.get("type", "conversation")
            model = config_data.get("model", "deepseek-v3-241226")
            system_prompt = config_data.get("system_prompt", "你是一个医疗康复助手")
            
            # 构建提示词
            prompt = f"""作为AI参数配置专家，请为以下类型的医疗康复AI助手生成最佳参数配置（JSON格式）。

助手信息:
- 类型: {agent_type}
- 使用模型: {model}
- 系统提示词: "{system_prompt}"

请根据此助手的类型和目的，生成一个合适的参数配置JSON。这些参数将用于控制模型的行为和输出。

常见参数包括:
- temperature: 控制输出的随机性（0.0到1.0）
- top_p: 用于控制输出多样性的概率阈值（0.0到1.0）
- max_tokens: 生成的最大标记数
- presence_penalty: 重复惩罚系数（-2.0到2.0）
- frequency_penalty: 频率惩罚系数（-2.0到2.0）
- 其他可能适用于这种类型助手的特定参数

请根据助手类型提供最佳参数配置:
- 对话助手: 注重流畅自然的对话体验
- 康复指导助手: 强调准确、权威和详细的康复建议
- 评估助手: 重视结构化输出和一致性
- 健康教育助手: 侧重清晰易懂的解释和全面的信息

请仅返回一个有效的JSON对象，不要包含任何其他解释或文本。参数应该适合用于{model}模型。"""

            # 调用LLM
            llm_response = await self._call_llm(prompt)
            
            # 解析JSON
            import json
            import re
            
            # 尝试从响应中提取JSON
            json_match = re.search(r'({.*})', llm_response.replace('\n', ' '), re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
                try:
                    parameters = json.loads(json_str)
                    
                    # 记录生成过程
                    await self.db.llm_generations.insert_one({
                        "type": "agent_parameters",
                        "config_data": config_data,
                        "prompt": prompt,
                        "response": llm_response,
                        "parsed_result": parameters,
                        "timestamp": datetime.utcnow()
                    })
                    
                    return parameters
                except json.JSONDecodeError:
                    print(f"无法解析LLM返回的JSON: {json_str}")
            
            print(f"无法从LLM响应中提取JSON: {llm_response}")
            return None
        except Exception as e:
            print(f"生成代理参数时出错: {str(e)}")
            return None
            
    async def generate_rehab_plan(self, patient_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Generate a rehabilitation plan using LLM"""
        try:
            # 构建提示词
            prompt = self._build_rehab_plan_prompt(patient_data)
            
            # 调用LLM
            llm_response = await self._call_llm(prompt)
            
            # 解析LLM响应
            parsed_plan = self._parse_rehab_plan_response(llm_response, patient_data)
            
            # 记录生成过程
            await self.db.llm_generations.insert_one({
                "type": "rehab_plan",
                "patient_data": patient_data,
                "prompt": prompt,
                "response": llm_response,
                "parsed_result": parsed_plan,
                "timestamp": datetime.utcnow()
            })
            
            return parsed_plan
        except Exception as e:
            print(f"Error generating rehab plan: {str(e)}")
            return None
    
    def _build_rehab_plan_prompt(self, patient_data: Dict[str, Any]) -> str:
        """构建用于生成康复计划的提示词"""
        # 提取基础数据
        condition = patient_data.get("condition", "")
        goal = patient_data.get("goal", "")
        patient_name = patient_data.get("patient_name", "")
        
        # 提取患者历史数据（如果有）
        patient_id = patient_data.get("patient_id", "")
        medical_history = patient_data.get("medical_history", "")
        age = patient_data.get("age", "")
        gender = patient_data.get("gender", "")
        physical_condition = patient_data.get("physical_condition", "")
        
        # 提取患者评估数据（如果有）
        latest_assessment = patient_data.get("latest_assessment", {})
        assessment_text = ""
        if latest_assessment:
            assessment_text = f"""
患者最新评估数据:
- 评估日期: {latest_assessment.get('date', '')}
- 关节活动度: {self._format_assessment_value(latest_assessment.get('range_of_motion', {}))}
- 肌肉力量: {self._format_assessment_value(latest_assessment.get('muscle_strength', {}))}
- 疼痛水平: {self._format_assessment_value(latest_assessment.get('pain_level', {}))}
- 功能状态: {self._format_assessment_value(latest_assessment.get('functional_status', {}))}
"""
        
        # 构建提示词
        prompt = f"""作为一名专业的康复医学专家，请为以下患者制定一份详细且个性化的康复计划。请在方案中应用循证医学原则，确保计划的安全性和有效性。

患者信息:
- 姓名: {patient_name}
- 年龄: {age}
- 性别: {gender}
- 康复需求/诊断: {condition}
- 康复目标: {goal}
- 身体状况: {physical_condition}
- 医疗历史: {medical_history}
{assessment_text}

请提供一份完整的康复计划，包括以下内容:
1. 计划名称: 应反映康复方向和主要目标
2. 计划描述: 提供详细的康复目标和预期效果
3. 分阶段计划: 将康复计划分为初始期、进步期和维持期三个阶段
4. 具体的康复运动列表（至少6-8个），每个运动应包括:
   - 运动名称（简洁明了）
   - 详细描述（目的、原理）
   - 针对的身体部位
   - 难度级别（简单/中等/困难）
   - 持续时间（分钟）
   - 重复次数和组数（明确指导）
   - 执行指南（详细步骤说明）
   - 注意事项和技巧
   - 预期益处
   - 可能的调整方案（如何简化或增加难度）
5. 运动进阶建议: 当患者达到特定标准时如何调整运动难度
6. 总体康复周期建议: 并解释为何推荐此周期
7. 进度追踪方法: 如何评估康复效果
8. 预防措施和注意事项: 针对患者特定情况的警示和建议

请以专业的医学术语结合通俗易懂的解释，使计划既专业又易于患者理解和执行。所有建议必须基于循证医学和最新康复指南。

以JSON格式返回，确保专业性、安全性和个性化。返回格式示例:

{
  "name": "计划名称",
  "description": "计划详细描述",
  "phases": [
    {
      "name": "初始期",
      "duration": "2周",
      "focus": "适应与基础能力建立",
      "description": "阶段详细描述..."
    },
    {
      "name": "进步期",
      "duration": "4周",
      "focus": "能力提升",
      "description": "阶段详细描述..."
    },
    {
      "name": "维持期",
      "duration": "持续",
      "focus": "功能维持与日常融合",
      "description": "阶段详细描述..."
    }
  ],
  "duration_weeks": 12,
  "frequency": "初始每周3次，进步期每周4-5次",
  "exercises": [
    {
      "name": "运动名称",
      "description": "运动详细描述",
      "body_part": "目标部位",
      "difficulty": "难度级别",
      "duration_minutes": 5,
      "repetitions": 10,
      "sets": 3,
      "instructions": ["步骤1", "步骤2", "步骤3"],
      "precautions": ["注意事项1", "注意事项2"],
      "benefits": ["预期益处1", "预期益处2"],
      "adjustments": {
        "easier": "如何简化",
        "harder": "如何增加难度"
      },
      "progression_criteria": "何时进阶此运动的标准"
    }
  ],
  "progress_tracking": {
    "metrics": ["追踪指标1", "追踪指标2"],
    "methods": ["追踪方法1", "追踪方法2"],
    "milestones": ["里程碑1", "里程碑2"]
  },
  "precautions": ["总体注意事项1", "总体注意事项2"],
  "notes": "其他重要信息和建议"
}
"""
        return prompt
    
    def _format_assessment_value(self, assessment_dict: Dict[str, Any]) -> str:
        """将评估数据格式化为文本描述"""
        if not assessment_dict:
            return "无数据"
            
        # 提取主要关键点（最多3个）
        key_points = []
        for key, value in assessment_dict.items():
            if len(key_points) >= 3:
                break
            if isinstance(value, (int, float)):
                key_points.append(f"{key}: {value}")
                
        return ", ".join(key_points) if key_points else "有评估数据"
        
    async def _call_llm(self, prompt: str) -> str:
        """调用LLM API获取响应"""
        # 使用华为云方舟平台API
        try:
            from openai import OpenAI
            
            # 初始化OpenAI客户端
            client = OpenAI(
                # 华为云方舟平台API地址
                base_url=settings.LLM_API_BASE_URL,
                # 使用API密钥
                api_key=settings.LLM_API_KEY,
            )
            
            # 准备系统提示和用户提示
            messages = [
                {"role": "system", "content": "你是一名专业的康复医学专家，负责根据患者信息制定个性化的康复计划。回复必须是JSON格式，不要有任何额外的注释或解释。"},
                {"role": "user", "content": prompt}
            ]
            
            # 调用API
            completion = client.chat.completions.create(
                model=settings.LLM_API_MODEL,  # 使用配置的模型
                messages=messages,
                temperature=0.7,  # 控制创造性与精确性的平衡
                max_tokens=2000,  # 限制响应长度
            )
            
            # 获取响应内容
            response_content = completion.choices[0].message.content
            
            # 日志记录
            print(f"LLM API调用成功，获取到响应")
            
            return response_content
            
        except Exception as e:
            print(f"LLM API调用失败: {str(e)}")
            
            # 如果API调用失败，使用备用的模拟数据
            print("使用备用的模拟数据...")
            
            # 模拟返回的康复计划JSON
            mock_response = {
                "name": f"定制化康复计划 - {datetime.utcnow().strftime('%Y-%m-%d')}",
                "description": "这个定制化康复计划旨在帮助患者逐步恢复功能，减轻症状，并达到设定的康复目标。",
                "duration_weeks": 8,
                "frequency": "每周3-5次",
                "exercises": [
                    {
                        "name": "颈部伸展运动",
                        "description": "温和地伸展颈部肌肉，减轻紧张感",
                        "body_part": "颈部",
                        "difficulty": "简单",
                        "duration_minutes": 5,
                        "repetitions": 10,
                        "sets": 3,
                        "instructions": [
                            "坐直，保持肩膀放松",
                            "慢慢将头向右侧倾斜，直到感觉左侧颈部有轻微拉伸",
                            "保持15-30秒",
                            "返回中心位置，然后向左侧重复"
                        ],
                        "contraindications": ["急性颈部损伤", "严重颈椎病"],
                        "benefits": ["改善颈部活动范围", "减轻肌肉紧张"]
                    },
                    {
                        "name": "肩部环绕运动",
                        "description": "增加肩部活动度和柔韧性",
                        "body_part": "肩部",
                        "difficulty": "简单",
                        "duration_minutes": 3,
                        "repetitions": 12,
                        "sets": 2,
                        "instructions": [
                            "站立或坐直",
                            "将双肩向前画圆，做5次",
                            "然后向后画圆，做5次"
                        ],
                        "contraindications": ["肩关节急性炎症"],
                        "benefits": ["增加肩部活动范围", "改善姿势"]
                    },
                    {
                        "name": "膝关节强化练习",
                        "description": "增强膝关节周围肌肉力量",
                        "body_part": "膝关节",
                        "difficulty": "中等",
                        "duration_minutes": 10,
                        "repetitions": 15,
                        "sets": 3,
                        "instructions": [
                            "坐在椅子上，背部挺直",
                            "慢慢伸直一条腿，抬高到与髋部同高",
                            "保持5秒钟",
                            "慢慢放下，重复另一条腿"
                        ],
                        "contraindications": ["急性膝关节损伤"],
                        "benefits": ["增强股四头肌", "改善膝关节稳定性"]
                    }
                ],
                "notes": "请确保在开始任何运动前进行适当的热身，如感到不适应立即停止。逐渐增加强度和持续时间，而不是一次性增加太多。",
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
                    },
                    {
                        "name": "维持期",
                        "duration": "持续",
                        "focus": "功能维持与日常融合",
                        "description": "将康复训练融入日常生活，维持并进一步提升功能"
                    }
                ],
                "progress_tracking": {
                    "metrics": ["症状改善", "功能恢复", "生活质量提升"],
                    "methods": ["定期评估", "日志记录", "功能测试"],
                    "milestones": ["初始期完成", "关键功能恢复", "回归日常活动"]
                }
            }
            
            return json.dumps(mock_response, ensure_ascii=False)
        
    def _parse_rehab_plan_response(self, llm_response: str, patient_data: Dict[str, Any]) -> Dict[str, Any]:
        """解析LLM响应为结构化康复计划"""
        try:
            # 解析JSON响应
            plan_data = json.loads(llm_response)
            
            # 添加患者信息
            plan_data["patient_id"] = patient_data.get("patient_id", "")
            plan_data["patient_name"] = patient_data.get("patient_name", "")
            plan_data["condition"] = patient_data.get("condition", "")
            plan_data["goal"] = patient_data.get("goal", "")
            
            # 确保phases字段存在
            if "phases" not in plan_data:
                plan_data["phases"] = [
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
                    },
                    {
                        "name": "维持期",
                        "duration": "持续",
                        "focus": "功能维持与日常融合",
                        "description": "将康复训练融入日常生活，维持并进一步提升功能"
                    }
                ]
            
            # 确保progress_tracking字段存在
            if "progress_tracking" not in plan_data:
                plan_data["progress_tracking"] = {
                    "metrics": ["症状改善", "功能恢复", "生活质量提升"],
                    "methods": ["定期评估", "日志记录", "功能测试"],
                    "milestones": ["初始期完成", "关键功能恢复", "回归日常活动"]
                }
            
            # 添加元数据
            plan_data["metadata"] = {
                "generated_by": "llm",
                "generation_timestamp": datetime.utcnow().isoformat(),
                "is_approved": False,  # 初始状态为未审核
                "approval_history": [],
                "version": 1,  # 计划版本号
                "last_updated": datetime.utcnow().isoformat()
            }
            
            # 转换运动为康复计划所需格式
            exercises = []
            for ex in plan_data.get("exercises", []):
                exercise = {
                    "name": ex.get("name", ""),
                    "description": ex.get("description", ""),
                    "body_part": ex.get("body_part", ""),
                    "difficulty": ex.get("difficulty", "简单"),
                    "duration_minutes": ex.get("duration_minutes", 5),
                    "repetitions": ex.get("repetitions", 10),
                    "sets": ex.get("sets", 3),
                    "instructions": ex.get("instructions", []),
                    "precautions": ex.get("precautions", []),
                    "contraindications": ex.get("contraindications", []),  # 兼容旧格式
                    "benefits": ex.get("benefits", []),
                    "adjustments": ex.get("adjustments", {"easier": "", "harder": ""}),
                    "progression_criteria": ex.get("progression_criteria", ""),
                    "phase": ex.get("phase", "初始期"),  # 运动所属阶段
                    "status": "active"  # 运动状态：active, completed, skipped
                }
                exercises.append(exercise)
                
            plan_data["exercises"] = exercises
            
            # 添加计划执行状态
            plan_data["execution_status"] = {
                "current_phase": "初始期",
                "current_week": 1,
                "adherence_rate": 0,  # 计划坚持率(0-100)
                "completed_exercises": 0,
                "total_exercises": len(exercises) * 3,  # 假设每个运动每周进行3次
                "last_updated": datetime.utcnow().isoformat()
            }
            
            # 添加计划调整历史
            plan_data["adjustment_history"] = []
            
            return plan_data
        except Exception as e:
            print(f"Error parsing LLM response: {str(e)}")
            return {}
    
    async def approve_generated_plan(self, plan_id: str, modifications: Dict[str, Any] = None) -> Optional[Dict[str, Any]]:
        """审核并确认生成的康复计划"""
        try:
            # 获取计划
            plan = await self.db.rehab_plans.find_one({"_id": ObjectId(plan_id)})
            if not plan:
                return None
                
            # 应用修改（如果有）
            if modifications:
                for key, value in modifications.items():
                    if key != "_id":
                        plan[key] = value
                        
            # 更新元数据
            if "metadata" not in plan:
                plan["metadata"] = {}
                
            plan["metadata"]["is_approved"] = True
            plan["metadata"]["approval_timestamp"] = datetime.utcnow().isoformat()
            plan["metadata"]["approval_history"].append({
                "timestamp": datetime.utcnow().isoformat(),
                "status": "approved",
                "modifications": bool(modifications)
            })
            
            # 更新计划
            await self.db.rehab_plans.update_one(
                {"_id": ObjectId(plan_id)},
                {"$set": plan}
            )
            
            plan["_id"] = str(plan["_id"])
            return plan
        except Exception as e:
            print(f"Error approving plan: {str(e)}")
            return None
        
    async def generate_assessment_analysis(self, assessment_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """生成康复评估分析与建议"""
        try:
            # 构建提示词
            prompt = self._build_assessment_analysis_prompt(assessment_data)
            
            # 调用LLM
            llm_response = await self._call_llm(prompt)
            
            # 解析LLM响应
            parsed_analysis = self._parse_assessment_analysis_response(llm_response)
            
            # 记录生成过程
            await self.db.llm_generations.insert_one({
                "type": "assessment_analysis",
                "assessment_data": assessment_data,
                "prompt": prompt,
                "response": llm_response,
                "parsed_result": parsed_analysis,
                "timestamp": datetime.utcnow()
            })
            
            return parsed_analysis
        except Exception as e:
            print(f"Error generating assessment analysis: {str(e)}")
            return None
    
    def _build_assessment_analysis_prompt(self, assessment_data: Dict[str, Any]) -> str:
        """构建用于生成康复评估分析的提示词"""
        current = assessment_data.get("current_assessment", {})
        previous = assessment_data.get("previous_assessment", {})
        differences = assessment_data.get("differences", {})
        
        # 提取患者基本信息
        patient_id = assessment_data.get("patient_id", "unknown")
        
        # 提取评估日期
        current_date = current.get("created_at", "unknown date")
        if isinstance(current_date, datetime):
            current_date = current_date.strftime("%Y-%m-%d")
            
        previous_date = "无" if not previous else previous.get("created_at", "unknown date")
        if isinstance(previous_date, datetime):
            previous_date = previous_date.strftime("%Y-%m-%d")
        
        # 提取当前评分
        current_scores = current.get("scores", {})
        overall_score = current_scores.get("overall", 0)
        
        # 提取差异数据
        score_diff = differences.get("scores", {}) if previous else {"overall": 0, "percent_change": 0}
        
        # 构建提示词
        prompt = f"""作为一名专业的康复医学专家，请分析以下康复评估结果，并提供专业的解释和建议。

患者信息：
- 患者ID: {patient_id}
- 当前评估日期: {current_date}
- 上次评估日期: {previous_date}

评估得分：
- 总体评分: {overall_score}/100
- 与上次相比变化: {score_diff.get("overall", 0)} 分 ({score_diff.get("percent_change", 0):.1f}%)

详细评估数据：
"""
        
        # 添加关节活动度数据
        if "range_of_motion" in current:
            prompt += "关节活动度:\n"
            for joint, value in current["range_of_motion"].items():
                diff_text = ""
                if previous and "range_of_motion" in previous and joint in previous["range_of_motion"]:
                    diff = value - previous["range_of_motion"][joint]
                    diff_text = f"(变化: {diff:+.1f})"
                prompt += f"- {joint}: {value} {diff_text}\n"
            
        # 添加肌肉力量数据
        if "muscle_strength" in current:
            prompt += "\n肌肉力量(0-5分):\n"
            for muscle, value in current["muscle_strength"].items():
                diff_text = ""
                if previous and "muscle_strength" in previous and muscle in previous["muscle_strength"]:
                    diff = value - previous["muscle_strength"][muscle]
                    diff_text = f"(变化: {diff:+.1f})"
                prompt += f"- {muscle}: {value} {diff_text}\n"
            
        # 添加疼痛水平数据
        if "pain_level" in current:
            prompt += "\n疼痛水平(0-10分, 0为无痛):\n"
            for location, value in current["pain_level"].items():
                diff_text = ""
                if previous and "pain_level" in previous and location in previous["pain_level"]:
                    diff = value - previous["pain_level"][location]
                    trend = "减轻" if diff < 0 else "加重" if diff > 0 else "不变"
                    diff_text = f"(变化: {diff:+.1f}, {trend})"
                prompt += f"- {location}: {value} {diff_text}\n"
            
        # 添加功能状态数据
        if "functional_status" in current:
            prompt += "\n功能状态(0-100分):\n"
            for function, value in current["functional_status"].items():
                diff_text = ""
                if previous and "functional_status" in previous and function in previous["functional_status"]:
                    diff = value - previous["functional_status"][function]
                    diff_text = f"(变化: {diff:+.1f})"
                prompt += f"- {function}: {value} {diff_text}\n"
        
        # 添加备注
        if "notes" in current:
            prompt += f"\n评估备注:\n{current['notes']}\n"
        
        prompt += """
请提供以下内容:
1. 评估结果总体解释 - 简要解释患者当前康复状态
2. 进展分析 - 与上次评估相比的进展或退步情况，重点关注变化明显的指标
3. 康复建议 - 针对评估结果提出3-5条具体的康复建议
4. 注意事项 - 患者需要注意的问题或潜在风险
5. 预期目标 - 下一阶段的合理康复目标

以JSON格式返回，结构如下:
{
  "summary": "总体评估解释",
  "progress_analysis": "进展分析",
  "recommendations": ["建议1", "建议2", "建议3", ...],
  "precautions": ["注意事项1", "注意事项2", ...],
  "next_goals": ["目标1", "目标2", ...]
}
"""
        return prompt
    
    def _parse_assessment_analysis_response(self, llm_response: str) -> Dict[str, Any]:
        """解析LLM对康复评估分析的响应"""
        try:
            # 解析JSON响应
            analysis_data = json.loads(llm_response)
            
            # 确保所有必要字段都存在
            required_fields = ["summary", "progress_analysis", "recommendations", "precautions", "next_goals"]
            for field in required_fields:
                if field not in analysis_data:
                    analysis_data[field] = []
                    if field in ["summary", "progress_analysis"]:
                        analysis_data[field] = "无数据"
            
            # 添加元数据
            analysis_data["metadata"] = {
                "generated_by": "llm",
                "generation_timestamp": datetime.utcnow().isoformat()
            }
            
            return analysis_data
        except Exception as e:
            print(f"Error parsing assessment analysis LLM response: {str(e)}")
            # 返回一个基本分析以防解析失败
            return {
                "summary": "系统无法解析评估结果，请咨询医生获取专业解释。",
                "progress_analysis": "数据解析错误，无法提供准确分析。",
                "recommendations": ["请咨询您的医生获取康复建议"],
                "precautions": ["在获得专业指导前，请遵循之前的康复方案"],
                "next_goals": ["尽快与康复医师沟通，制定合适的康复目标"],
                "metadata": {
                    "error": True,
                    "message": str(e),
                    "generation_timestamp": datetime.utcnow().isoformat()
                }
            } 
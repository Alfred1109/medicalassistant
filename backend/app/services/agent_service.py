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
        condition = patient_data.get("condition", "")
        goal = patient_data.get("goal", "")
        
        prompt = f"""作为一名专业的康复医学专家，请为以下患者制定一份详细的康复计划。
        
患者情况：
- 康复需求/诊断: {condition}
- 康复目标: {goal}

请提供一份完整的康复计划，包括以下内容：
1. 计划名称
2. 计划描述（康复目标和预期效果）
3. 具体的康复运动列表（至少5个），每个运动包括：
   - 运动名称
   - 详细描述
   - 身体部位
   - 难度级别（简单/中等/困难）
   - 持续时间（分钟）
   - 重复次数
   - 组数
   - 执行指南（步骤说明）
   - 禁忌症
   - 预期益处
4. 建议频率（每周几次）
5. 总体康复周期（几周）
6. 注意事项

以JSON格式返回，确保专业性、安全性和个性化。

JSON结构示例:
{{
  "name": "计划名称",
  "description": "计划描述",
  "duration_weeks": 8,
  "frequency": "每周3-5次",
  "exercises": [
    {{
      "name": "运动名称",
      "description": "运动描述",
      "body_part": "颈部",
      "difficulty": "简单",
      "duration_minutes": 5,
      "repetitions": 10,
      "sets": 3,
      "instructions": ["步骤1", "步骤2", "步骤3"],
      "contraindications": ["禁忌症1", "禁忌症2"],
      "benefits": ["好处1", "好处2"]
    }}
  ],
  "notes": "任何其他说明或建议"
}}
"""
        return prompt
        
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
                    },
                    {
                        "name": "平衡训练",
                        "description": "提高身体平衡能力和协调性",
                        "body_part": "全身",
                        "difficulty": "中等",
                        "duration_minutes": 5,
                        "repetitions": 0,
                        "sets": 0,
                        "instructions": [
                            "站立，双脚与肩同宽",
                            "闭上眼睛，保持平衡30秒",
                            "睁开眼睛休息",
                            "重复3-5次"
                        ],
                        "contraindications": ["严重平衡障碍", "眩晕症状"],
                        "benefits": ["提高平衡能力", "预防跌倒"]
                    },
                    {
                        "name": "深呼吸练习",
                        "description": "促进放松，改善肺功能",
                        "body_part": "呼吸系统",
                        "difficulty": "简单",
                        "duration_minutes": 5,
                        "repetitions": 10,
                        "sets": 1,
                        "instructions": [
                            "舒适坐姿或平躺",
                            "通过鼻子慢慢吸气，数4秒",
                            "屏住呼吸2秒",
                            "通过嘴巴慢慢呼气，数6秒"
                        ],
                        "contraindications": [],
                        "benefits": ["减轻焦虑", "改善肺功能", "促进放松"]
                    }
                ],
                "notes": "请确保在开始任何运动前进行适当的热身，如感到不适应立即停止。逐渐增加强度和持续时间，而不是一次性增加太多。"
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
            
            # 添加元数据
            plan_data["metadata"] = {
                "generated_by": "llm",
                "generation_timestamp": datetime.utcnow().isoformat(),
                "is_approved": False,  # 初始状态为未审核
                "approval_history": []
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
                    "contraindications": ex.get("contraindications", []),
                    "benefits": ex.get("benefits", []),
                }
                exercises.append(exercise)
                
            plan_data["exercises"] = exercises
            
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
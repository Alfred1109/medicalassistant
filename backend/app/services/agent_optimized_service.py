from typing import List, Dict, Any, Optional
from datetime import datetime
import uuid
from motor.motor_asyncio import AsyncIOMotorDatabase
from bson.objectid import ObjectId
import os
import json
import requests
import asyncio
import time
import logging
from concurrent.futures import ThreadPoolExecutor

from app.core.config import settings
from app.schemas.agent import AgentCreate, AgentUpdate, AgentQuery

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("agent_optimized_service")

# 线程池执行器
executor = ThreadPoolExecutor(max_workers=5)

class AgentOptimizedService:
    """优化版智能代理服务，重点改进响应速度和用户体验"""
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.collection = db.agents
        self.interaction_collection = db.agent_interactions
        self.cache_collection = db.agent_cache
        self.response_queue = asyncio.Queue()
        
        # 缓存设置
        self.enable_cache = True
        self.cache_ttl = 3600  # 缓存有效期（秒）
        
        # 响应优化设置
        self.streaming_enabled = True
        self.max_tokens_per_chunk = 50
        
    async def create_agent(self, agent_data: AgentCreate) -> Dict[str, Any]:
        """创建新智能代理"""
        agent = agent_data.dict()
        agent["created_at"] = datetime.utcnow()
        agent["updated_at"] = agent["created_at"]
        
        result = await self.collection.insert_one(agent)
        agent["_id"] = str(result.inserted_id)
        
        return agent
        
    async def get_agent_by_id(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """获取智能代理详情"""
        try:
            agent = await self.collection.find_one({"_id": ObjectId(agent_id)})
            if agent:
                agent["_id"] = str(agent["_id"])
                return agent
        except Exception as e:
            logger.error(f"获取代理失败: {str(e)}")
        return None
        
    async def update_agent(self, agent_id: str, agent_data: AgentUpdate) -> Optional[Dict[str, Any]]:
        """更新智能代理"""
        try:
            update_data = agent_data.dict(exclude_unset=True)
            update_data["updated_at"] = datetime.utcnow()
            
            result = await self.collection.update_one(
                {"_id": ObjectId(agent_id)},
                {"$set": update_data}
            )
            
            if result.modified_count:
                # 更新代理后清除相关缓存
                if self.enable_cache:
                    await self._clear_agent_cache(agent_id)
                    
                return await self.get_agent_by_id(agent_id)
        except Exception as e:
            logger.error(f"更新代理失败: {str(e)}")
        return None
        
    async def delete_agent(self, agent_id: str) -> bool:
        """删除智能代理"""
        try:
            result = await self.collection.delete_one({"_id": ObjectId(agent_id)})
            
            # 删除相关缓存
            if self.enable_cache:
                await self._clear_agent_cache(agent_id)
                
            return result.deleted_count > 0
        except Exception as e:
            logger.error(f"删除代理失败: {str(e)}")
            return False
            
    async def list_agents(self, skip: int = 0, limit: int = 100) -> List[Dict[str, Any]]:
        """列出所有智能代理"""
        cursor = self.collection.find().skip(skip).limit(limit)
        agents = []
        
        async for agent in cursor:
            agent["_id"] = str(agent["_id"])
            agents.append(agent)
            
        return agents
            
    async def add_tool(self, agent_id: str, tool_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """为智能代理添加工具"""
        try:
            agent = await self.get_agent_by_id(agent_id)
            if not agent:
                return None
                
            # 添加新工具
            result = await self.collection.update_one(
                {"_id": ObjectId(agent_id)},
                {
                    "$push": {"tools": tool_data},
                    "$set": {"updated_at": datetime.utcnow()}
                }
            )
            
            if result.modified_count:
                # 更新工具后清除相关缓存
                if self.enable_cache:
                    await self._clear_agent_cache(agent_id)
                    
                return await self.get_agent_by_id(agent_id)
        except Exception as e:
            logger.error(f"添加工具失败: {str(e)}")
        return None
    
    async def process_query(
        self, 
        agent_id: str, 
        query_data: Dict[str, Any],
        streaming: bool = False
    ) -> Optional[Dict[str, Any]]:
        """
        处理查询请求
        
        Args:
            agent_id: 智能代理ID
            query_data: 查询数据
            streaming: 是否启用流式响应
            
        Returns:
            响应数据
        """
        # 记录开始时间，用于性能监控
        start_time = time.time()
        
        agent = await self.get_agent_by_id(agent_id)
        if not agent:
            return None
        
        try:
            # 获取用户查询文本
            user_query = query_data.get("query", "")
            query_id = query_data.get("query_id", str(uuid.uuid4()))
            
            # 检查缓存
            if self.enable_cache:
                cache_key = f"{agent_id}:{user_query}"
                cached_response = await self._get_cache(cache_key)
                if cached_response:
                    logger.info(f"命中缓存: {cache_key}")
                    
                    # 更新使用信息
                    await self._update_cache_usage(cache_key)
                    
                    # 记录交互（即使是缓存响应）
                    await self._record_interaction(
                        agent_id, 
                        user_query, 
                        cached_response["response"], 
                        cached_response,
                        True
                    )
                    
                    # 添加性能指标
                    cached_response["performance"] = {
                        "response_time": time.time() - start_time,
                        "cached": True
                    }
                    
                    return cached_response
            
            # 从代理配置获取系统提示词
            system_prompt = agent.get("system_prompt", "你是一个医疗康复助手，可以帮助患者回答康复相关的问题。")
            
            # 获取代理参数
            model = agent.get("model", settings.LLM_API_MODEL)
            temperature = agent.get("temperature", 0.7)
            max_tokens = agent.get("max_tokens", 1500)
            
            # 如果启用流式响应
            if streaming and self.streaming_enabled:
                # 创建流式响应任务
                asyncio.create_task(
                    self._streaming_llm_call(
                        agent_id, 
                        user_query, 
                        system_prompt, 
                        model, 
                        temperature, 
                        max_tokens,
                        query_id
                    )
                )
                
                # 返回初始响应，表示流已经开始
                return {
                    "streaming": True,
                    "query_id": query_id,
                    "message": "流式响应已开始，请通过get_streaming_response接口获取响应片段",
                    "metadata": {
                        "model": model,
                        "agent_id": agent_id,
                        "timestamp": datetime.utcnow().isoformat()
                    }
                }
            
            # 如果不是流式响应，执行标准调用
            from openai import OpenAI
            
            # 初始化OpenAI客户端
            client = OpenAI(
                base_url=settings.LLM_API_BASE_URL,
                api_key=settings.LLM_API_KEY,
            )
            
            # 优化系统提示词
            optimized_system_prompt = self._optimize_system_prompt(system_prompt, user_query)
            
            # 准备消息
            messages = [
                {"role": "system", "content": optimized_system_prompt},
                {"role": "user", "content": user_query}
            ]
            
            # 使用线程池执行LLM调用，避免阻塞
            completion_future = asyncio.get_event_loop().run_in_executor(
                executor,
                lambda: client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    top_p=0.95,
                )
            )
            
            # 等待响应，设置超时
            completion = await asyncio.wait_for(completion_future, timeout=30.0)
            
            # 获取响应内容
            ai_response = completion.choices[0].message.content
            
            # 构建响应对象
            response = {
                "response": ai_response,
                "thinking": f"处理查询: '{user_query}' 使用代理ID: {agent_id}",
                "metadata": {
                    "model": model,
                    "agent_id": agent_id,
                    "timestamp": datetime.utcnow().isoformat(),
                    "query_id": query_id
                },
                "performance": {
                    "response_time": time.time() - start_time,
                    "cached": False
                }
            }
            
            # 记录交互
            await self._record_interaction(agent_id, user_query, ai_response, response)
            
            # 缓存响应
            if self.enable_cache:
                cache_key = f"{agent_id}:{user_query}"
                await self._set_cache(cache_key, response)
            
            return response
        
        except asyncio.TimeoutError:
            # 处理超时情况
            logger.error(f"LLM请求超时: agent_id={agent_id}")
            
            return {
                "response": "抱歉，系统处理您的请求时发生超时。请稍后再试或尝试简化您的问题。",
                "thinking": "LLM请求超时",
                "metadata": {
                    "error": True,
                    "error_type": "timeout",
                    "agent_id": agent_id,
                    "timestamp": datetime.utcnow().isoformat()
                },
                "performance": {
                    "response_time": time.time() - start_time,
                    "error": "timeout"
                }
            }
        except Exception as e:
            # 记录错误
            logger.error(f"处理查询时出错: {str(e)}")
            
            # 返回错误响应
            return {
                "response": f"抱歉，我在处理您的问题时遇到了技术问题。请稍后再试。",
                "thinking": f"处理查询时发生错误: {str(e)}",
                "metadata": {
                    "error": True,
                    "error_type": "processing",
                    "agent_id": agent_id,
                    "timestamp": datetime.utcnow().isoformat()
                },
                "performance": {
                    "response_time": time.time() - start_time,
                    "error": str(e)
                }
            }
    
    async def get_streaming_response(self, query_id: str) -> Optional[Dict[str, Any]]:
        """
        获取流式响应片段
        
        Args:
            query_id: 查询ID
            
        Returns:
            响应片段或None（如果队列为空）
        """
        try:
            # 检查队列中是否有相关响应
            if not self.response_queue.empty():
                # 获取一个响应，但不会阻塞
                response = self.response_queue.get_nowait()
                
                # 检查是否是对应查询的响应
                if response.get("query_id") == query_id:
                    return response
                else:
                    # 不是当前查询的响应，放回队列
                    await self.response_queue.put(response)
            
            return None
        except asyncio.QueueEmpty:
            return None
        except Exception as e:
            logger.error(f"获取流式响应出错: {str(e)}")
            return None
    
    async def get_interaction_history(
        self, 
        agent_id: str, 
        limit: int = 20, 
        skip: int = 0
    ) -> List[Dict[str, Any]]:
        """获取代理交互历史"""
        try:
            cursor = self.interaction_collection.find(
                {"agent_id": agent_id}
            ).sort("timestamp", -1).skip(skip).limit(limit)
            
            interactions = []
            async for doc in cursor:
                doc["_id"] = str(doc["_id"])
                interactions.append(doc)
                
            return interactions
        except Exception as e:
            logger.error(f"获取交互历史出错: {str(e)}")
            return []
    
    async def get_query_response_time_stats(self, agent_id: str) -> Dict[str, Any]:
        """获取查询响应时间统计"""
        try:
            # 聚合查询，计算平均响应时间
            pipeline = [
                {"$match": {"agent_id": agent_id}},
                {"$group": {
                    "_id": None,
                    "avg_response_time": {"$avg": "$performance.response_time"},
                    "min_response_time": {"$min": "$performance.response_time"},
                    "max_response_time": {"$max": "$performance.response_time"},
                    "total_queries": {"$sum": 1}
                }}
            ]
            
            cursor = self.interaction_collection.aggregate(pipeline)
            
            async for doc in cursor:
                return {
                    "agent_id": agent_id,
                    "avg_response_time": doc.get("avg_response_time"),
                    "min_response_time": doc.get("min_response_time"),
                    "max_response_time": doc.get("max_response_time"),
                    "total_queries": doc.get("total_queries")
                }
                
            # 如果没有数据
            return {
                "agent_id": agent_id,
                "avg_response_time": None,
                "min_response_time": None,
                "max_response_time": None,
                "total_queries": 0
            }
        except Exception as e:
            logger.error(f"获取响应时间统计出错: {str(e)}")
            return {
                "agent_id": agent_id,
                "error": str(e)
            }
    
    async def clear_cache(self, agent_id: Optional[str] = None) -> Dict[str, Any]:
        """清除缓存"""
        try:
            if agent_id:
                # 清除特定代理的缓存
                await self._clear_agent_cache(agent_id)
                return {"status": "success", "message": f"已清除代理ID {agent_id} 的缓存"}
            else:
                # 清除所有缓存
                await self.cache_collection.delete_many({})
                return {"status": "success", "message": "已清除所有缓存"}
        except Exception as e:
            logger.error(f"清除缓存出错: {str(e)}")
            return {"status": "error", "message": f"清除缓存时发生错误: {str(e)}"}
    
    def _optimize_system_prompt(self, system_prompt: str, user_query: str) -> str:
        """
        基于用户查询优化系统提示词
        
        Args:
            system_prompt: 原始系统提示词
            user_query: 用户查询
            
        Returns:
            优化后的系统提示词
        """
        # 基础优化：保持原始提示词
        optimized_prompt = system_prompt
        
        # 增加响应质量提升指令
        optimized_prompt += "\n\n请提供准确、专业且易于理解的回答。优先使用简明扼要的语言表达核心信息，避免不必要的冗长回复。"
        
        # 如果查询包含特定关键词，添加相应的专业指导
        lower_query = user_query.lower()
        
        if "疼痛" in lower_query or "痛" in lower_query:
            optimized_prompt += "\n\n在回答疼痛相关问题时，请考虑疼痛的类型、持续时间、严重程度和影响因素，并提供科学的缓解建议。"
            
        if "运动" in lower_query or "锻炼" in lower_query or "活动" in lower_query:
            optimized_prompt += "\n\n在回答运动相关问题时，请考虑患者的具体情况，提供安全、适度和渐进式的运动建议。"
            
        if "康复" in lower_query or "恢复" in lower_query:
            optimized_prompt += "\n\n在回答康复相关问题时，请强调康复是一个渐进过程，需要专业指导和患者的积极参与。"
            
        return optimized_prompt
    
    async def _streaming_llm_call(
        self, 
        agent_id: str, 
        user_query: str, 
        system_prompt: str, 
        model: str, 
        temperature: float, 
        max_tokens: int,
        query_id: str
    ) -> None:
        """
        执行流式LLM调用
        
        Args:
            agent_id: 智能代理ID
            user_query: 用户查询
            system_prompt: 系统提示词
            model: 模型名称
            temperature: 温度参数
            max_tokens: 最大令牌数
            query_id: 查询ID
        """
        try:
            # 记录开始时间
            start_time = time.time()
            
            from openai import OpenAI
            
            # 初始化OpenAI客户端
            client = OpenAI(
                base_url=settings.LLM_API_BASE_URL,
                api_key=settings.LLM_API_KEY,
            )
            
            # 优化系统提示词
            optimized_system_prompt = self._optimize_system_prompt(system_prompt, user_query)
            
            # 准备消息
            messages = [
                {"role": "system", "content": optimized_system_prompt},
                {"role": "user", "content": user_query}
            ]
            
            # 创建流式调用
            stream = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                top_p=0.95,
                stream=True
            )
            
            # 收集完整响应
            full_response = ""
            chunk_index = 0
            
            # 遍历流式响应
            for chunk in stream:
                if hasattr(chunk.choices[0], 'delta') and hasattr(chunk.choices[0].delta, 'content'):
                    content = chunk.choices[0].delta.content
                    if content:
                        # 累积完整响应
                        full_response += content
                        
                        # 将响应片段添加到队列
                        await self.response_queue.put({
                            "query_id": query_id,
                            "chunk_index": chunk_index,
                            "content": content,
                            "done": False,
                            "timestamp": datetime.utcnow().isoformat()
                        })
                        
                        chunk_index += 1
            
            # 添加完成标记
            await self.response_queue.put({
                "query_id": query_id,
                "chunk_index": chunk_index,
                "content": "",
                "done": True,
                "full_response": full_response,
                "timestamp": datetime.utcnow().isoformat()
            })
            
            # 记录交互
            performance_data = {
                "response_time": time.time() - start_time,
                "cached": False,
                "streaming": True
            }
            
            await self._record_interaction(
                agent_id, 
                user_query, 
                full_response, 
                {
                    "response": full_response,
                    "metadata": {
                        "model": model,
                        "agent_id": agent_id,
                        "query_id": query_id
                    },
                    "performance": performance_data
                },
                False
            )
            
            # 缓存完整响应
            if self.enable_cache:
                cache_key = f"{agent_id}:{user_query}"
                await self._set_cache(
                    cache_key, 
                    {
                        "response": full_response,
                        "metadata": {
                            "model": model,
                            "agent_id": agent_id,
                            "timestamp": datetime.utcnow().isoformat()
                        },
                        "performance": performance_data
                    }
                )
            
        except Exception as e:
            logger.error(f"流式调用出错: {str(e)}")
            
            # 添加错误标记
            await self.response_queue.put({
                "query_id": query_id,
                "error": True,
                "error_message": str(e),
                "done": True,
                "timestamp": datetime.utcnow().isoformat()
            })
    
    async def _record_interaction(
        self, 
        agent_id: str, 
        query: str, 
        response: str, 
        metadata: Dict[str, Any],
        from_cache: bool = False
    ) -> None:
        """记录代理交互"""
        try:
            interaction = {
                "agent_id": agent_id,
                "query": query,
                "response": response,
                "timestamp": datetime.utcnow(),
                "metadata": metadata.get("metadata", {}),
                "performance": metadata.get("performance", {}),
                "from_cache": from_cache
            }
            
            await self.interaction_collection.insert_one(interaction)
        except Exception as e:
            logger.error(f"记录交互出错: {str(e)}")
    
    async def _get_cache(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """从缓存获取响应"""
        try:
            cache_item = await self.cache_collection.find_one({"key": cache_key})
            
            if cache_item:
                # 检查是否过期
                if "expire_at" in cache_item:
                    expire_time = cache_item["expire_at"]
                    if expire_time < datetime.utcnow():
                        # 已过期，删除缓存
                        await self.cache_collection.delete_one({"key": cache_key})
                        return None
                
                return cache_item["value"]
            
            return None
        except Exception as e:
            logger.error(f"获取缓存出错: {str(e)}")
            return None
    
    async def _set_cache(self, cache_key: str, value: Dict[str, Any]) -> bool:
        """设置缓存"""
        try:
            # 设置过期时间
            expire_at = datetime.utcnow() + timedelta(seconds=self.cache_ttl)
            
            # 更新或插入缓存
            await self.cache_collection.update_one(
                {"key": cache_key},
                {
                    "$set": {
                        "key": cache_key,
                        "value": value,
                        "expire_at": expire_at,
                        "created_at": datetime.utcnow(),
                        "access_count": 0
                    }
                },
                upsert=True
            )
            
            return True
        except Exception as e:
            logger.error(f"设置缓存出错: {str(e)}")
            return False
    
    async def _update_cache_usage(self, cache_key: str) -> None:
        """更新缓存使用信息"""
        try:
            await self.cache_collection.update_one(
                {"key": cache_key},
                {
                    "$inc": {"access_count": 1},
                    "$set": {"last_accessed": datetime.utcnow()}
                }
            )
        except Exception as e:
            logger.error(f"更新缓存使用信息出错: {str(e)}")
    
    async def _clear_agent_cache(self, agent_id: str) -> None:
        """清除特定代理的缓存"""
        try:
            # 查找包含指定代理ID的所有键
            cache_keys = []
            cursor = self.cache_collection.find()
            
            async for item in cursor:
                key = item.get("key", "")
                if key.startswith(f"{agent_id}:"):
                    cache_keys.append(key)
            
            # 删除找到的缓存项
            for key in cache_keys:
                await self.cache_collection.delete_one({"key": key})
                
        except Exception as e:
            logger.error(f"清除代理缓存出错: {str(e)}")
    
    async def generate_agent_parameters(self, config_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """生成代理参数配置"""
        try:
            # 获取配置信息
            agent_type = config_data.get("type", "conversation")
            model = config_data.get("model", settings.LLM_API_MODEL)
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

            # 调用优化版的LLM
            response = await self.process_query(
                "system",  # 使用系统代理
                {
                    "query": prompt,
                    "query_id": f"genparams_{uuid.uuid4()}"
                }
            )
            
            if not response or "response" not in response:
                logger.error("生成代理参数时未获得有效响应")
                return None
                
            llm_response = response["response"]
            
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
                    logger.error(f"无法解析LLM返回的JSON: {json_str}")
            
            logger.error(f"无法从LLM响应中提取JSON: {llm_response}")
            return None
        except Exception as e:
            logger.error(f"生成代理参数时出错: {str(e)}")
            return None 
from typing import List, Optional, Any, Dict
from fastapi import APIRouter, Depends, HTTPException, Body, Query, BackgroundTasks
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.db.mongodb import get_database
from app.services.agent_optimized_service import AgentOptimizedService
from app.core.dependencies import get_current_user
from app.models.user import User
from app.schemas.agent import AgentCreate, AgentUpdate

router = APIRouter()

@router.post("/agents")
async def create_agent(
    agent_data: AgentCreate,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: User = Depends(get_current_user)
):
    """创建新智能代理"""
    agent_service = AgentOptimizedService(db)
    agent = await agent_service.create_agent(agent_data)
    return agent

@router.get("/agents/{agent_id}")
async def get_agent(
    agent_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: User = Depends(get_current_user)
):
    """获取智能代理详情"""
    agent_service = AgentOptimizedService(db)
    agent = await agent_service.get_agent_by_id(agent_id)
    
    if not agent:
        raise HTTPException(status_code=404, detail="智能代理不存在")
    
    return agent

@router.put("/agents/{agent_id}")
async def update_agent(
    agent_id: str,
    agent_data: AgentUpdate,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: User = Depends(get_current_user)
):
    """更新智能代理"""
    agent_service = AgentOptimizedService(db)
    agent = await agent_service.update_agent(agent_id, agent_data)
    
    if not agent:
        raise HTTPException(status_code=404, detail="智能代理不存在或更新失败")
    
    return agent

@router.delete("/agents/{agent_id}")
async def delete_agent(
    agent_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: User = Depends(get_current_user)
):
    """删除智能代理"""
    agent_service = AgentOptimizedService(db)
    success = await agent_service.delete_agent(agent_id)
    
    if not success:
        raise HTTPException(status_code=404, detail="智能代理不存在或删除失败")
    
    return {"status": "success", "message": "智能代理已删除"}

@router.get("/agents")
async def list_agents(
    skip: int = 0,
    limit: int = 100,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: User = Depends(get_current_user)
):
    """列出所有智能代理"""
    agent_service = AgentOptimizedService(db)
    agents = await agent_service.list_agents(skip, limit)
    return agents

@router.post("/agents/{agent_id}/tools")
async def add_tool(
    agent_id: str,
    tool_data: Dict[str, Any] = Body(...),
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: User = Depends(get_current_user)
):
    """为智能代理添加工具"""
    agent_service = AgentOptimizedService(db)
    agent = await agent_service.add_tool(agent_id, tool_data)
    
    if not agent:
        raise HTTPException(status_code=404, detail="智能代理不存在或添加工具失败")
    
    return agent

@router.post("/agents/{agent_id}/query")
async def process_query(
    agent_id: str,
    query_data: Dict[str, Any] = Body(...),
    streaming: bool = Query(False),
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: User = Depends(get_current_user)
):
    """
    处理查询请求
    
    可选参数streaming=true启用流式响应
    """
    agent_service = AgentOptimizedService(db)
    response = await agent_service.process_query(agent_id, query_data, streaming)
    
    if not response:
        raise HTTPException(status_code=404, detail="智能代理不存在或处理查询失败")
    
    return response

@router.get("/agents/streaming/{query_id}")
async def get_streaming_response(
    query_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: User = Depends(get_current_user)
):
    """
    获取流式响应片段
    
    需要轮询此接口获取完整响应
    """
    agent_service = AgentOptimizedService(db)
    response = await agent_service.get_streaming_response(query_id)
    
    # 注意：这里我们不返回404，因为可能只是暂时没有新的响应片段
    return response or {"query_id": query_id, "content": "", "done": False}

@router.get("/agents/{agent_id}/history")
async def get_interaction_history(
    agent_id: str,
    limit: int = 20,
    skip: int = 0,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: User = Depends(get_current_user)
):
    """获取代理交互历史"""
    agent_service = AgentOptimizedService(db)
    history = await agent_service.get_interaction_history(agent_id, limit, skip)
    return history

@router.get("/agents/{agent_id}/stats")
async def get_agent_stats(
    agent_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: User = Depends(get_current_user)
):
    """获取代理性能统计"""
    agent_service = AgentOptimizedService(db)
    stats = await agent_service.get_query_response_time_stats(agent_id)
    return stats

@router.post("/agents/{agent_id}/cache/clear")
async def clear_agent_cache(
    agent_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: User = Depends(get_current_user)
):
    """清除特定代理的缓存"""
    agent_service = AgentOptimizedService(db)
    result = await agent_service.clear_cache(agent_id)
    return result

@router.post("/agents/cache/clear")
async def clear_all_cache(
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: User = Depends(get_current_user)
):
    """清除所有代理缓存"""
    agent_service = AgentOptimizedService(db)
    result = await agent_service.clear_cache()
    return result

@router.post("/agents/generate-parameters")
async def generate_agent_parameters(
    config_data: Dict[str, Any] = Body(...),
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: User = Depends(get_current_user)
):
    """生成代理参数配置"""
    agent_service = AgentOptimizedService(db)
    parameters = await agent_service.generate_agent_parameters(config_data)
    
    if not parameters:
        raise HTTPException(status_code=400, detail="参数生成失败")
    
    return parameters 
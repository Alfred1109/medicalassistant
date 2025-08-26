from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Dict, Any, Optional

from app.schemas.agent import AgentCreate, AgentUpdate, AgentResponse, AgentQueryResponse
from app.services.agent_service import AgentService
from app.core.dependencies import get_agent_service

router = APIRouter()

@router.post("/", response_model=AgentResponse, status_code=status.HTTP_201_CREATED)
async def create_agent(
    agent_data: AgentCreate,
    agent_service: AgentService = Depends(get_agent_service)
):
    """Create a new dynamic agent with specified capabilities"""
    return await agent_service.create_agent(agent_data)

@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(
    agent_id: str,
    agent_service: AgentService = Depends(get_agent_service)
):
    """Get agent details by ID"""
    agent = await agent_service.get_agent_by_id(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent

@router.put("/{agent_id}", response_model=AgentResponse)
async def update_agent(
    agent_id: str,
    agent_data: AgentUpdate,
    agent_service: AgentService = Depends(get_agent_service)
):
    """Update an existing agent's configuration"""
    agent = await agent_service.update_agent(agent_id, agent_data)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent

@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(
    agent_id: str,
    agent_service: AgentService = Depends(get_agent_service)
):
    """Delete an agent by ID"""
    success = await agent_service.delete_agent(agent_id)
    if not success:
        raise HTTPException(status_code=404, detail="Agent not found")

@router.post("/{agent_id}/query", response_model=AgentQueryResponse)
async def query_agent(
    agent_id: str,
    query: Dict[str, Any],
    agent_service: AgentService = Depends(get_agent_service)
):
    """Send a query to the agent and get a response"""
    response = await agent_service.process_query(agent_id, query)
    if not response:
        raise HTTPException(status_code=404, detail="Agent not found or query processing failed")
    return response

@router.get("/", response_model=List[AgentResponse])
async def list_agents(
    skip: int = 0,
    limit: int = 100,
    agent_service: AgentService = Depends(get_agent_service)
):
    """List all available agents with pagination"""
    return await agent_service.list_agents(skip, limit)

@router.post("/{agent_id}/tools", response_model=Dict[str, Any])
async def add_tool_to_agent(
    agent_id: str,
    tool_data: Dict[str, Any],
    agent_service: AgentService = Depends(get_agent_service)
):
    """Add a new tool/capability to an existing agent"""
    result = await agent_service.add_tool(agent_id, tool_data)
    if not result:
        raise HTTPException(status_code=404, detail="Agent not found or tool addition failed")
    return result

@router.post("/generate-parameters", response_model=Dict[str, Any])
async def generate_agent_parameters(
    config_data: Dict[str, Any],
    agent_service: AgentService = Depends(get_agent_service)
):
    """Generate agent parameters configuration using LLM"""
    parameters = await agent_service.generate_agent_parameters(config_data)
    if not parameters:
        raise HTTPException(status_code=500, detail="Failed to generate parameters")
    return {"parameters": parameters} 
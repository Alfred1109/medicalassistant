from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime

class Tool(BaseModel):
    name: str
    description: str
    parameters: Dict[str, Any]
    required_parameters: List[str]
    
class AgentBase(BaseModel):
    name: str
    description: str
    model: str
    system_prompt: str
    tools: Optional[List[Tool]] = []
    metadata: Optional[Dict[str, Any]] = {}
    
class AgentCreate(AgentBase):
    pass
    
class AgentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    model: Optional[str] = None
    system_prompt: Optional[str] = None
    tools: Optional[List[Tool]] = None
    metadata: Optional[Dict[str, Any]] = None
    
class AgentResponse(BaseModel):
    id: str = Field(..., alias="_id")
    name: str
    description: str
    model: str
    system_prompt: str
    tools: Optional[List[Tool]] = []
    metadata: Optional[Dict[str, Any]] = {}
    created_at: datetime
    updated_at: datetime
    
    class Config:
        orm_mode = True
        allow_population_by_field_name = True
        
class AgentQuery(BaseModel):
    query: str
    parameters: Optional[Dict[str, Any]] = {}
    user_id: Optional[str] = None
    
class AgentQueryResponse(BaseModel):
    response: str
    thinking: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    metadata: Optional[Dict[str, Any]] = {} 
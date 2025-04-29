"""
智能代理模型
定义智能代理及其工具
"""
from datetime import datetime
from bson import ObjectId
from typing import Dict, List, Optional, Any

class AgentTool:
    """代理工具模型"""
    
    def __init__(
        self,
        name: str,
        description: str,
        parameters: Dict[str, Any],
        required_parameters: List[str] = None
    ):
        self.name = name
        self.description = description
        self.parameters = parameters
        self.required_parameters = required_parameters or []
    
    def to_dict(self):
        """将工具对象转换为字典"""
        return self.__dict__.copy()
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]):
        """从字典创建工具对象"""
        return cls(**data)


class Agent:
    """智能代理模型"""
    collection_name = "agents"
    
    def __init__(
        self,
        name: str,
        description: str,
        model: str,
        system_prompt: str,
        tools: List[Dict[str, Any]] = None,
        created_by: str = None,
        organization_id: str = None,
        is_public: bool = False,
        usage_count: int = 0,
        rating: float = None,
        created_at: datetime = None,
        updated_at: datetime = None,
        _id: str = None,
        metadata: Dict[str, Any] = None
    ):
        self.name = name
        self.description = description
        self.model = model
        self.system_prompt = system_prompt
        self.tools = tools or []
        self.created_by = created_by
        self.organization_id = organization_id
        self.is_public = is_public
        self.usage_count = usage_count
        self.rating = rating
        self.created_at = created_at or datetime.utcnow()
        self.updated_at = updated_at or datetime.utcnow()
        self._id = _id or str(ObjectId())
        self.metadata = metadata or {}
    
    @classmethod
    def from_mongo(cls, mongo_doc):
        """从MongoDB文档创建代理对象"""
        if not mongo_doc:
            return None
            
        agent_data = mongo_doc.copy()
        agent_data["_id"] = str(agent_data["_id"])
        
        return cls(**agent_data)
    
    def to_mongo(self):
        """将代理对象转换为MongoDB文档"""
        doc = self.__dict__.copy()
        if doc.get("_id") and isinstance(doc["_id"], str):
            doc["_id"] = ObjectId(doc["_id"])
        return doc
    
    def to_dict(self):
        """将代理对象转换为字典，用于API响应"""
        return self.__dict__.copy()
    
    def add_tool(self, tool: AgentTool):
        """添加工具到代理"""
        self.tools.append(tool.to_dict())
        self.updated_at = datetime.utcnow()
    
    def remove_tool(self, tool_name: str):
        """从代理中移除工具"""
        self.tools = [t for t in self.tools if t["name"] != tool_name]
        self.updated_at = datetime.utcnow()
    
    def update_system_prompt(self, system_prompt: str):
        """更新系统提示词"""
        self.system_prompt = system_prompt
        self.updated_at = datetime.utcnow()
    
    def increment_usage(self):
        """增加使用计数"""
        self.usage_count += 1
        self.updated_at = datetime.utcnow()
    
    def update_rating(self, new_rating: float):
        """更新评分"""
        if self.rating is None:
            self.rating = new_rating
        else:
            # 简单平均
            self.rating = (self.rating + new_rating) / 2
        self.updated_at = datetime.utcnow()


class AgentInteraction:
    """代理交互记录模型"""
    collection_name = "agent_interactions"
    
    def __init__(
        self,
        agent_id: str,
        user_id: str,
        query: str,
        response: str,
        thinking: str = None,
        tool_calls: List[Dict[str, Any]] = None,
        session_id: str = None,
        context: Dict[str, Any] = None,
        is_helpful: bool = None,
        user_feedback: str = None,
        created_at: datetime = None,
        _id: str = None,
        metadata: Dict[str, Any] = None
    ):
        self.agent_id = agent_id
        self.user_id = user_id
        self.query = query
        self.response = response
        self.thinking = thinking
        self.tool_calls = tool_calls or []
        self.session_id = session_id
        self.context = context or {}
        self.is_helpful = is_helpful
        self.user_feedback = user_feedback
        self.created_at = created_at or datetime.utcnow()
        self._id = _id or str(ObjectId())
        self.metadata = metadata or {}
    
    @classmethod
    def from_mongo(cls, mongo_doc):
        """从MongoDB文档创建交互记录对象"""
        if not mongo_doc:
            return None
            
        data = mongo_doc.copy()
        data["_id"] = str(data["_id"])
        
        return cls(**data)
    
    def to_mongo(self):
        """将交互记录对象转换为MongoDB文档"""
        doc = self.__dict__.copy()
        if doc.get("_id") and isinstance(doc["_id"], str):
            doc["_id"] = ObjectId(doc["_id"])
        return doc
    
    def to_dict(self):
        """将交互记录对象转换为字典，用于API响应"""
        return self.__dict__.copy()
    
    def add_feedback(self, is_helpful: bool, feedback_text: str = None):
        """添加用户反馈"""
        self.is_helpful = is_helpful
        self.user_feedback = feedback_text 
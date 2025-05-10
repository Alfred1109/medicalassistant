"""
高级数据过滤服务
用于处理复杂的数据过滤条件和查询构建
"""
from typing import List, Dict, Any, Optional, Union
from datetime import datetime
import re
from bson import ObjectId

from ..db.mongodb import get_db


class DataFilterService:
    """数据过滤服务，用于构建和执行复杂的查询条件"""
    
    def __init__(self):
        """初始化数据过滤服务"""
        self.db = None
    
    async def init_db(self):
        """初始化数据库连接"""
        if not self.db:
            self.db = await get_db()
    
    def build_filter_query(self, conditions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        根据过滤条件构建MongoDB查询对象
        
        参数:
        - conditions: 过滤条件列表
        
        返回:
        - MongoDB查询对象
        """
        if not conditions:
            return {}
        
        # 处理条件组合逻辑
        query_parts = []
        
        for i, condition in enumerate(conditions):
            # 第一个条件不使用逻辑运算符
            if i == 0:
                query_parts.append(self._build_single_condition(condition))
                continue
            
            # 使用逻辑运算符组合条件
            logic = condition.get("logic", "AND").upper()
            
            if logic == "AND":
                query_parts.append(self._build_single_condition(condition))
            elif logic == "OR":
                # 如果是OR，需要调整查询结构
                if len(query_parts) == 1:
                    # 如果只有一个前置条件，需要将其包装成$and数组
                    query_parts = [{"$and": query_parts}]
                
                # 添加OR条件
                query_parts.append({"$or": [self._build_single_condition(condition)]})
        
        # 组合最终查询
        if len(query_parts) == 1:
            return query_parts[0]
        else:
            # 检查是否有OR逻辑
            has_or = any("$or" in part for part in query_parts)
            
            if has_or:
                # 如果有OR逻辑，需要使用$or组合
                or_parts = []
                and_parts = []
                
                for part in query_parts:
                    if "$or" in part:
                        or_parts.extend(part["$or"])
                    else:
                        and_parts.append(part)
                
                if and_parts:
                    or_parts.append({"$and": and_parts})
                
                return {"$or": or_parts}
            else:
                # 如果全是AND逻辑，直接使用$and组合
                return {"$and": query_parts}
    
    def _build_single_condition(self, condition: Dict[str, Any]) -> Dict[str, Any]:
        """
        构建单个过滤条件
        
        参数:
        - condition: 单个过滤条件
        
        返回:
        - MongoDB查询条件
        """
        field = condition.get("field")
        operator = condition.get("operator")
        value = condition.get("value")
        value_type = condition.get("type", "string")
        
        # 根据类型转换值
        if value_type == "number" and value not in ["", None]:
            try:
                if isinstance(value, list):
                    value = [float(v) for v in value]
                else:
                    value = float(value)
            except (ValueError, TypeError):
                pass
        elif value_type == "date" and value not in ["", None]:
            try:
                if isinstance(value, list):
                    value = [self._parse_date(v) for v in value]
                else:
                    value = self._parse_date(value)
            except (ValueError, TypeError):
                pass
        elif value_type == "boolean" and value not in ["", None]:
            try:
                if isinstance(value, str):
                    value = value.lower() in ["true", "1", "yes"]
                else:
                    value = bool(value)
            except (ValueError, TypeError):
                pass
        
        # 根据操作符构建查询条件
        if operator == "equals":
            return {field: value}
        elif operator == "notEquals":
            return {field: {"$ne": value}}
        elif operator == "contains":
            if isinstance(value, str):
                return {field: {"$regex": re.escape(value), "$options": "i"}}
            return {}
        elif operator == "startsWith":
            if isinstance(value, str):
                return {field: {"$regex": f"^{re.escape(value)}", "$options": "i"}}
            return {}
        elif operator == "endsWith":
            if isinstance(value, str):
                return {field: {"$regex": f"{re.escape(value)}$", "$options": "i"}}
            return {}
        elif operator == "isEmpty":
            return {"$or": [{field: ""}, {field: None}, {field: {"$exists": False}}]}
        elif operator == "isNotEmpty":
            return {"$and": [{field: {"$ne": ""}}, {field: {"$ne": None}}, {field: {"$exists": True}}]}
        elif operator == "greaterThan":
            return {field: {"$gt": value}}
        elif operator == "lessThan":
            return {field: {"$lt": value}}
        elif operator == "greaterOrEqual":
            return {field: {"$gte": value}}
        elif operator == "lessOrEqual":
            return {field: {"$lte": value}}
        elif operator == "between":
            if isinstance(value, list) and len(value) == 2:
                return {field: {"$gte": value[0], "$lte": value[1]}}
            return {}
        elif operator == "before":
            return {field: {"$lt": value}}
        elif operator == "after":
            return {field: {"$gt": value}}
        else:
            # 默认情况下使用相等操作符
            return {field: value}
    
    def _parse_date(self, date_str: str) -> datetime:
        """
        解析日期字符串为datetime对象
        
        参数:
        - date_str: 日期字符串 (YYYY-MM-DD格式)
        
        返回:
        - datetime对象
        """
        try:
            if "T" in date_str:
                # ISO格式 (YYYY-MM-DDTHH:MM:SS)
                return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            else:
                # 简单日期格式 (YYYY-MM-DD)
                parts = date_str.split("-")
                if len(parts) == 3:
                    year, month, day = map(int, parts)
                    return datetime(year, month, day)
        except (ValueError, TypeError):
            pass
        
        # 如果解析失败，返回当前时间
        return datetime.utcnow()
    
    async def apply_filter(
        self, 
        collection_name: str, 
        conditions: List[Dict[str, Any]],
        sort_field: Optional[str] = None,
        sort_order: int = -1,
        skip: int = 0,
        limit: int = 100,
        projection: Optional[Dict[str, int]] = None
    ) -> List[Dict[str, Any]]:
        """
        应用过滤条件查询数据
        
        参数:
        - collection_name: 集合名称
        - conditions: 过滤条件列表
        - sort_field: 排序字段
        - sort_order: 排序顺序 (1为升序, -1为降序)
        - skip: 跳过记录数
        - limit: 返回记录数
        - projection: 投影配置
        
        返回:
        - 查询结果列表
        """
        await self.init_db()
        
        # 检查集合是否存在
        if collection_name not in await self.db.list_collection_names():
            return []
        
        # 获取集合对象
        collection = self.db[collection_name]
        
        # 构建查询条件
        query = self.build_filter_query(conditions)
        
        # 构建排序条件
        sort_options = None
        if sort_field:
            sort_options = [(sort_field, sort_order)]
        
        # 执行查询
        cursor = collection.find(query, projection)
        
        # 应用排序
        if sort_options:
            cursor = cursor.sort(sort_options)
        
        # 应用分页
        cursor = cursor.skip(skip).limit(limit)
        
        # 收集结果
        results = []
        async for doc in cursor:
            # 转换ObjectId为字符串
            if "_id" in doc and isinstance(doc["_id"], ObjectId):
                doc["_id"] = str(doc["_id"])
            
            results.append(doc)
        
        return results
    
    async def count_filtered(
        self, 
        collection_name: str, 
        conditions: List[Dict[str, Any]]
    ) -> int:
        """
        计算符合过滤条件的记录数量
        
        参数:
        - collection_name: 集合名称
        - conditions: 过滤条件列表
        
        返回:
        - 记录数量
        """
        await self.init_db()
        
        # 检查集合是否存在
        if collection_name not in await self.db.list_collection_names():
            return 0
        
        # 获取集合对象
        collection = self.db[collection_name]
        
        # 构建查询条件
        query = self.build_filter_query(conditions)
        
        # 执行计数
        return await collection.count_documents(query)
    
    async def save_filter(self, filter_data: Dict[str, Any]) -> str:
        """
        保存过滤器配置
        
        参数:
        - filter_data: 过滤器配置
        
        返回:
        - 过滤器ID
        """
        await self.init_db()
        
        # 设置创建时间
        if "createdAt" not in filter_data:
            filter_data["createdAt"] = datetime.utcnow()
        
        # 插入记录
        result = await self.db.saved_filters.insert_one(filter_data)
        return str(result.inserted_id)
    
    async def get_saved_filters(
        self, 
        user_id: Optional[str] = None, 
        collection: Optional[str] = None,
        global_only: bool = False
    ) -> List[Dict[str, Any]]:
        """
        获取保存的过滤器列表
        
        参数:
        - user_id: 用户ID，为None则返回所有过滤器
        - collection: 集合名称，为None则返回所有集合的过滤器
        - global_only: 是否只返回全局过滤器
        
        返回:
        - 过滤器列表
        """
        await self.init_db()
        
        # 构建查询条件
        query = {}
        
        if user_id and not global_only:
            query["$or"] = [{"createdBy": user_id}, {"global": True}]
        elif global_only:
            query["global"] = True
        
        if collection:
            query["collection"] = collection
        
        # 查询过滤器
        filters = []
        async for filter_doc in self.db.saved_filters.find(query).sort("createdAt", -1):
            # 转换ID为字符串
            filter_doc["_id"] = str(filter_doc["_id"])
            filters.append(filter_doc)
        
        return filters
    
    async def get_filter(self, filter_id: str) -> Optional[Dict[str, Any]]:
        """
        获取单个过滤器配置
        
        参数:
        - filter_id: 过滤器ID
        
        返回:
        - 过滤器配置
        """
        await self.init_db()
        
        filter_doc = await self.db.saved_filters.find_one({"_id": ObjectId(filter_id)})
        if filter_doc:
            filter_doc["_id"] = str(filter_doc["_id"])
        
        return filter_doc
    
    async def update_filter(self, filter_id: str, filter_data: Dict[str, Any]) -> bool:
        """
        更新过滤器配置
        
        参数:
        - filter_id: 过滤器ID
        - filter_data: 更新的过滤器配置
        
        返回:
        - 更新是否成功
        """
        await self.init_db()
        
        # 移除不允许更新的字段
        if "_id" in filter_data:
            del filter_data["_id"]
        
        if "createdAt" in filter_data:
            del filter_data["createdAt"]
        
        # 更新记录
        result = await self.db.saved_filters.update_one(
            {"_id": ObjectId(filter_id)},
            {"$set": filter_data}
        )
        
        return result.modified_count > 0
    
    async def delete_filter(self, filter_id: str) -> bool:
        """
        删除过滤器
        
        参数:
        - filter_id: 过滤器ID
        
        返回:
        - 删除是否成功
        """
        await self.init_db()
        
        result = await self.db.saved_filters.delete_one({"_id": ObjectId(filter_id)})
        return result.deleted_count > 0
    
    async def get_collection_schema(self, collection_name: str) -> List[Dict[str, Any]]:
        """
        获取集合字段结构
        
        参数:
        - collection_name: 集合名称
        
        返回:
        - 字段信息列表
        """
        await self.init_db()
        
        # 检查集合是否存在
        if collection_name not in await self.db.list_collection_names():
            return []
        
        # 获取集合对象
        collection = self.db[collection_name]
        
        # 分析样本数据推断字段结构
        fields = {}
        async for doc in collection.find().limit(100):
            for field_name, field_value in doc.items():
                if field_name not in fields:
                    fields[field_name] = {
                        "type": self._infer_field_type(field_value),
                        "samples": [],
                        "count": 0
                    }
                
                # 收集样本值
                if len(fields[field_name]["samples"]) < 10:
                    sample_value = str(field_value)
                    if len(sample_value) > 50:
                        sample_value = sample_value[:47] + "..."
                    
                    if sample_value not in fields[field_name]["samples"]:
                        fields[field_name]["samples"].append(sample_value)
                
                fields[field_name]["count"] += 1
        
        # 转换为列表格式
        result = []
        for field_name, info in fields.items():
            result.append({
                "name": field_name,
                "label": field_name.replace("_", " ").title(),
                "type": info["type"],
                "samples": info["samples"],
                "coverage": round(info["count"] / 100, 2) if info["count"] <= 100 else 1.0
            })
        
        # 按字段名排序
        result.sort(key=lambda x: x["name"])
        
        return result
    
    def _infer_field_type(self, value: Any) -> str:
        """
        推断字段类型
        
        参数:
        - value: 字段值
        
        返回:
        - 字段类型
        """
        if value is None:
            return "string"
        
        if isinstance(value, bool):
            return "boolean"
        
        if isinstance(value, (int, float)):
            return "number"
        
        if isinstance(value, datetime):
            return "date"
        
        if isinstance(value, (list, tuple)):
            if value:
                # 如果列表不为空，推断第一个元素的类型
                return f"array<{self._infer_field_type(value[0])}>"
            return "array<string>"
        
        if isinstance(value, dict):
            return "object"
        
        if isinstance(value, str):
            # 尝试解析日期
            try:
                if re.match(r'^\d{4}-\d{2}-\d{2}', value):
                    datetime.fromisoformat(value.replace("Z", "+00:00"))
                    return "date"
            except:
                pass
        
        return "string"


# 创建服务实例
data_filter_service = DataFilterService() 
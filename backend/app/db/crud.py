"""
通用CRUD操作辅助类
提供与MongoDB交互的基本操作
"""
from typing import List, Dict, Any, Optional, Type, TypeVar, Generic
from motor.motor_asyncio import AsyncIOMotorDatabase, AsyncIOMotorCollection
from bson import ObjectId

# 创建模型类型变量
T = TypeVar('T')

class CRUDBase(Generic[T]):
    """
    通用CRUD操作基类
    """
    
    def __init__(self, db: AsyncIOMotorDatabase, model_class: Type[T]):
        """
        初始化CRUD操作基类
        :param db: MongoDB数据库连接
        :param model_class: 模型类
        """
        self.db = db
        self.model_class = model_class
        self.collection = db[model_class.collection_name]
    
    async def create(self, obj: T) -> T:
        """
        创建对象
        :param obj: 对象实例
        :return: 创建后的对象
        """
        doc = obj.to_mongo()
        result = await self.collection.insert_one(doc)
        obj._id = str(result.inserted_id)
        return obj
    
    async def get(self, id: str) -> Optional[T]:
        """
        通过ID获取对象
        :param id: 对象ID
        :return: 对象实例，如不存在则返回None
        """
        try:
            doc = await self.collection.find_one({"_id": ObjectId(id)})
            if doc:
                return self.model_class.from_mongo(doc)
            return None
        except Exception:
            return None
    
    async def get_multi(self, skip: int = 0, limit: int = 100) -> List[T]:
        """
        获取多个对象
        :param skip: 跳过记录数
        :param limit: 限制记录数
        :return: 对象列表
        """
        cursor = self.collection.find().skip(skip).limit(limit)
        results = []
        
        async for doc in cursor:
            results.append(self.model_class.from_mongo(doc))
            
        return results
    
    async def update(self, id: str, obj: T) -> Optional[T]:
        """
        更新对象
        :param id: 对象ID
        :param obj: 更新后的对象实例
        :return: 更新后的对象，如不存在则返回None
        """
        try:
            doc = obj.to_mongo()
            doc.pop("_id", None)  # 移除_id字段，避免更新时出错
            
            result = await self.collection.update_one(
                {"_id": ObjectId(id)},
                {"$set": doc}
            )
            
            if result.modified_count:
                return await self.get(id)
            return None
        except Exception:
            return None
    
    async def delete(self, id: str) -> bool:
        """
        删除对象
        :param id: 对象ID
        :return: 是否删除成功
        """
        try:
            result = await self.collection.delete_one({"_id": ObjectId(id)})
            return result.deleted_count > 0
        except Exception:
            return False
    
    async def exists(self, id: str) -> bool:
        """
        检查对象是否存在
        :param id: 对象ID
        :return: 是否存在
        """
        try:
            count = await self.collection.count_documents({"_id": ObjectId(id)})
            return count > 0
        except Exception:
            return False
    
    async def count(self, filter: Dict[str, Any] = None) -> int:
        """
        计算满足条件的对象数量
        :param filter: 筛选条件
        :return: 对象数量
        """
        try:
            return await self.collection.count_documents(filter or {})
        except Exception:
            return 0
    
    async def find(self, filter: Dict[str, Any], skip: int = 0, limit: int = 100) -> List[T]:
        """
        查找满足条件的对象
        :param filter: 筛选条件
        :param skip: 跳过记录数
        :param limit: 限制记录数
        :return: 对象列表
        """
        cursor = self.collection.find(filter).skip(skip).limit(limit)
        results = []
        
        async for doc in cursor:
            results.append(self.model_class.from_mongo(doc))
            
        return results
    
    async def find_one(self, filter: Dict[str, Any]) -> Optional[T]:
        """
        查找满足条件的第一个对象
        :param filter: 筛选条件
        :return: 对象实例，如不存在则返回None
        """
        try:
            doc = await self.collection.find_one(filter)
            if doc:
                return self.model_class.from_mongo(doc)
            return None
        except Exception:
            return None 
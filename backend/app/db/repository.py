"""
仓库模式实现
提供数据访问抽象层，隔离数据库具体实现细节
"""
from abc import ABC, abstractmethod
from typing import Generic, TypeVar, List, Dict, Any, Optional, Type, Union, Tuple
from datetime import datetime
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase, AsyncIOMotorCollection

from app.core.exceptions import DatabaseException, ResourceNotFoundException
from app.core.logging import app_logger as logger
from app.core.utils import format_document

T = TypeVar('T')
ID = TypeVar('ID')


class Repository(Generic[T, ID], ABC):
    """
    抽象仓库接口
    定义所有仓库必须实现的方法
    """
    
    @abstractmethod
    async def create(self, entity: T) -> T:
        """创建实体"""
        pass
        
    @abstractmethod
    async def get_by_id(self, id: ID) -> Optional[T]:
        """通过ID获取实体"""
        pass
        
    @abstractmethod
    async def update(self, id: ID, entity: T) -> Optional[T]:
        """更新实体"""
        pass
        
    @abstractmethod
    async def delete(self, id: ID) -> bool:
        """删除实体"""
        pass
        
    @abstractmethod
    async def find(self, filter_params: Dict[str, Any] = None, **kwargs) -> List[T]:
        """查找符合条件的实体"""
        pass
        
    @abstractmethod
    async def find_one(self, filter_params: Dict[str, Any]) -> Optional[T]:
        """查找符合条件的第一个实体"""
        pass
        
    @abstractmethod
    async def count(self, filter_params: Dict[str, Any] = None) -> int:
        """计算符合条件的实体数量"""
        pass


class MongoRepository(Repository[T, str]):
    """
    MongoDB仓库基类实现
    使用motor异步驱动
    """
    
    def __init__(self, db: AsyncIOMotorDatabase, model_class: Type[T]):
        """
        初始化MongoDB仓库
        
        参数:
            db: MongoDB数据库连接
            model_class: 模型类
        """
        self.db = db
        self.model_class = model_class
        
        # 获取集合名称，约定模型类应有collection_name属性
        collection_name = getattr(model_class, 'collection_name', model_class.__name__.lower())
        self.collection: AsyncIOMotorCollection = db[collection_name]
        
    async def create(self, entity: T) -> T:
        """创建实体"""
        try:
            # 将实体转换为MongoDB文档
            doc = self._to_mongo(entity)
            
            # 设置创建和更新时间
            if 'created_at' not in doc:
                doc['created_at'] = datetime.utcnow()
            if 'updated_at' not in doc:
                doc['updated_at'] = datetime.utcnow()
                
            # 插入文档
            result = await self.collection.insert_one(doc)
            
            # 更新ID并返回
            entity_id = str(result.inserted_id)
            return await self.get_by_id(entity_id)
            
        except Exception as e:
            logger.error(f"创建实体错误: {type(e).__name__} - {str(e)}")
            raise DatabaseException(
                message=f"创建{self.model_class.__name__}失败",
                original_error=e
            )
            
    async def get_by_id(self, id: str) -> Optional[T]:
        """通过ID获取实体"""
        try:
            # 检查ID格式
            if not self._is_valid_id(id):
                return None
                
            # 查询文档
            doc = await self.collection.find_one({"_id": ObjectId(id)})
            if not doc:
                return None
                
            # 转换为实体对象
            return self._from_mongo(doc)
            
        except Exception as e:
            logger.error(f"通过ID获取实体错误: {type(e).__name__} - {str(e)}")
            raise DatabaseException(
                message=f"获取{self.model_class.__name__}失败",
                original_error=e
            )
            
    async def update(self, id: str, entity: T) -> Optional[T]:
        """更新实体"""
        try:
            # 检查ID格式
            if not self._is_valid_id(id):
                return None
                
            # 将实体转换为MongoDB文档
            doc = self._to_mongo(entity)
            
            # 设置更新时间
            doc['updated_at'] = datetime.utcnow()
            
            # 移除ID字段，避免更新错误
            doc.pop('_id', None)
            
            # 更新文档
            result = await self.collection.update_one(
                {"_id": ObjectId(id)},
                {"$set": doc}
            )
            
            # 如果更新成功，返回更新后的实体
            if result.modified_count > 0 or result.matched_count > 0:
                return await self.get_by_id(id)
                
            return None
            
        except Exception as e:
            logger.error(f"更新实体错误: {type(e).__name__} - {str(e)}")
            raise DatabaseException(
                message=f"更新{self.model_class.__name__}失败",
                original_error=e
            )
            
    async def delete(self, id: str) -> bool:
        """删除实体"""
        try:
            # 检查ID格式
            if not self._is_valid_id(id):
                return False
                
            # 执行删除
            result = await self.collection.delete_one({"_id": ObjectId(id)})
            return result.deleted_count > 0
            
        except Exception as e:
            logger.error(f"删除实体错误: {type(e).__name__} - {str(e)}")
            raise DatabaseException(
                message=f"删除{self.model_class.__name__}失败",
                original_error=e
            )
            
    async def find(
        self, 
        filter_params: Dict[str, Any] = None, 
        sort: Dict[str, int] = None,
        skip: int = 0, 
        limit: int = 100,
        projection: Dict[str, int] = None
    ) -> List[T]:
        """查找符合条件的实体"""
        try:
            filter_params = filter_params or {}
            # 处理查询条件中的ID
            self._process_id_in_filter(filter_params)
            
            # 构建查询
            cursor = self.collection.find(filter_params, projection)
            
            # 应用排序
            if sort:
                cursor = cursor.sort(list(sort.items()))
                
            # 应用分页
            cursor = cursor.skip(skip).limit(limit)
            
            # 执行查询并转换结果
            results = []
            async for doc in cursor:
                results.append(self._from_mongo(doc))
                
            return results
            
        except Exception as e:
            logger.error(f"查询实体错误: {type(e).__name__} - {str(e)}")
            raise DatabaseException(
                message=f"查询{self.model_class.__name__}失败",
                original_error=e
            )
            
    async def find_one(self, filter_params: Dict[str, Any]) -> Optional[T]:
        """查找符合条件的第一个实体"""
        try:
            # 处理查询条件中的ID
            self._process_id_in_filter(filter_params)
            
            # 执行查询
            doc = await self.collection.find_one(filter_params)
            if not doc:
                return None
                
            # 转换为实体对象
            return self._from_mongo(doc)
            
        except Exception as e:
            logger.error(f"查找单个实体错误: {type(e).__name__} - {str(e)}")
            raise DatabaseException(
                message=f"查询{self.model_class.__name__}失败",
                original_error=e
            )
            
    async def count(self, filter_params: Dict[str, Any] = None) -> int:
        """计算符合条件的实体数量"""
        try:
            filter_params = filter_params or {}
            # 处理查询条件中的ID
            self._process_id_in_filter(filter_params)
            
            # 执行计数
            return await self.collection.count_documents(filter_params)
            
        except Exception as e:
            logger.error(f"计数实体错误: {type(e).__name__} - {str(e)}")
            raise DatabaseException(
                message=f"计数{self.model_class.__name__}失败",
                original_error=e
            )
    
    async def exists(self, id: str) -> bool:
        """检查实体是否存在"""
        try:
            # 检查ID格式
            if not self._is_valid_id(id):
                return False
                
            # 执行计数
            count = await self.collection.count_documents({"_id": ObjectId(id)})
            return count > 0
            
        except Exception as e:
            logger.error(f"检查实体存在错误: {type(e).__name__} - {str(e)}")
            raise DatabaseException(
                message=f"检查{self.model_class.__name__}存在失败",
                original_error=e
            )
    
    async def find_by_field(
        self, 
        field: str, 
        value: Any, 
        skip: int = 0, 
        limit: int = 100,
        sort: Dict[str, int] = None
    ) -> List[T]:
        """通过字段值查找实体"""
        return await self.find(
            filter_params={field: value},
            skip=skip,
            limit=limit,
            sort=sort
        )
    
    async def find_by_fields(
        self,
        fields: Dict[str, Any],
        skip: int = 0,
        limit: int = 100,
        sort: Dict[str, int] = None
    ) -> List[T]:
        """通过多个字段值查找实体"""
        return await self.find(
            filter_params=fields,
            skip=skip,
            limit=limit,
            sort=sort
        )
    
    async def update_fields(self, id: str, fields: Dict[str, Any]) -> Optional[T]:
        """更新实体的特定字段"""
        try:
            # 检查ID格式
            if not self._is_valid_id(id):
                return None
                
            # 设置更新时间
            update_fields = fields.copy()
            update_fields['updated_at'] = datetime.utcnow()
            
            # 执行更新
            result = await self.collection.update_one(
                {"_id": ObjectId(id)},
                {"$set": update_fields}
            )
            
            # 如果更新成功，返回更新后的实体
            if result.modified_count > 0 or result.matched_count > 0:
                return await self.get_by_id(id)
                
            return None
            
        except Exception as e:
            logger.error(f"更新字段错误: {type(e).__name__} - {str(e)}")
            raise DatabaseException(
                message=f"更新{self.model_class.__name__}字段失败",
                original_error=e
            )
    
    async def add_to_array(self, id: str, field: str, value: Any) -> bool:
        """向数组字段添加值"""
        try:
            # 检查ID格式
            if not self._is_valid_id(id):
                return False
                
            # 执行更新
            result = await self.collection.update_one(
                {"_id": ObjectId(id)},
                {
                    "$addToSet": {field: value},
                    "$set": {"updated_at": datetime.utcnow()}
                }
            )
            
            return result.modified_count > 0
            
        except Exception as e:
            logger.error(f"添加到数组错误: {type(e).__name__} - {str(e)}")
            raise DatabaseException(
                message=f"向{self.model_class.__name__}添加数组元素失败",
                original_error=e
            )
    
    async def remove_from_array(self, id: str, field: str, value: Any) -> bool:
        """从数组字段删除值"""
        try:
            # 检查ID格式
            if not self._is_valid_id(id):
                return False
                
            # 执行更新
            result = await self.collection.update_one(
                {"_id": ObjectId(id)},
                {
                    "$pull": {field: value},
                    "$set": {"updated_at": datetime.utcnow()}
                }
            )
            
            return result.modified_count > 0
            
        except Exception as e:
            logger.error(f"从数组删除错误: {type(e).__name__} - {str(e)}")
            raise DatabaseException(
                message=f"从{self.model_class.__name__}删除数组元素失败",
                original_error=e
            )
    
    async def find_with_pagination(
        self,
        filter_params: Dict[str, Any] = None,
        sort: Dict[str, int] = None,
        page: int = 1,
        page_size: int = 50
    ) -> Tuple[List[T], int, int]:
        """分页查询实体"""
        # 计算总数
        total = await self.count(filter_params)
        
        # 计算总页数
        total_pages = (total + page_size - 1) // page_size if total > 0 else 1
        
        # 计算跳过的记录数
        skip = (page - 1) * page_size
        
        # 查询数据
        items = await self.find(
            filter_params=filter_params,
            sort=sort,
            skip=skip,
            limit=page_size
        )
        
        return items, total, total_pages
    
    async def soft_delete(self, id: str) -> bool:
        """软删除实体"""
        try:
            # 检查ID格式
            if not self._is_valid_id(id):
                return False
                
            # 执行更新
            result = await self.collection.update_one(
                {"_id": ObjectId(id)},
                {
                    "$set": {
                        "deleted": True,
                        "deleted_at": datetime.utcnow(),
                        "updated_at": datetime.utcnow()
                    }
                }
            )
            
            return result.modified_count > 0
            
        except Exception as e:
            logger.error(f"软删除错误: {type(e).__name__} - {str(e)}")
            raise DatabaseException(
                message=f"软删除{self.model_class.__name__}失败",
                original_error=e
            )
    
    async def restore(self, id: str) -> bool:
        """恢复软删除的实体"""
        try:
            # 检查ID格式
            if not self._is_valid_id(id):
                return False
                
            # 执行更新
            result = await self.collection.update_one(
                {"_id": ObjectId(id)},
                {
                    "$set": {
                        "deleted": False,
                        "updated_at": datetime.utcnow()
                    },
                    "$unset": {
                        "deleted_at": ""
                    }
                }
            )
            
            return result.modified_count > 0
            
        except Exception as e:
            logger.error(f"恢复删除错误: {type(e).__name__} - {str(e)}")
            raise DatabaseException(
                message=f"恢复{self.model_class.__name__}失败",
                original_error=e
            )
    
    def _is_valid_id(self, id: str) -> bool:
        """检查ID是否有效"""
        try:
            ObjectId(id)
            return True
        except:
            return False
    
    def _process_id_in_filter(self, filter_params: Dict[str, Any]) -> None:
        """处理查询条件中的ID字段"""
        if not filter_params:
            return
            
        # 处理_id字段
        if '_id' in filter_params:
            id_value = filter_params['_id']
            
            if isinstance(id_value, str) and self._is_valid_id(id_value):
                filter_params['_id'] = ObjectId(id_value)
                
            elif isinstance(id_value, dict):
                # 处理复杂查询条件，如 {'_id': {'$in': [id1, id2]}}
                for op, value in id_value.items():
                    if op == '$in' and isinstance(value, list):
                        filter_params['_id'][op] = [
                            ObjectId(item) if isinstance(item, str) and self._is_valid_id(item) else item
                            for item in value
                        ]
    
    def _to_mongo(self, entity: T) -> Dict[str, Any]:
        """将实体转换为MongoDB文档"""
        if hasattr(entity, 'to_mongo') and callable(getattr(entity, 'to_mongo')):
            return entity.to_mongo()
        elif hasattr(entity, 'model_dump') and callable(getattr(entity, 'model_dump')):
            # 处理Pydantic模型
            return entity.model_dump(exclude_unset=True)
        elif hasattr(entity, 'dict') and callable(getattr(entity, 'dict')):
            # 处理旧版Pydantic模型
            return entity.dict(exclude_unset=True)
        elif isinstance(entity, dict):
            return entity
        else:
            # 默认情况：尝试将对象转换为字典
            return dict(entity.__dict__)
    
    def _from_mongo(self, doc: Dict[str, Any]) -> T:
        """将MongoDB文档转换为实体"""
        if hasattr(self.model_class, 'from_mongo') and callable(getattr(self.model_class, 'from_mongo')):
            return self.model_class.from_mongo(doc)
        elif hasattr(self.model_class, 'model_validate') and callable(getattr(self.model_class, 'model_validate')):
            # 处理Pydantic模型
            # 转换_id为id
            if '_id' in doc and isinstance(doc['_id'], ObjectId):
                doc['id'] = str(doc.pop('_id'))
            return self.model_class.model_validate(doc)
        else:
            # 尝试直接实例化
            if '_id' in doc and isinstance(doc['_id'], ObjectId):
                doc['_id'] = str(doc['_id'])
            return self.model_class(**doc)
    
    def to_api_response(self, entity: Optional[T]) -> Optional[Dict[str, Any]]:
        """将实体转换为API响应格式"""
        if not entity:
            return None
            
        if hasattr(entity, 'to_dict') and callable(getattr(entity, 'to_dict')):
            return entity.to_dict()
        elif hasattr(entity, 'model_dump') and callable(getattr(entity, 'model_dump')):
            return entity.model_dump()
        elif hasattr(entity, 'dict') and callable(getattr(entity, 'dict')):
            return entity.dict()
        elif isinstance(entity, dict):
            return format_document(entity)
        else:
            # 将对象__dict__转换为字典，并格式化
            return format_document(entity.__dict__) 
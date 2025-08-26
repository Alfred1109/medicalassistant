"""
服务层基类
提供服务层通用功能的实现
"""
from typing import Generic, TypeVar, Dict, List, Any, Optional, Type, Tuple
from datetime import datetime

from app.db.repository import Repository
from app.core.exceptions import (
    ResourceNotFoundException, ValidationException, 
    BusinessLogicException, DatabaseException
)
from app.core.logging import app_logger as logger
from app.schemas.common import PaginatedResponse, PaginationParams

T = TypeVar('T')  # 实体类型
R = TypeVar('R')  # 仓库类型
C = TypeVar('C')  # 创建请求类型 
U = TypeVar('U')  # 更新请求类型
O = TypeVar('O')  # 响应类型

class BaseService(Generic[T, R, C, U, O]):
    """
    服务层基类
    提供通用CRUD操作和业务逻辑封装
    """
    
    def __init__(self, repository: Repository):
        """
        初始化服务
        
        参数:
            repository: 实体仓库
        """
        self.repository = repository
    
    async def create(self, data: C) -> O:
        """
        创建实体
        
        参数:
            data: 创建请求数据
            
        返回:
            创建的实体响应
        """
        try:
            # 数据验证
            await self._validate_create(data)
            
            # 将请求数据转换为实体
            entity = self._create_entity_from_request(data)
            
            # 保存实体
            created_entity = await self.repository.create(entity)
            
            # 返回响应
            return self._to_response(created_entity)
        except Exception as e:
            logger.error(f"创建实体错误: {type(e).__name__} - {str(e)}")
            # 重新抛出已知异常，包装未知异常
            if isinstance(e, (ResourceNotFoundException, ValidationException, BusinessLogicException)):
                raise
            raise DatabaseException(message="创建失败", original_error=e)
    
    async def get_by_id(self, id: str) -> O:
        """
        通过ID获取实体
        
        参数:
            id: 实体ID
            
        返回:
            实体响应
            
        异常:
            ResourceNotFoundException: 实体不存在
        """
        try:
            entity = await self.repository.get_by_id(id)
            if not entity:
                raise ResourceNotFoundException(
                    resource_type=self._get_resource_type(),
                    resource_id=id
                )
            return self._to_response(entity)
        except ResourceNotFoundException:
            raise
        except Exception as e:
            logger.error(f"获取实体错误: {type(e).__name__} - {str(e)}")
            raise DatabaseException(message="获取失败", original_error=e)
    
    async def update(self, id: str, data: U) -> O:
        """
        更新实体
        
        参数:
            id: 实体ID
            data: 更新请求数据
            
        返回:
            更新后的实体响应
            
        异常:
            ResourceNotFoundException: 实体不存在
            ValidationException: 数据验证错误
        """
        try:
            # 检查实体是否存在
            entity = await self.repository.get_by_id(id)
            if not entity:
                raise ResourceNotFoundException(
                    resource_type=self._get_resource_type(),
                    resource_id=id
                )
            
            # 数据验证
            await self._validate_update(id, data, entity)
            
            # 将请求数据应用到实体
            updated_entity = self._update_entity_from_request(entity, data)
            
            # 保存实体
            result = await self.repository.update(id, updated_entity)
            if not result:
                raise DatabaseException(message="更新失败")
                
            # 返回响应
            return self._to_response(result)
        except (ResourceNotFoundException, ValidationException):
            raise
        except Exception as e:
            logger.error(f"更新实体错误: {type(e).__name__} - {str(e)}")
            if isinstance(e, (ResourceNotFoundException, ValidationException, BusinessLogicException)):
                raise
            raise DatabaseException(message="更新失败", original_error=e)
    
    async def delete(self, id: str) -> bool:
        """
        删除实体
        
        参数:
            id: 实体ID
            
        返回:
            是否删除成功
            
        异常:
            ResourceNotFoundException: 实体不存在
        """
        try:
            # 检查实体是否存在
            entity = await self.repository.get_by_id(id)
            if not entity:
                raise ResourceNotFoundException(
                    resource_type=self._get_resource_type(),
                    resource_id=id
                )
            
            # 检查是否可以删除
            await self._validate_delete(id, entity)
            
            # 删除实体
            return await self.repository.delete(id)
        except ResourceNotFoundException:
            raise
        except Exception as e:
            logger.error(f"删除实体错误: {type(e).__name__} - {str(e)}")
            if isinstance(e, (ResourceNotFoundException, ValidationException, BusinessLogicException)):
                raise
            raise DatabaseException(message="删除失败", original_error=e)
    
    async def soft_delete(self, id: str) -> bool:
        """
        软删除实体
        
        参数:
            id: 实体ID
            
        返回:
            是否软删除成功
            
        异常:
            ResourceNotFoundException: 实体不存在
        """
        try:
            # 检查实体是否存在
            entity = await self.repository.get_by_id(id)
            if not entity:
                raise ResourceNotFoundException(
                    resource_type=self._get_resource_type(),
                    resource_id=id
                )
            
            # 检查是否可以删除
            await self._validate_delete(id, entity)
            
            # 软删除实体
            return await self.repository.soft_delete(id)
        except ResourceNotFoundException:
            raise
        except Exception as e:
            logger.error(f"软删除实体错误: {type(e).__name__} - {str(e)}")
            if isinstance(e, (ResourceNotFoundException, ValidationException, BusinessLogicException)):
                raise
            raise DatabaseException(message="软删除失败", original_error=e)
    
    async def find(
        self,
        filter_params: Dict[str, Any] = None,
        sort: Dict[str, int] = None,
        pagination: PaginationParams = None
    ) -> PaginatedResponse[O]:
        """
        查找实体
        
        参数:
            filter_params: 过滤参数
            sort: 排序参数 {字段名: 排序方向(1升序,-1降序)}
            pagination: 分页参数
            
        返回:
            分页响应
        """
        try:
            # 处理分页
            pagination = pagination or PaginationParams()
            skip = pagination.get_skip()
            limit = pagination.get_limit()
            
            # 查询数据
            items, total, _ = await self.repository.find_with_pagination(
                filter_params=filter_params,
                sort=sort,
                page=pagination.page,
                page_size=pagination.page_size
            )
            
            # 转换为响应
            return PaginatedResponse.create(
                items=[self._to_response(item) for item in items],
                total=total,
                params=pagination
            )
        except Exception as e:
            logger.error(f"查询实体错误: {type(e).__name__} - {str(e)}")
            raise DatabaseException(message="查询失败", original_error=e)
    
    async def find_all(
        self,
        filter_params: Dict[str, Any] = None,
        sort: Dict[str, int] = None,
        skip: int = 0,
        limit: int = 100
    ) -> List[O]:
        """
        查找所有符合条件的实体
        
        参数:
            filter_params: 过滤参数
            sort: 排序参数
            skip: 跳过记录数
            limit: 限制记录数
            
        返回:
            实体响应列表
        """
        try:
            entities = await self.repository.find(
                filter_params=filter_params,
                sort=sort,
                skip=skip,
                limit=limit
            )
            return [self._to_response(entity) for entity in entities]
        except Exception as e:
            logger.error(f"查询所有实体错误: {type(e).__name__} - {str(e)}")
            raise DatabaseException(message="查询失败", original_error=e)
    
    async def exists(self, id: str) -> bool:
        """
        检查实体是否存在
        
        参数:
            id: 实体ID
            
        返回:
            是否存在
        """
        try:
            return await self.repository.exists(id)
        except Exception as e:
            logger.error(f"检查实体存在错误: {type(e).__name__} - {str(e)}")
            raise DatabaseException(message="检查失败", original_error=e)
    
    async def count(self, filter_params: Dict[str, Any] = None) -> int:
        """
        计算实体数量
        
        参数:
            filter_params: 过滤参数
            
        返回:
            实体数量
        """
        try:
            return await self.repository.count(filter_params)
        except Exception as e:
            logger.error(f"计数实体错误: {type(e).__name__} - {str(e)}")
            raise DatabaseException(message="计数失败", original_error=e)
    
    async def find_by_field(
        self,
        field: str,
        value: Any,
        skip: int = 0,
        limit: int = 100,
        sort: Dict[str, int] = None
    ) -> List[O]:
        """
        通过字段值查找实体
        
        参数:
            field: 字段名
            value: 字段值
            skip: 跳过记录数
            limit: 限制记录数
            sort: 排序参数
            
        返回:
            实体响应列表
        """
        try:
            entities = await self.repository.find_by_field(
                field=field,
                value=value,
                skip=skip,
                limit=limit,
                sort=sort
            )
            return [self._to_response(entity) for entity in entities]
        except Exception as e:
            logger.error(f"通过字段查询实体错误: {type(e).__name__} - {str(e)}")
            raise DatabaseException(message="查询失败", original_error=e)
    
    async def update_fields(self, id: str, fields: Dict[str, Any]) -> O:
        """
        更新实体字段
        
        参数:
            id: 实体ID
            fields: 要更新的字段
            
        返回:
            更新后的实体响应
            
        异常:
            ResourceNotFoundException: 实体不存在
        """
        try:
            # 检查实体是否存在
            entity = await self.repository.get_by_id(id)
            if not entity:
                raise ResourceNotFoundException(
                    resource_type=self._get_resource_type(),
                    resource_id=id
                )
            
            # 更新字段
            result = await self.repository.update_fields(id, fields)
            if not result:
                raise DatabaseException(message="更新字段失败")
                
            # 返回响应
            return self._to_response(result)
        except ResourceNotFoundException:
            raise
        except Exception as e:
            logger.error(f"更新字段错误: {type(e).__name__} - {str(e)}")
            if isinstance(e, (ResourceNotFoundException, ValidationException, BusinessLogicException)):
                raise
            raise DatabaseException(message="更新字段失败", original_error=e)
    
    # 以下是子类可以重写的钩子方法
    
    async def _validate_create(self, data: C) -> None:
        """
        验证创建请求数据
        
        参数:
            data: 创建请求数据
            
        异常:
            ValidationException: 数据验证错误
        """
        # 默认不做额外验证，子类可以重写
        pass
    
    async def _validate_update(self, id: str, data: U, entity: T) -> None:
        """
        验证更新请求数据
        
        参数:
            id: 实体ID
            data: 更新请求数据
            entity: 当前实体
            
        异常:
            ValidationException: 数据验证错误
        """
        # 默认不做额外验证，子类可以重写
        pass
    
    async def _validate_delete(self, id: str, entity: T) -> None:
        """
        验证删除操作
        
        参数:
            id: 实体ID
            entity: 当前实体
            
        异常:
            ValidationException: 验证错误
            BusinessLogicException: 业务逻辑错误
        """
        # 默认不做额外验证，子类可以重写
        pass
    
    def _create_entity_from_request(self, data: C) -> T:
        """
        从创建请求创建实体
        
        参数:
            data: 创建请求数据
            
        返回:
            创建的实体
        """
        # 默认直接使用请求数据，子类可以重写
        if hasattr(data, 'model_dump') and callable(getattr(data, 'model_dump')):
            return data.model_dump()
        elif hasattr(data, 'dict') and callable(getattr(data, 'dict')):
            return data.dict()
        return data
    
    def _update_entity_from_request(self, entity: T, data: U) -> T:
        """
        从更新请求更新实体
        
        参数:
            entity: 当前实体
            data: 更新请求数据
            
        返回:
            更新后的实体
        """
        # 默认直接使用请求数据更新实体，子类可以重写
        if hasattr(data, 'model_dump') and callable(getattr(data, 'model_dump')):
            update_data = data.model_dump(exclude_unset=True)
        elif hasattr(data, 'dict') and callable(getattr(data, 'dict')):
            update_data = data.dict(exclude_unset=True)
        else:
            update_data = data
            
        if isinstance(entity, dict):
            # 如果实体是字典，直接更新
            entity.update(update_data)
        else:
            # 如果实体是对象，更新属性
            for key, value in update_data.items():
                if hasattr(entity, key):
                    setattr(entity, key, value)
        
        return entity
    
    def _to_response(self, entity: T) -> O:
        """
        将实体转换为响应
        
        参数:
            entity: 实体
            
        返回:
            响应对象
        """
        # 默认直接返回实体，子类可以重写
        return entity
    
    def _get_resource_type(self) -> str:
        """
        获取资源类型名称
        
        返回:
            资源类型名
        """
        # 默认使用仓库的模型类名
        return getattr(self.repository, 'model_class', object).__name__ 
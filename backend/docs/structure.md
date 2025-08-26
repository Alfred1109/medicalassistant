# 项目架构说明

## 当前架构概述

本项目采用分层架构设计，主要分为以下几层：

### 1. API层 (`app/api/`)
- 负责处理HTTP请求和响应
- 定义API路由和端点
- 处理请求参数验证
- 调用服务层执行业务逻辑

### 2. 服务层 (`app/services/`)
- 实现核心业务逻辑
- 协调数据访问和业务规则
- 处理服务间协作
- 封装与外部系统的交互

### 3. 数据访问层 (`app/db/`)
- 提供数据库交互抽象
- 实现通用CRUD操作
- 处理数据转换和格式化
- 管理数据库连接和事务

### 4. 模型层 (`app/models/`)
- 定义数据模型和实体关系
- 提供数据验证和业务规则
- 实现与数据库的映射
- 封装实体行为和状态

### 5. 模式层 (`app/schemas/`)
- 定义API请求和响应模式
- 提供数据验证和转换
- 实现API文档生成支持
- 处理模型与API之间的映射

### 6. 核心层 (`app/core/`)
- 提供通用功能和工具
- 定义配置和常量
- 实现中间件和扩展
- 处理认证和授权

## 当前架构问题

在审查现有架构后，发现以下结构性问题：

### 1. 层间责任边界模糊
- 数据格式化逻辑在路由层和服务层都有出现
- 数据验证职责在多层中重复
- 业务逻辑在路由处理函数中泄漏

### 2. 模块间高耦合
- 服务层直接依赖模型层的特定实现
- 路由层与多个服务层组件强耦合
- 数据访问层与模型层实现细节紧密绑定

### 3. 横切关注点分散
- 异常处理策略不一致
- 日志记录分散在各个组件中
- 缓存策略缺乏统一实现

### 4. 扩展性局限
- 数据库访问层与MongoDB强绑定
- 服务组件难以替换或模拟
- 新功能添加需要修改多个组件

## 改进架构建议

为解决上述问题，建议采取以下架构改进措施：

### 1. 实现清晰的层间接口

#### 数据访问层改进
- 创建抽象数据仓库接口，隔离MongoDB具体实现
- 实现通用查询构建器，统一查询逻辑
- 提供标准化的实体映射机制

```python
# 示例：抽象数据仓库接口
from abc import ABC, abstractmethod
from typing import Generic, TypeVar, List, Optional, Dict, Any

T = TypeVar('T')

class Repository(Generic[T], ABC):
    @abstractmethod
    async def create(self, entity: T) -> T:
        pass
        
    @abstractmethod
    async def get(self, id: str) -> Optional[T]:
        pass
    
    @abstractmethod
    async def find(self, filter_params: Dict[str, Any], sort: Dict[str, int] = None, 
                  skip: int = 0, limit: int = 100) -> List[T]:
        pass
    
    # 其他抽象方法...
```

#### 服务层改进
- 引入服务接口定义，实现依赖倒置
- 创建通用服务基类，提供标准CRUD功能
- 将服务组件设计为可独立测试单元

```python
# 示例：服务层接口与实现
from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any, Generic, TypeVar

T = TypeVar('T')
ID = TypeVar('ID')

class Service(Generic[T, ID], ABC):
    @abstractmethod
    async def create(self, data: Dict[str, Any]) -> T:
        pass
    
    @abstractmethod
    async def get_by_id(self, id: ID) -> Optional[T]:
        pass
    
    # 其他抽象方法...

class BaseService(Service[T, ID]):
    """通用服务基类实现"""
    def __init__(self, repository):
        self.repository = repository
        
    async def create(self, data: Dict[str, Any]) -> T:
        # 通用实现
        pass
```

### 2. 重构依赖管理

- 实现依赖注入容器，统一管理组件依赖
- 利用工厂模式创建服务和仓库实例
- 通过依赖配置实现组件动态替换

```python
# 示例：依赖注入容器
class DependencyContainer:
    def __init__(self):
        self._services = {}
        self._repositories = {}
        self._factories = {}
    
    def register_service(self, service_name, service_factory):
        self._services[service_name] = service_factory
        
    def get_service(self, service_name):
        if service_name not in self._services:
            raise ValueError(f"Service {service_name} not registered")
        return self._services[service_name]()
```

### 3. 统一横切关注点

- 创建异常处理中心，统一异常转换和处理
- 实现集中式日志管理，提供上下文日志记录
- 开发统一的缓存抽象层，支持多种缓存策略

```python
# 示例：统一异常处理器
class ExceptionHandler:
    def __init__(self, logger):
        self.logger = logger
        
    def handle(self, exception, context=None):
        """处理异常并转换为适当的API响应"""
        if isinstance(exception, ResourceNotFoundException):
            self.logger.warning(f"Resource not found: {exception.message}")
            return self._create_error_response(404, exception)
        # 处理其他类型的异常...
```

### 4. 引入领域驱动设计元素

- 定义清晰的领域边界和上下文
- 引入聚合根和值对象概念，增强模型表达能力
- 实现领域事件机制，支持服务间松耦合通信

```python
# 示例：聚合根实现
class Patient:
    """患者聚合根"""
    def __init__(self, id, name, medical_profile, practitioners=None):
        self.id = id
        self.name = name
        self.medical_profile = medical_profile
        self.practitioners = practitioners or []
        self._events = []
        
    def assign_practitioner(self, practitioner_id):
        if practitioner_id not in self.practitioners:
            self.practitioners.append(practitioner_id)
            self._events.append(PractitionerAssignedEvent(self.id, practitioner_id))
            
    def get_domain_events(self):
        return self._events
```

## 改进实施路线图

### 第一阶段：基础结构优化
1. 重构数据访问层，引入仓库模式
2. 统一异常处理机制
3. 实现服务层抽象接口

### 第二阶段：依赖管理重构
1. 实现简单的依赖注入容器
2. 重构服务组件，支持依赖注入
3. 优化路由层与服务层的集成

### 第三阶段：领域模型增强
1. 定义核心领域模型和聚合
2. 实现基本的领域事件机制
3. 重构现有服务以支持领域模型

### 第四阶段：横切关注点优化
1. 实现统一的缓存抽象层
2. 增强日志记录和监控能力
3. 引入分布式追踪支持

## 系统组件图

```
+----------------------+
|     API层 (路由)      |
+----------+-----------+
           |
           v
+----------+-----------+
|     服务层 (业务逻辑)   |
+----------+-----------+
           |
           v
+----------+-----------+
|   仓库层 (数据访问)     |
+----------+-----------+
           |
           v
+----------+-----------+
|   数据库 (MongoDB)    |
+----------------------+
```

## 核心领域模型

项目的核心领域模型包括：

1. **用户域**
   - 患者
   - 医生
   - 健康管理师
   - 系统管理员

2. **健康记录域**
   - 健康档案
   - 随访记录
   - 健康数据

3. **康复域**
   - 康复计划
   - 锻炼活动
   - 进度记录

4. **设备域**
   - 设备信息
   - 设备数据
   - 数据分析

5. **通信域**
   - 消息
   - 会话
   - 通知

## 技术实现注意事项

1. **异步IO最佳实践**
   - 确保所有数据库操作都是异步的
   - 避免在异步代码中使用阻塞调用
   - 适当使用任务池管理长时间运行的操作

2. **MongoDB使用优化**
   - 建立适当的索引
   - 使用投影查询减少数据传输
   - 利用聚合管道优化复杂查询
   - 实现数据分页和游标管理

3. **API设计原则**
   - 遵循RESTful设计原则
   - 实现统一的错误处理
   - 支持合适的内容协商
   - 提供完整的API文档

4. **安全考虑**
   - 实现细粒度的访问控制
   - 安全存储和验证凭据
   - 防止常见的Web安全漏洞
   - 审计关键操作 
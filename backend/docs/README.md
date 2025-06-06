# 项目概述

## 项目介绍

Medical Rehabilitation Assistant是一个医疗康复辅助系统，旨在帮助医生、健康管理师和患者进行康复过程管理。系统支持用户管理、康复计划制定、健康记录追踪、设备数据分析和智能代理辅助等功能。

## 项目架构

本项目采用分层架构设计：

- **API层**：处理HTTP请求和响应
- **服务层**：实现业务逻辑
- **数据访问层**：与数据库交互
- **模型层**：定义数据结构

## 重构工作总结

项目重构主要关注以下几个方面：

### 1. 统一异常处理

- 创建了统一的异常类体系（`app/core/exceptions.py`）
- 定义了多种业务异常类型
- 在FastAPI应用中注册了全局异常处理器

### 2. 通用工具函数

- 创建了工具函数模块（`app/core/utils.py`）
- 提供文档转换、对象处理等通用函数
- 统一了命名风格转换（蛇形/驼峰）

### 3. 缓存机制

- 实现了内存缓存系统（`app/core/cache.py`）
- 提供缓存装饰器，支持同步和异步函数
- 支持缓存失效和模式匹配删除

### 4. 统一响应格式

- 创建了标准响应模型（`app/schemas/common.py`）
- 支持成功和错误响应的统一格式
- 实现了分页响应模型

### 5. 配置管理

- 增强了配置系统（`app/core/config.py`）
- 添加环境变量支持
- 提供辅助函数判断环境类型

### 6. 日志系统

- 优化了日志配置（`app/core/logging.py`）
- 支持不同日志级别和格式
- 实现了轮转日志文件

### 7. 数据库连接

- 增强了数据库连接管理（`app/db/mongodb.py`）
- 添加连接池配置
- 提供连接健康检查

### 8. CRUD服务优化

- 重构了CRUD服务类（`app/db/crud_services.py`）
- 优化了继承结构，减少代码冗余
- 统一了异常处理

## 文档完善

作为重构的一部分，我们添加了以下文档：

1. **项目架构说明**（`docs/structure.md`）：详细描述了项目的架构与组织
2. **开发计划**（`docs/develop.md`）：制定了项目的开发路线图和技术债务管理计划
3. **项目概述**（`docs/README.md`）：总结了项目重构工作

## 下一步工作

1. **测试覆盖率提升**：编写单元测试和集成测试
2. **API文档生成**：使用OpenAPI规范生成API文档
3. **性能优化**：数据库查询优化、批量操作优化
4. **安全增强**：添加更多安全检查和防护措施

## 技术栈

- **后端框架**：FastAPI
- **数据库**：MongoDB
- **认证**：JWT
- **缓存**：内存缓存
- **日志**：Loguru 
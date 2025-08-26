# 医疗助手系统 (Medical Assistant)

一个综合性的医疗健康管理平台，旨在连接医生和患者，提供健康记录管理、康复跟踪和医患沟通服务。

## 项目结构

项目采用前后端分离架构：

- **前端**：React + TypeScript + Material UI
- **后端**：Python FastAPI + MongoDB

### 目录结构

```
├── backend/             # 后端服务
│   ├── app/             # 应用核心代码
│   ├── docs/            # 项目文档
│   └── tests/           # 测试用例
│
├── frontend/            # 前端应用
│   ├── public/          # 静态资源
│   └── src/             # 源代码
│       ├── components/  # UI组件
│       ├── pages/       # 页面组件
│       ├── services/    # API服务
│       └── store/       # 状态管理
│
└── docs/                # 项目整体文档
    ├── structure.md     # 架构说明文档
    ├── develop.md       # 开发计划文档
    └── milestone.md     # 里程碑文档
```

## 核心功能

- 医生患者管理
- 健康记录追踪
- 数据可视化仪表盘
- 康复进度管理
- 医患即时沟通
- 任务提醒与通知

## 开发与部署

请查看 `docs/develop.md` 文件获取详细的开发指南和部署说明。 
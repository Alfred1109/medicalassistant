# Medical Rehabilitation Assistant Backend

A FastAPI backend for a dynamic agent-powered medical rehabilitation assistant system.

## Features

- User management (patients, practitioners, admins)
- Dynamic agent system for personalized rehabilitation assistance
- Rehabilitation plan and exercise management
- Authentication with JWT

## Architecture

This backend follows the MCP (Model-Controller-Presenter) pattern:
- **Models**: Data schemas for users, agents, rehab plans, and exercises
- **Controllers**: API endpoints defined in router files
- **Presenters**: Service layer that processes business logic

## Setup

1. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows, use: venv\Scripts\activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Configure environment variables in a `.env` file:
```
MONGODB_URL=mongodb://localhost:27017
DATABASE_NAME=rehab_assistant
SECRET_KEY=your_secret_key
OPENAI_API_KEY=your_openai_api_key
ANTHROPIC_API_KEY=your_anthropic_api_key
```

4. Run the server:
```bash
uvicorn app.main:app --reload
```

## API Documentation

Once running, access the auto-generated API documentation at:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Dynamic Agent System

The system features a flexible agent architecture that allows:

1. Creating custom agents with specific capabilities
2. Adding tools and actions to agents dynamically
3. Processing queries through agents for personalized rehabilitation assistance
4. Integrating with various LLM providers (OpenAI, Anthropic)

### Agent Configuration Example

```json
{
  "name": "Rehabilitation Assistant",
  "description": "An agent specialized in rehabilitation exercises and plans",
  "model": "gpt-4-turbo",
  "system_prompt": "You are a medical rehabilitation assistant. Help patients with their rehabilitation journey by providing exercise recommendations, answering questions about their rehabilitation plan, and offering encouragement. Always prioritize patient safety and refer to healthcare professionals for medical advice.",
  "tools": [
    {
      "name": "search_exercises",
      "description": "Search for exercises based on body part and condition",
      "parameters": {
        "body_part": {"type": "string", "description": "The body part to target"},
        "condition": {"type": "string", "description": "The medical condition"}
      },
      "required_parameters": ["body_part"]
    }
  ]
}
```

### Agent Query Example

```json
{
  "query": "What exercises would you recommend for knee rehabilitation?",
  "parameters": {
    "patient_id": "patient_123",
    "condition": "knee",
    "goal": "mobility"
  }
}
```

## Key Backend Components

### Authentication

JWT-based authentication with:
- Token generation and validation
- Password hashing with bcrypt
- Role-based access control

### Database Integration

MongoDB integration using Motor for async operations:
- Document-based data model
- Non-blocking I/O
- Scalable data storage

### API Endpoints

The API is organized into domain-specific routers:
- `/api/users/` - User management
- `/api/rehabilitation/` - Rehab plans and exercises
- `/api/agent/` - Agent management and queries

## Development

### Project Structure

```
app/
├── api/            # API endpoints (routers)
├── core/           # Core functionality, config, dependencies
├── db/             # Database connections and utils
├── models/         # Database models
├── schemas/        # Pydantic schemas for requests/responses
├── services/       # Business logic layer
└── utils/          # Utility functions
```

### Adding New Features

1. Define schemas in the appropriate schema file
2. Add service methods in the relevant service class
3. Create API endpoints in the corresponding router
4. Update dependencies if necessary

### Testing

Run tests with:
```bash
pytest
```

## Deployment

For production deployment:

1. Set up a proper MongoDB instance (Atlas or self-hosted)
2. Use a production ASGI server like Uvicorn with Gunicorn
3. Set environment variables for production settings
4. Deploy behind a reverse proxy like Nginx

Example production deployment command:
```bash
gunicorn app.main:app --workers 4 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

## 模拟数据生成

项目中的模拟数据生成脚本已整理至 `mock_data_scripts` 目录。这些脚本用于开发和测试阶段初始化数据库，生成各类模拟数据。

### 使用方法

我们提供了一个便捷的脚本 `run_mock_data.py` 来运行这些模拟数据生成脚本：

```bash
# 进入backend目录
cd backend

# 查看可用的数据生成选项
python mock_data_scripts/run_mock_data.py --list

# 生成所有模拟数据
python mock_data_scripts/run_mock_data.py all

# 或者直接执行脚本（默认生成所有数据）
python mock_data_scripts/run_mock_data.py

# 生成特定类型的模拟数据
python mock_data_scripts/run_mock_data.py users
python mock_data_scripts/run_mock_data.py doctors
python mock_data_scripts/run_mock_data.py patients
# 其他类型请参考 --list 查看所有选项
```

也可以通过Python模块的方式运行：

```bash
# 生成所有模拟数据
python -m mock_data_scripts.create_mockdata

# 生成特定类型的模拟数据
python -m mock_data_scripts.create_test_users
python -m mock_data_scripts.create_test_doctors
# 其他脚本使用类似方式运行
```

### 主要模拟数据脚本

- `create_mockdata.py` - 主脚本，调用所有其他模拟数据生成脚本
- `create_test_users.py` - 生成基础用户账号
- `create_test_organizations.py` - 生成医疗机构数据
- `create_test_doctors.py` - 生成医生数据
- `create_test_health_managers.py` - 生成健康管理师数据
- `create_test_patients.py` - 生成患者基础数据
- `create_test_rehab_plans.py` - 生成康复计划数据
- `create_test_health_records.py` - 生成健康记录数据
- `create_test_devices.py` - 生成设备和设备数据
- `init_dashboard_data.py` - 生成仪表盘数据
- `init_notification_data.py` - 生成系统通知数据

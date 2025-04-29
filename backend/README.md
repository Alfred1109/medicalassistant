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

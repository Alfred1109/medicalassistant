# Medical Rehabilitation Assistant

A dynamic agent-powered medical rehabilitation assistant system built with FastAPI, MongoDB, and React.

## Project Overview

This system provides a flexible platform for managing rehabilitation plans and exercises, with intelligent agent-based recommendations. The project follows a microservice architecture with a clear separation between backend and frontend.

### Key Features

- **User Management**: Support for patients, doctors, health managers, and administrators
- **Role-Based Access Control**: Comprehensive RBAC permission system with role-specific workspaces
- **Dynamic Agent System**: Customizable agent configurations for personalized assistance
- **Rehabilitation Plans**: Create and manage tailored rehabilitation plans with AI-powered recommendations
- **Exercise Recommendations**: AI-powered exercise recommendations based on patient conditions
- **Agent Chat Interface**: Natural language interaction with rehabilitation agents
- **Health Data Monitoring**: Track and visualize health data with threshold alerts
- **Patient-Doctor Communication**: Real-time messaging system for efficient communication
- **Medical Records Management**: Comprehensive health record system with version history
- **Follow-up Management**: Track and manage follow-up appointments and reminders

## Architecture

This project uses a microservice architecture with multiple specialized components:

### Backend

- **FastAPI**: Modern, fast Python web framework
- **MongoDB**: NoSQL database for flexible document storage
- **Motor**: Asynchronous MongoDB driver
- **Pydantic**: Data validation and settings management
- **JWT Authentication**: Secure API access with token-based auth
- **WebSocket**: Real-time communication for chat and notifications

### Frontend

- **React**: UI component library
- **Redux Toolkit**: State management with a focus on simplicity
- **Material UI**: Modern component library
- **TypeScript**: Type-safe JavaScript
- **Axios**: HTTP client for API communication
- **Role-Based Routing**: Route protection based on user roles

## Dynamic Agent System

The system's core feature is its dynamic agent architecture, which allows:

1. Creating custom agents with specific capabilities for rehabilitation contexts
2. Adding tools and actions dynamically to extend agent functionality
3. Personalized interactions based on patient data and conditions
4. Integration with various LLM providers (OpenAI, Anthropic)
5. Automated rehabilitation plan generation and recommendations
6. Parameter auto-configuration for optimal agent performance

## Role-Based Permission System

The system implements a comprehensive RBAC model:

1. Role-specific workspaces for doctors, health managers, patients, and administrators
2. Fine-grained permission control with configurable permission matrix
3. Resource categorization and access management
4. Role-based route guards for frontend security
5. Permission auditing and dynamic permission adjustment

## Getting Started

### Prerequisites

- Python 3.8+
- Node.js 16+
- MongoDB

### Backend Setup

1. Navigate to the backend directory:
```bash
cd backend
```

2. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows, use: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Configure environment variables in a `.env` file:
```
MONGODB_URL=mongodb://localhost:27017
DATABASE_NAME=rehab_assistant
SECRET_KEY=your_secret_key
OPENAI_API_KEY=your_openai_api_key
ANTHROPIC_API_KEY=your_anthropic_api_key
```

5. Run the server:
```bash
uvicorn app.main:app --reload
```

### Frontend Setup

1. Navigate to the frontend directory:
```bash
cd frontend
```

2. Install dependencies:
```bash
npm install
```

3. Start the development server:
```bash
npm run dev
```

### Quick Start Script

For convenience, you can use the start script:

```bash
./start-project.sh
```

This script will:
- Start MongoDB if not running
- Activate virtual environment
- Start the backend server
- Start the frontend development server

## API Documentation

Once the backend is running, access the auto-generated API documentation at:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Project Structure

```
.
├── backend/
│   ├── app/
│   │   ├── api/            # API endpoints (routers)
│   │   │   └── routers/    # Feature-specific routers
│   │   ├── core/           # Core functionality, config, dependencies
│   │   ├── db/             # Database connections and utils
│   │   ├── models/         # Database models
│   │   ├── schemas/        # Pydantic schemas for requests/responses
│   │   ├── services/       # Business logic layer
│   │   └── utils/          # Utility functions
│   └── tests/              # Test suite
└── frontend/
    ├── public/             # Static assets
    └── src/
        ├── components/     # Reusable UI components
        │   ├── Agent/      # Agent-related components
        │   ├── Doctor/     # Doctor workspace components
        │   ├── Patient/    # Patient workspace components
        │   ├── HealthManager/ # Health manager components
        │   ├── Admin/      # Admin components
        │   ├── Rehabilitation/ # Rehab-specific components
        │   └── common/     # Shared components
        ├── hooks/          # Custom React hooks
        ├── pages/          # Page components
        ├── services/       # API services
        ├── store/          # Redux store and slices
        ├── types/          # TypeScript type definitions
        └── utils/          # Utility functions
```

## Development Progress

The project is actively being developed with multiple modules at different completion stages:
- Health Record Management: 75% complete
- Follow-up Management: 70% complete
- Rehabilitation Plan Management: 92% complete
- Health Data Monitoring: 88% complete
- User Management: 65% complete
- System Integration: 65% complete
- Doctor-Patient Communication: 85% complete
- Informed Consent: 60% complete
- Mini Program Adaptation: 10% complete
- Intelligent Rehabilitation Features: 80% complete
- Intelligent Agent System: 85% complete
- Role Permission System: 90% complete

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- OpenAI and Anthropic for their LLM APIs
- FastAPI, React, and other open-source libraries used in this project 
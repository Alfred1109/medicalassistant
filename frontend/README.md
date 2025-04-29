# Medical Rehabilitation Assistant Frontend

The React-based frontend for the Medical Rehabilitation Assistant system.

## Features

- Material UI components for a modern, accessible interface
- Redux for state management
- Type-safe with TypeScript
- Dynamic agent interaction through chat interfaces
- Rehabilitation plan and exercise management
- Agent configuration interface

## Tech Stack

- **React**: UI component library
- **Redux Toolkit**: State management with a focus on simplicity
- **Material UI**: Modern component library
- **TypeScript**: Type-safe JavaScript
- **Axios**: HTTP client for API communication
- **Vite**: Fast build tool
- **Formik & Yup**: Form handling and validation

## Getting Started

### Prerequisites

- Node.js 16+
- npm or yarn

### Installation

1. Install dependencies:
```bash
npm install
```

2. Start the development server:
```bash
npm run dev
```

3. Build for production:
```bash
npm run build
```

## Project Structure

```
src/
├── components/       # Reusable UI components
│   ├── Agent/        # Agent-related components
│   ├── Layout/       # Layout components
│   └── Rehabilitation/ # Rehabilitation components
├── hooks/            # Custom React hooks
├── pages/            # Page components
├── services/         # API services
├── store/            # Redux store and slices
│   └── slices/       # Redux slices
├── types/            # TypeScript type definitions
└── utils/            # Utility functions
```

## Key Components

### Agent System

The frontend provides interfaces for:

1. **Agent Creation and Configuration**: Customizable agent setup with system prompts and tools
2. **Agent Chat Interface**: Natural language interaction with rehabilitation agents
3. **Exercise Recommendations**: AI-powered exercise suggestions based on patient conditions

### Authentication

User authentication is handled using JWT tokens with:

- Token storage in localStorage
- Automatic token inclusion in API requests
- Route protection for authenticated users
- Role-based access control

### Rehabilitation Management

The app includes interfaces for:

- Creating and managing rehabilitation plans
- Adding exercises to plans
- Tracking progress
- Receiving personalized recommendations

## Development Guide

### Adding New Features

1. Create necessary components in the appropriate directories
2. Add Redux slice if state management is needed
3. Create any required API services
4. Update routing in App.tsx

### Code Style

This project uses ESLint and Prettier for code quality:

```bash
# Run linting
npm run lint

# Format code
npm run format
```

### Testing

```bash
# Run tests
npm test

# Run tests in watch mode
npm run test:watch
```

## Component Examples

### Agent Chat

```jsx
<AgentChat 
  agentId="agent_id" 
  patientId="patient_id"
  contextData={{ condition: "knee", goal: "mobility" }}
  onRecommendation={(data) => console.log(data)}
/>
```

### Exercise Recommendation

```jsx
<ExerciseRecommendation
  patientId="patient_id"
  planId="plan_id" // Optional - if provided, allows adding to rehab plan
/>
```

## API Integration

All API interactions are centralized in the `services/api.ts` file, separated by domain:

- `authAPI`: Authentication endpoints
- `rehabAPI`: Rehabilitation-related endpoints
- `agentAPI`: Agent management and interaction endpoints
- `userAPI`: User management endpoints

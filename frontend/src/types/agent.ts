export interface Agent {
  id: string;
  name: string;
  description: string;
  model: string;
  systemPrompt: string;
  tools: AgentTool[];
  userId: string;
  metadata: Record<string, any>;
  createdAt: string;
  updatedAt: string;
}

export interface AgentTool {
  name: string;
  description: string;
  parameters: Record<string, any>; // JSON Schema
  required: boolean;
}

export interface AgentState {
  agents: Agent[];
  selectedAgent: Agent | null;
  loading: boolean;
  generating: boolean;
  error: string | null;
}

export interface AgentFormValues {
  name: string;
  description: string;
  model: string;
  systemPrompt: string;
  tools: AgentTool[];
  metadata: Record<string, any>;
}

export interface AgentQuery {
  agentId: string;
  query: string;
  contextId?: string;
}

export interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: string;
}

export interface Conversation {
  id: string;
  agentId: string;
  messages: Message[];
  createdAt: string;
  updatedAt: string;
  title: string;
  userId: string;
}

export interface AgentResponse {
  message: string;
  conversationId: string;
  recommendations?: any[];  // Type depends on the specific agent's response format
  actions?: any[]; // Type depends on the specific agent's response format
  metadata?: Record<string, any>;
}

export interface AgentResponseState {
  response: AgentResponse | null;
  loading: boolean;
  error: string | null;
} 
import { createSlice, createAsyncThunk, PayloadAction } from '@reduxjs/toolkit';
import axios from 'axios';

// 使用环境变量获取API基础URL
const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:5502';

// Define the agent interface
export interface Agent {
  _id: string;
  name: string;
  description: string;
  type?: string;
  model: string;
  system_prompt?: string;
  tools?: any[];
  metadata?: Record<string, any>;
  parameters?: Record<string, any>;
  created_at: string;
  updated_at: string;
}

// Define the agent state interface
interface AgentState {
  agents: Agent[];
  selectedAgent: Agent | null;
  loading: boolean;
  error: string | null;
  queryResponse: string | null;
}

// Define the initial state
const initialState: AgentState = {
  agents: [],
  selectedAgent: null,
  loading: false,
  error: null,
  queryResponse: null,
};

// Define async thunks
export const fetchAgents = createAsyncThunk(
  'agents/fetchAgents',
  async (_, { rejectWithValue }) => {
    try {
      const response = await axios.get(`${BASE_URL}/api/agents`);
      return response.data;
    } catch (error: any) {
      return rejectWithValue(error.response?.data?.message || '获取助手列表失败');
    }
  }
);

export const fetchAgentById = createAsyncThunk(
  'agents/fetchAgentById',
  async (id: string, { rejectWithValue }) => {
    try {
      const response = await axios.get(`${BASE_URL}/api/agents/${id}`);
      return response.data;
    } catch (error: any) {
      return rejectWithValue(error.response?.data?.message || '获取助手详情失败');
    }
  }
);

export const createAgent = createAsyncThunk(
  'agents/createAgent',
  async (agentData: Omit<Agent, 'id' | 'createdAt' | 'updatedAt'>, { rejectWithValue }) => {
    try {
      const response = await axios.post(`${BASE_URL}/api/agents`, agentData);
      return response.data;
    } catch (error: any) {
      return rejectWithValue(error.response?.data?.message || '创建助手失败');
    }
  }
);

export const updateAgent = createAsyncThunk(
  'agents/updateAgent',
  async ({ id, agentData }: { id: string; agentData: Partial<Agent> }, { rejectWithValue }) => {
    try {
      const response = await axios.put(`${BASE_URL}/api/agents/${id}`, agentData);
      return response.data;
    } catch (error: any) {
      return rejectWithValue(error.response?.data?.message || '更新助手失败');
    }
  }
);

export const deleteAgent = createAsyncThunk(
  'agents/deleteAgent',
  async (id: string, { rejectWithValue }) => {
    try {
      await axios.delete(`${BASE_URL}/api/agents/${id}`);
      return id;
    } catch (error: any) {
      return rejectWithValue(error.response?.data?.message || '删除助手失败');
    }
  }
);

export const queryAgent = createAsyncThunk(
  'agents/queryAgent',
  async ({ id, query }: { id: string; query: string }, { rejectWithValue }) => {
    try {
      const response = await axios.post(`${BASE_URL}/api/agents/${id}/query`, { query });
      return response.data.response;
    } catch (error: any) {
      return rejectWithValue(error.response?.data?.message || '查询助手失败');
    }
  }
);

// Create the agent slice
const agentSlice = createSlice({
  name: 'agents',
  initialState,
  reducers: {
    clearQueryResponse: (state) => {
      state.queryResponse = null;
    },
    setSelectedAgent: (state, action: PayloadAction<Agent | null>) => {
      state.selectedAgent = action.payload;
    },
  },
  extraReducers: (builder) => {
    builder
      // Fetch agents
      .addCase(fetchAgents.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(fetchAgents.fulfilled, (state, action) => {
        state.loading = false;
        state.agents = action.payload;
      })
      .addCase(fetchAgents.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload as string;
      })
      
      // Fetch agent by ID
      .addCase(fetchAgentById.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(fetchAgentById.fulfilled, (state, action) => {
        state.loading = false;
        state.selectedAgent = action.payload;
      })
      .addCase(fetchAgentById.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload as string;
      })
      
      // Create agent
      .addCase(createAgent.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(createAgent.fulfilled, (state, action) => {
        state.loading = false;
        state.agents.push(action.payload);
      })
      .addCase(createAgent.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload as string;
      })
      
      // Update agent
      .addCase(updateAgent.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(updateAgent.fulfilled, (state, action) => {
        state.loading = false;
        const index = state.agents.findIndex((agent) => agent._id === action.payload._id);
        if (index !== -1) {
          state.agents[index] = action.payload;
        }
        if (state.selectedAgent?._id === action.payload._id) {
          state.selectedAgent = action.payload;
        }
      })
      .addCase(updateAgent.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload as string;
      })
      
      // Delete agent
      .addCase(deleteAgent.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(deleteAgent.fulfilled, (state, action) => {
        state.loading = false;
        state.agents = state.agents.filter((agent) => agent._id !== action.payload);
        if (state.selectedAgent?._id === action.payload) {
          state.selectedAgent = null;
        }
      })
      .addCase(deleteAgent.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload as string;
      })
      
      // Query agent
      .addCase(queryAgent.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(queryAgent.fulfilled, (state, action) => {
        state.loading = false;
        state.queryResponse = action.payload;
      })
      .addCase(queryAgent.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload as string;
        state.queryResponse = null;
      });
  },
});

export const { clearQueryResponse, setSelectedAgent } = agentSlice.actions;
export default agentSlice.reducer; 
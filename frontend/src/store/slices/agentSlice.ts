import { createSlice, createAsyncThunk, PayloadAction } from '@reduxjs/toolkit';
import axios from 'axios';
import { API_BASE_URL } from '../../config/constants';
import { ThunkApiConfig } from '../types';


// 助手可调用的工具
export interface Tool {
  name: string;
  description: string;
  parameters: Record<string, any>;
  required_parameters?: string[];
}

// Define the agent interface
export interface Agent {
  _id: string;
  name: string;
  description: string;
  type?: string;
  model: string;
  system_prompt?: string;
  tools?: Tool[];
  metadata?: Record<string, any>;
  parameters?: Record<string, any>;
  created_at: string;
  updated_at: string;
}

// 助手提问接口的返回结构(对应后端 AgentQueryResponse)
export interface AgentQueryResult {
  response: string;
  thinking?: string | null;
  tool_calls?: Array<Record<string, any>> | null;
  metadata?: Record<string, any> | null;
}

// Define the agent state interface
export interface AgentState {
  agents: Agent[];
  selectedAgent: Agent | null;
  loading: boolean;
  error: string | null;
  queryResponse: string | null;
  /** 提问接口返回的附加数据(如推荐动作) */
  queryMetadata: Record<string, any> | null;
}

// Define the initial state
const initialState: AgentState = {
  agents: [],
  selectedAgent: null,
  loading: false,
  error: null,
  queryResponse: null,
  queryMetadata: null,
};

// Define async thunks
export const fetchAgents = createAsyncThunk<Agent[], void, ThunkApiConfig>(
  'agents/fetchAgents',
  async (_, { rejectWithValue }) => {
    try {
      const response = await axios.get(`${API_BASE_URL}/agents`);
      return response.data;
    } catch (error: any) {
      return rejectWithValue(error.response?.data?.message || '获取助手列表失败');
    }
  }
);

export const fetchAgentById = createAsyncThunk<Agent, string, ThunkApiConfig>(
  'agents/fetchAgentById',
  async (id: string, { rejectWithValue }) => {
    try {
      const response = await axios.get(`${API_BASE_URL}/agents/${id}`);
      return response.data;
    } catch (error: any) {
      return rejectWithValue(error.response?.data?.message || '获取助手详情失败');
    }
  }
);

export const createAgent = createAsyncThunk<Agent, Partial<Agent>, ThunkApiConfig>(
  'agents/createAgent',
  async (agentData: Partial<Agent>, { rejectWithValue }) => {
    try {
      const response = await axios.post(`${API_BASE_URL}/agents`, agentData);
      return response.data;
    } catch (error: any) {
      return rejectWithValue(error.response?.data?.message || '创建助手失败');
    }
  }
);

export const updateAgent = createAsyncThunk<
  Agent,
  { id: string; agentData: Partial<Agent> },
  ThunkApiConfig
>(
  'agents/updateAgent',
  async ({ id, agentData }: { id: string; agentData: Partial<Agent> }, { rejectWithValue }) => {
    try {
      const response = await axios.put(`${API_BASE_URL}/agents/${id}`, agentData);
      return response.data;
    } catch (error: any) {
      return rejectWithValue(error.response?.data?.message || '更新助手失败');
    }
  }
);

export const deleteAgent = createAsyncThunk<string, string, ThunkApiConfig>(
  'agents/deleteAgent',
  async (id: string, { rejectWithValue }) => {
    try {
      await axios.delete(`${API_BASE_URL}/agents/${id}`);
      return id;
    } catch (error: any) {
      return rejectWithValue(error.response?.data?.message || '删除助手失败');
    }
  }
);

export const queryAgent = createAsyncThunk<
  AgentQueryResult,
  { id: string; query: string },
  ThunkApiConfig
>(
  'agents/queryAgent',
  async ({ id, query }: { id: string; query: string }, { rejectWithValue }) => {
    try {
      const response = await axios.post(`${API_BASE_URL}/agents/${id}/query`, { query });
      return response.data as AgentQueryResult;
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
      state.queryMetadata = null;
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
        state.queryResponse = action.payload?.response ?? null;
        state.queryMetadata = action.payload?.metadata ?? null;
      })
      .addCase(queryAgent.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload as string;
        state.queryResponse = null;
        state.queryMetadata = null;
      });
  },
});

export const { clearQueryResponse, setSelectedAgent } = agentSlice.actions;
export default agentSlice.reducer; 
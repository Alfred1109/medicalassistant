import { API_COLLECTION_PATHS } from '../../config/apiPaths';
import httpClient from '../../services/httpClient';
import { createSlice, createAsyncThunk, PayloadAction } from '@reduxjs/toolkit';
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

/** queryAgent 失败时的结构化载荷：透传后端错误码，便于 UI 区分可重试错误与配置问题 */
export interface QueryAgentError {
  /** 面向用户的提示信息 */
  message: string;
  /** 后端 error_code（如 LLM_NOT_CONFIGURED），无则为 null */
  code: string | null;
  /** HTTP 状态码，无则为 null */
  status: number | null;
}

// Define the agent state interface
export interface AgentState {
  agents: Agent[];
  selectedAgent: Agent | null;
  loading: boolean;
  error: string | null;
  queryResponse: string | null;
  /** 最近一次 queryAgent 失败的后端错误码（如 LLM_NOT_CONFIGURED），无则为 null */
  queryErrorCode: string | null;
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
  queryErrorCode: null,
  queryMetadata: null,
};

// Define async thunks
export const fetchAgents = createAsyncThunk<Agent[], void, ThunkApiConfig>(
  'agents/fetchAgents',
  async (_, { rejectWithValue }) => {
    try {
      const response = await httpClient.get(API_COLLECTION_PATHS.AGENTS);
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
      const response = await httpClient.get(`/agents/${id}`);
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
      const response = await httpClient.post(API_COLLECTION_PATHS.AGENTS, agentData);
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
      const response = await httpClient.put(`/agents/${id}`, agentData);
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
      await httpClient.delete(`/agents/${id}`);
      return id;
    } catch (error: any) {
      return rejectWithValue(error.response?.data?.message || '删除助手失败');
    }
  }
);

export const queryAgent = createAsyncThunk<
  AgentQueryResult,
  { id: string; query: string },
  Omit<ThunkApiConfig, 'rejectValue'> & { rejectValue: QueryAgentError }
>(
  'agents/queryAgent',
  async ({ id, query }: { id: string; query: string }, { rejectWithValue }) => {
    try {
      const response = await httpClient.post(`/agents/${id}/query`, { query });
      return response.data as AgentQueryResult;
    } catch (error: any) {
      const status: number | null = error?.response?.status ?? null;
      // 后端 AppBaseException 统一返回 { error: error_code, message, ... }
      const code: string | null = error?.response?.data?.error ?? null;
      if (status === 503 && code === 'LLM_NOT_CONFIGURED') {
        // LLM 未配置属于部署配置问题，重试无意义。
        return rejectWithValue({ message: 'LLM 未配置，请联系管理员', code, status });
      }
      // 其他错误（网络波动、超时、临时故障）均可重试。
      return rejectWithValue({ message: '查询助手失败，请稍后重试', code, status });
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
      state.queryErrorCode = null;
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
        state.queryErrorCode = null;
      })
      .addCase(queryAgent.fulfilled, (state, action) => {
        state.loading = false;
        state.queryResponse = action.payload?.response ?? null;
        state.queryMetadata = action.payload?.metadata ?? null;
      })
      .addCase(queryAgent.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload?.message ?? '查询助手失败';
        state.queryErrorCode = action.payload?.code ?? null;
        state.queryResponse = null;
        state.queryMetadata = null;
      });
  },
});

export const { clearQueryResponse, setSelectedAgent } = agentSlice.actions;
export default agentSlice.reducer; 
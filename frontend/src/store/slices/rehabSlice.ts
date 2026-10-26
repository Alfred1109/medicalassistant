import { createSlice, createAsyncThunk, PayloadAction } from '@reduxjs/toolkit';
import axios, { AxiosError, AxiosResponse } from 'axios';
import {
  RehabPlan,
  Exercise,
  RehabState,
  ExerciseFormValues,
  ExerciseCompletionParams,
  RecommendationRequest
} from '../../types/rehab';
import { API_ORIGIN } from '../../config/constants';
import { ThunkApiConfig } from '../types';

// 领域类型统一放在 types/rehab,这里再导出一次,方便组件从 slice 统一引入
export type {
  Exercise,
  ExerciseFormValues,
  PlanExercise,
  Recommendation,
  RecommendationRequest,
  RehabPlan,
  RehabPlanFormValues,
  RehabState,
} from '../../types/rehab';

// API 根地址(不含 /api),由 nginx 反向代理转发
const BASE_URL = API_ORIGIN;

// 后端错误响应体:不同接口分别用 message 或 detail 字段
interface ApiErrorPayload {
  message?: string;
  detail?: string;
}

// Initial state
const initialState: RehabState = {
  plans: [],
  selectedPlan: null,
  exercises: [],
  selectedExercise: null,
  loading: false,
  error: null,
  recommendations: [],
};

// Async thunks
export const fetchRehabPlans = createAsyncThunk<RehabPlan[], void, ThunkApiConfig>(
  'rehab/fetchRehabPlans',
  async (_: void, { rejectWithValue }) => {
    try {
      const response: AxiosResponse<RehabPlan[]> = await axios.get(`${BASE_URL}/api/rehabilitation/plans`);
      return response.data;
    } catch (error) {
      const axiosError = error as AxiosError<ApiErrorPayload>;
      return rejectWithValue(axiosError.response?.data?.message || '获取康复计划列表失败');
    }
  }
);

export const fetchRehabPlanById = createAsyncThunk<RehabPlan, string, ThunkApiConfig>(
  'rehab/fetchRehabPlanById',
  async (id: string, { rejectWithValue }) => {
    try {
      const response: AxiosResponse<RehabPlan> = await axios.get(`${BASE_URL}/api/rehabilitation/plans/${id}`);
      return response.data;
    } catch (error) {
      const axiosError = error as AxiosError<ApiErrorPayload>;
      return rejectWithValue(axiosError.response?.data?.message || '获取康复计划详情失败');
    }
  }
);

export const createRehabPlan = createAsyncThunk<RehabPlan, Partial<RehabPlan>, ThunkApiConfig>(
  'rehab/createRehabPlan',
  async (planData: Partial<RehabPlan>, { rejectWithValue }) => {
    try {
      const response = await axios.post(`${BASE_URL}/api/rehabilitation/plans`, planData);
      return response.data;
    } catch (error: any) {
      return rejectWithValue(error.response?.data?.message || '创建康复计划失败');
    }
  }
);

export const updateRehabPlan = createAsyncThunk<
  RehabPlan,
  { id: string; planData: Partial<RehabPlan> },
  ThunkApiConfig
>(
  'rehab/updateRehabPlan',
  async ({ id, planData }: { id: string; planData: Partial<RehabPlan> }, { rejectWithValue }) => {
    try {
      const response = await axios.put(`${BASE_URL}/api/rehabilitation/plans/${id}`, planData);
      return response.data;
    } catch (error: any) {
      return rejectWithValue(error.response?.data?.message || '更新康复计划失败');
    }
  }
);

export const deleteRehabPlan = createAsyncThunk<string, string, ThunkApiConfig>(
  'rehab/deleteRehabPlan',
  async (id: string, { rejectWithValue }) => {
    try {
      await axios.delete(`${BASE_URL}/api/rehabilitation/plans/${id}`);
      return id;
    } catch (error: any) {
      return rejectWithValue(error.response?.data?.message || '删除康复计划失败');
    }
  }
);

export const fetchExercises = createAsyncThunk<Exercise[], void, ThunkApiConfig>(
  'rehab/fetchExercises',
  async (_, { rejectWithValue }) => {
    try {
      const response = await axios.post(`${BASE_URL}/api/rehabilitation/exercises/list`, {
        category: null,
        difficulty: null,
        body_parts: [],
        skip: 0,
        limit: 100
      });
      return response.data;
    } catch (error: any) {
      return rejectWithValue(error.response?.data?.detail || 'Failed to fetch exercises');
    }
  }
);

export const createExercise = createAsyncThunk<Exercise, ExerciseFormValues, ThunkApiConfig>(
  'rehab/createExercise',
  async (exerciseData: ExerciseFormValues, { rejectWithValue }) => {
    try {
      const response = await axios.post(`${BASE_URL}/api/rehabilitation/exercises`, exerciseData);
      return response.data;
    } catch (error: any) {
      return rejectWithValue(error.response?.data?.detail || 'Failed to create exercise');
    }
  }
);

// 后端记录运动进度的接口是 POST /plans/{plan_id}/exercises/{exercise_id}/progress
export const updateExerciseCompletion = createAsyncThunk<
  RehabPlan,
  ExerciseCompletionParams,
  ThunkApiConfig
>(
  'rehab/updateExerciseCompletion',
  async ({ planId, exerciseId, completed }: ExerciseCompletionParams, { rejectWithValue }) => {
    try {
      const response = await axios.post(
        `${BASE_URL}/api/rehabilitation/plans/${planId}/exercises/${exerciseId}/progress`,
        { completed }
      );
      return response.data;
    } catch (error: any) {
      return rejectWithValue(error.response?.data?.message || '更新运动完成状态失败');
    }
  }
);

// 后端要求用 { exercise_ids: [...] } 作为请求体
export const addExercisesToPlan = createAsyncThunk<
  RehabPlan,
  { planId: string; exerciseIds: string[] },
  ThunkApiConfig
>(
  'rehab/addExercisesToPlan',
  async ({ planId, exerciseIds }: { planId: string; exerciseIds: string[] }, { rejectWithValue }) => {
    try {
      const response = await axios.post(`${BASE_URL}/api/rehabilitation/plans/${planId}/exercises`, {
        exercise_ids: exerciseIds,
      });
      return response.data;
    } catch (error: any) {
      return rejectWithValue(error.response?.data?.message || '添加运动到康复计划失败');
    }
  }
);

// 后端的推荐接口是 GET,查询参数用 snake_case
export const getRecommendations = createAsyncThunk<
  Exercise[],
  RecommendationRequest,
  ThunkApiConfig
>(
  'rehab/getRecommendations',
  async ({ patientId, condition, goal, agentId }: RecommendationRequest, { rejectWithValue }) => {
    try {
      const response = await axios.get(`${BASE_URL}/api/rehabilitation/exercises/recommendations`, {
        params: {
          patient_id: patientId,
          condition,
          goal,
          agent_id: agentId,
        },
      });
      return response.data;
    } catch (error: any) {
      return rejectWithValue(error.response?.data?.message || '获取推荐运动失败');
    }
  }
);

export const fetchExerciseById = createAsyncThunk<Exercise, string, ThunkApiConfig>(
  'rehab/fetchExerciseById',
  async (id: string, { rejectWithValue }) => {
    try {
      const response = await axios.get(`${BASE_URL}/api/rehabilitation/exercises/${id}`);
      return response.data;
    } catch (error: any) {
      return rejectWithValue(error.response?.data?.detail || '获取运动详情失败');
    }
  }
);

export const deleteExercise = createAsyncThunk<string, string, ThunkApiConfig>(
  'rehab/deleteExercise',
  async (id: string, { rejectWithValue }) => {
    try {
      await axios.delete(`${BASE_URL}/api/rehabilitation/exercises/${id}`);
      return id;
    } catch (error: any) {
      return rejectWithValue(error.response?.data?.message || '删除运动失败');
    }
  }
);

export const updateExercise = createAsyncThunk<
  Exercise,
  { id: string; exerciseData: Partial<Exercise> },
  ThunkApiConfig
>(
  'rehab/updateExercise',
  async ({ id, exerciseData }: { id: string; exerciseData: Partial<Exercise> }, { rejectWithValue }) => {
    try {
      const response = await axios.put(`${BASE_URL}/api/rehabilitation/exercises/${id}`, exerciseData);
      return response.data;
    } catch (error: any) {
      return rejectWithValue(error.response?.data?.message || '更新运动失败');
    }
  }
);

// Slice
const rehabSlice = createSlice({
  name: 'rehab',
  initialState,
  reducers: {
    clearSelectedPlan: (state) => {
      state.selectedPlan = null;
    },
    clearRehabError: (state) => {
      state.error = null;
    },
  },
  extraReducers: (builder) => {
    builder
      // fetchRehabPlans
      .addCase(fetchRehabPlans.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(fetchRehabPlans.fulfilled, (state, action) => {
        state.loading = false;
        state.plans = action.payload;
      })
      .addCase(fetchRehabPlans.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload as string;
      })
      
      // fetchRehabPlanById
      .addCase(fetchRehabPlanById.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(fetchRehabPlanById.fulfilled, (state, action) => {
        state.loading = false;
        state.selectedPlan = action.payload;
      })
      .addCase(fetchRehabPlanById.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload as string;
      })
      
      // createRehabPlan
      .addCase(createRehabPlan.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(createRehabPlan.fulfilled, (state, action) => {
        state.loading = false;
        state.plans.push(action.payload);
        state.selectedPlan = action.payload;
      })
      .addCase(createRehabPlan.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload as string;
      })
      
      // updateRehabPlan
      .addCase(updateRehabPlan.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(updateRehabPlan.fulfilled, (state, action) => {
        state.loading = false;
        const index = state.plans.findIndex((plan) => plan.id === action.payload.id);
        if (index !== -1) {
          state.plans[index] = action.payload;
        }
        if (state.selectedPlan?.id === action.payload.id) {
          state.selectedPlan = action.payload;
        }
      })
      .addCase(updateRehabPlan.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload as string;
      })
      
      // deletePlan
      .addCase(deleteRehabPlan.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(deleteRehabPlan.fulfilled, (state, action) => {
        state.loading = false;
        state.plans = state.plans.filter((plan) => plan.id !== action.payload);
        if (state.selectedPlan?.id === action.payload) {
          state.selectedPlan = null;
        }
      })
      .addCase(deleteRehabPlan.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload as string;
      })
      
      // fetchExercises
      .addCase(fetchExercises.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(fetchExercises.fulfilled, (state, action: PayloadAction<Exercise[]>) => {
        state.loading = false;
        state.exercises = action.payload;
      })
      .addCase(fetchExercises.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload as string;
      })
      
      // createExercise
      .addCase(createExercise.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(createExercise.fulfilled, (state, action: PayloadAction<Exercise>) => {
        state.loading = false;
        state.exercises.push(action.payload);
      })
      .addCase(createExercise.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload as string;
      })
      
      // updateExerciseCompletion
      .addCase(updateExerciseCompletion.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(updateExerciseCompletion.fulfilled, (state, action) => {
        state.loading = false;
        
        // Update the selected plan if it matches
        if (state.selectedPlan?.id === action.payload.id) {
          state.selectedPlan = action.payload;
        }
        
        // Update in the plans array
        const index = state.plans.findIndex((plan) => plan.id === action.payload.id);
        if (index !== -1) {
          state.plans[index] = action.payload;
        }
      })
      .addCase(updateExerciseCompletion.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload as string;
      })
      
      // addExercisesToPlan
      .addCase(addExercisesToPlan.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(addExercisesToPlan.fulfilled, (state, action) => {
        state.loading = false;
        
        // Update the selected plan if it matches
        if (state.selectedPlan?.id === action.payload.id) {
          state.selectedPlan = action.payload;
        }
        
        // Update in the plans array
        const index = state.plans.findIndex((plan) => plan.id === action.payload.id);
        if (index !== -1) {
          state.plans[index] = action.payload;
        }
      })
      .addCase(addExercisesToPlan.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload as string;
      })
      
      // Get recommendations
      .addCase(getRecommendations.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(getRecommendations.fulfilled, (state, action) => {
        state.loading = false;
        state.recommendations = action.payload;
      })
      .addCase(getRecommendations.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload as string;
      })
      
      // fetchExerciseById
      .addCase(fetchExerciseById.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(fetchExerciseById.fulfilled, (state, action: PayloadAction<Exercise>) => {
        state.loading = false;
        state.selectedExercise = action.payload;
      })
      .addCase(fetchExerciseById.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload as string;
      })
      
      // deleteExercise
      .addCase(deleteExercise.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(deleteExercise.fulfilled, (state, action: PayloadAction<string>) => {
        state.loading = false;
        state.exercises = state.exercises.filter(exercise => exercise.id !== action.payload);
        if (state.selectedExercise?.id === action.payload) {
          state.selectedExercise = null;
        }
      })
      .addCase(deleteExercise.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload as string;
      })
      
      // updateExercise
      .addCase(updateExercise.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(updateExercise.fulfilled, (state, action: PayloadAction<Exercise>) => {
        state.loading = false;
        // 更新exercises数组中的项
        const index = state.exercises.findIndex(exercise => exercise.id === action.payload.id);
        if (index !== -1) {
          state.exercises[index] = action.payload;
        }
        // 如果当前选中的是更新的项，也更新selectedExercise
        if (state.selectedExercise?.id === action.payload.id) {
          state.selectedExercise = action.payload;
        }
      })
      .addCase(updateExercise.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload as string;
      });
  },
});

export const { clearSelectedPlan, clearRehabError } = rehabSlice.actions;
export default rehabSlice.reducer; 
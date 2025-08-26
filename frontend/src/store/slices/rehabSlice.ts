import { createSlice, createAsyncThunk, PayloadAction } from '@reduxjs/toolkit';
import axios, { AxiosError, AxiosResponse } from 'axios';
import { 
  RehabPlan, 
  Exercise, 
  RehabState, 
  RehabPlanFormValues, 
  ExerciseFormValues,
  ExerciseCompletionParams,
  RecommendationRequest,
  Recommendation
} from '../../types/rehab';

// API基础URL
const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:5502';

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
export const fetchRehabPlans = createAsyncThunk(
  'rehab/fetchRehabPlans',
  async (_: void, { rejectWithValue }) => {
    try {
      const response: AxiosResponse<RehabPlan[]> = await axios.get(`${BASE_URL}/api/rehabilitation/plans`);
      return response.data;
    } catch (error) {
      const axiosError = error as AxiosError;
      return rejectWithValue(axiosError.response?.data?.message || '获取康复计划列表失败');
    }
  }
);

export const fetchRehabPlanById = createAsyncThunk(
  'rehab/fetchRehabPlanById',
  async (id: string, { rejectWithValue }) => {
    try {
      const response: AxiosResponse<RehabPlan> = await axios.get(`${BASE_URL}/api/rehabilitation/plans/${id}`);
      return response.data;
    } catch (error) {
      const axiosError = error as AxiosError;
      return rejectWithValue(axiosError.response?.data?.message || '获取康复计划详情失败');
    }
  }
);

export const createRehabPlan = createAsyncThunk(
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

export const updateRehabPlan = createAsyncThunk(
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

export const deleteRehabPlan = createAsyncThunk(
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

export const fetchExercises = createAsyncThunk(
  'rehab/fetchExercises',
  async (_, { rejectWithValue }) => {
    try {
      const response = await axios.post(`${BASE_URL}/api/rehabilitation/exercises/list`, {
        category: null,
        difficulty: null,
        body_parts: null,
        skip: 0,
        limit: 100
      });
      return response.data;
    } catch (error: any) {
      return rejectWithValue(error.response?.data?.detail || 'Failed to fetch exercises');
    }
  }
);

export const createExercise = createAsyncThunk(
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

export const updateExerciseCompletion = createAsyncThunk(
  'rehab/updateExerciseCompletion',
  async ({ planId, exerciseId, completed }: { planId: string; exerciseId: string; completed: boolean }, { rejectWithValue }) => {
    try {
      const response = await axios.patch(
        `${BASE_URL}/api/rehabilitation/plans/${planId}/exercises/${exerciseId}`,
        { completed }
      );
      return response.data;
    } catch (error: any) {
      return rejectWithValue(error.response?.data?.message || '更新运动完成状态失败');
    }
  }
);

export const getRecommendedExercises = createAsyncThunk(
  'rehab/getRecommendedExercises',
  async (requestData: RecommendationRequest, { rejectWithValue }) => {
    try {
      const response = await axios.post(`${BASE_URL}/api/rehabilitation/exercises/recommendations`, requestData);
      return response.data;
    } catch (error: any) {
      return rejectWithValue(error.response?.data?.detail || 'Failed to get exercise recommendations');
    }
  }
);

export const addExercisesToPlan = createAsyncThunk(
  'rehab/addExercisesToPlan',
  async ({ planId, exercises }: { planId: string; exercises: Partial<Exercise>[] }, { rejectWithValue }) => {
    try {
      const response = await axios.post(`${BASE_URL}/api/rehabilitation/plans/${planId}/exercises`, { exercises });
      return response.data;
    } catch (error: any) {
      return rejectWithValue(error.response?.data?.message || '添加运动到康复计划失败');
    }
  }
);

export const getRecommendations = createAsyncThunk(
  'rehab/getRecommendations',
  async ({ patientId, condition }: { patientId: string; condition: string }, { rejectWithValue }) => {
    try {
      const response = await axios.get(`${BASE_URL}/api/rehabilitation/exercises/recommendations`, {
        params: { patientId, condition },
      });
      return response.data;
    } catch (error: any) {
      return rejectWithValue(error.response?.data?.message || '获取推荐运动失败');
    }
  }
);

export const fetchExerciseById = createAsyncThunk(
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

export const deleteExercise = createAsyncThunk(
  'rehab/deleteExercise',
  async (id: string, { rejectWithValue }) => {
    try {
      await axios.delete(`${BASE_URL}/api/rehabilitation/exercises/${id}`);
      return id;
    } catch (error: any) {
      return rejectWithValue(error.response?.data?.detail || '删除运动失败');
    }
  }
);

export const updateExercise = createAsyncThunk(
  'rehab/updateExercise',
  async ({ id, exerciseData }: { id: string; exerciseData: Partial<Exercise> }, { rejectWithValue }) => {
    try {
      const response = await axios.put(`${BASE_URL}/api/rehabilitation/exercises/${id}`, exerciseData);
      return response.data;
    } catch (error: any) {
      return rejectWithValue(error.response?.data?.detail || '更新运动失败');
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
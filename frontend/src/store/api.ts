import { API_COLLECTION_PATHS } from '../config/apiPaths';
import { createApi, fetchBaseQuery, BaseQueryFn, FetchArgs, FetchBaseQueryError } from '@reduxjs/toolkit/query/react';
import { API_BASE_URL } from '../config/constants';
import { assertSameOrigin, csrfHeaders, getAuthConfig, loginPageUrl } from '../services/authSession';

const rawBaseQuery = fetchBaseQuery({ baseUrl: API_BASE_URL });
const authenticatedBaseQuery: BaseQueryFn<string | FetchArgs, unknown, FetchBaseQueryError> = async (args, api, extra) => {
  try {
    const config = await getAuthConfig();
    const request = typeof args === 'string' ? { url: args } : { ...args };
    const headers = new Headers(request.headers as HeadersInit | undefined);
    if (config.mode === 'oidc') {
      assertSameOrigin(new URL(request.url, new URL(`${API_BASE_URL}/`, window.location.origin)).href);
      headers.delete('Authorization');
      for (const [name, value] of Object.entries(csrfHeaders(request.method))) headers.set(name, value);
      request.credentials = 'include';
    } else {
      const token = (api.getState() as { auth: { token: string | null } }).auth.token;
      if (token) headers.set('Authorization', `Bearer ${token}`);
    }
    const result = await rawBaseQuery({ ...request, headers }, api, extra);
    if (config.mode === 'oidc' && result.error?.status === 401) window.location.href = loginPageUrl();
    return result;
  } catch (error) {
    return { error: { status: 'CUSTOM_ERROR', error: error instanceof Error ? error.message : '登录状态验证失败' } };
  }
};

export const api = createApi({
  reducerPath: 'api',
  baseQuery: authenticatedBaseQuery,
  tagTypes: ['Patients', 'Doctors', 'HealthManagers', 'RehabPlans', 'Exercises', 'Agents'],
  endpoints: (builder) => ({
    // 患者相关端点
    getPatients: builder.query({
      query: (params) => ({
        url: 'patients',
        params,
      }),
      providesTags: ['Patients'],
    }),
    getPatientById: builder.query({
      query: (id) => `patients/${id}`,
      providesTags: (_result, _error, id) => [{ type: 'Patients', id }],
    }),
    createPatient: builder.mutation({
      query: (patient) => ({
        url: 'patients',
        method: 'POST',
        body: patient,
      }),
      invalidatesTags: ['Patients'],
    }),
    updatePatient: builder.mutation({
      query: ({ id, ...patient }) => ({
        url: `patients/${id}`,
        method: 'PUT',
        body: patient,
      }),
      invalidatesTags: (_result, _error, { id }) => [{ type: 'Patients', id }],
    }),
    
    // 医生相关端点
    getDoctors: builder.query({
      query: (params) => ({
        url: 'doctors',
        params,
      }),
      providesTags: ['Doctors'],
    }),
    
    // 康复计划相关端点
    getRehabPlans: builder.query({
      query: (params) => ({
        url: 'rehab-plans',
        params,
      }),
      providesTags: ['RehabPlans'],
    }),
    getRehabPlanById: builder.query({
      query: (id) => `rehab-plans/${id}`,
      providesTags: (_result, _error, id) => [{ type: 'RehabPlans', id }],
    }),
    createRehabPlan: builder.mutation({
      query: (plan) => ({
        url: 'rehab-plans',
        method: 'POST',
        body: plan,
      }),
      invalidatesTags: ['RehabPlans'],
    }),
    updateRehabPlan: builder.mutation({
      query: ({ id, ...plan }) => ({
        url: `rehab-plans/${id}`,
        method: 'PUT',
        body: plan,
      }),
      invalidatesTags: (_result, _error, { id }) => [{ type: 'RehabPlans', id }],
    }),
    
    // 智能代理相关端点
    getAgents: builder.query({
      query: (params) => ({
        url: API_COLLECTION_PATHS.AGENTS,
        params,
      }),
      providesTags: ['Agents'],
    }),
    getAgentById: builder.query({
      query: (id) => `agents/${id}`,
      providesTags: (_result, _error, id) => [{ type: 'Agents', id }],
    }),
    createAgent: builder.mutation({
      query: (agent) => ({
        url: API_COLLECTION_PATHS.AGENTS,
        method: 'POST',
        body: agent,
      }),
      invalidatesTags: ['Agents'],
    }),
    
    // 康复练习相关端点
    getExercises: builder.query({
      query: (params) => ({
        url: 'exercises',
        params,
      }),
      providesTags: ['Exercises'],
    }),
    getExerciseById: builder.query({
      query: (id) => `exercises/${id}`,
      providesTags: (_result, _error, id) => [{ type: 'Exercises', id }],
    }),
  }),
});

// 导出自动生成的hooks
export const {
  useGetPatientsQuery,
  useGetPatientByIdQuery,
  useCreatePatientMutation,
  useUpdatePatientMutation,
  useGetDoctorsQuery,
  useGetRehabPlansQuery,
  useGetRehabPlanByIdQuery,
  useCreateRehabPlanMutation,
  useUpdateRehabPlanMutation,
  useGetAgentsQuery,
  useGetAgentByIdQuery,
  useCreateAgentMutation,
  useGetExercisesQuery,
  useGetExerciseByIdQuery,
} = api;

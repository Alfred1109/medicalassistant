import { createApi, fetchBaseQuery } from '@reduxjs/toolkit/query/react';

// 设置API基础URL
const baseUrl = import.meta.env.VITE_API_URL || 'http://localhost:5502/api';

// 创建API服务
export const api = createApi({
  reducerPath: 'api',
  baseQuery: fetchBaseQuery({ 
    baseUrl,
    prepareHeaders: (headers, { getState }) => {
      // 从state中获取token
      const token = (getState() as any).auth.token;
      
      // 如果存在token，则在头部中添加Authorization
      if (token) {
        headers.set('Authorization', `Bearer ${token}`);
      }
      
      return headers;
    },
  }),
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
        url: 'agents',
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
        url: 'agents',
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
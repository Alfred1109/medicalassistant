import api from './api';

/**
 * 康复计划统计服务
 *
 * 数据来源（真实后端端点，见 backend/app/api/routers/rehabilitation_router.py:529-576）：
 * - GET /api/rehabilitation/plans/{plan_id}/statistics  计划进度统计
 *   （响应含 total_records/completed_records/completion_rate/avg_pain_level/
 *     weekly_completion[]/per_exercise[]/range_of_motion:null/muscle_strength:null/
 *     unsupported_metrics/data_source/data_notes）
 * - GET /api/rehabilitation/plans/{plan_id}/trends       运动趋势（按天聚合）
 *   （metric=difficulty|pain|completion；无值日 value 为 null / 不出现在 series）
 */

// 计划统计响应形状（见 rehabilitation_service.calculate_plan_statistics）
export interface PlanStatisticsResponse {
  plan_id: string;
  time_range: string;
  total_records: number;
  completed_records: number;
  completion_rate: number | null;
  avg_pain_level: number | null;
  avg_difficulty_rating: number | null;
  // 后端无对应数据字段，如实为 null
  range_of_motion: null;
  muscle_strength: null;
  weekly_completion: Array<{
    week_start: string;
    total: number;
    completed: number;
    completion_rate: number;
  }>;
  per_exercise: Array<{
    exercise_id: string;
    exercise_name: string;
    total: number;
    completed: number;
    completion_rate: number | null;
    avg_pain_level: number | null;
    avg_difficulty_rating: number | null;
  }>;
  unsupported_metrics: string[];
  data_source: string;
  data_notes: string[];
}

// 趋势响应形状（见 rehabilitation_service.get_exercise_trends）
export interface PlanTrendsResponse {
  plan_id: string;
  exercise_id: string | null;
  metric: 'difficulty' | 'pain' | 'completion';
  days: number;
  total_records: number;
  series: Array<{
    date: string;
    // metric=completion 时为 total/completed/completion_rate，否则为 value（当日均值，可能为 null）
    value?: number | null;
    total?: number;
    completed?: number;
    completion_rate?: number;
  }>;
  data_source: string;
  data_notes: string[];
}

export const rehabilitationService = {
  /** 获取康复计划进度统计（time_range: all/week/month） */
  getPlanStatistics: (
    planId: string,
    timeRange: 'all' | 'week' | 'month' = 'all'
  ): Promise<{ data: PlanStatisticsResponse }> =>
    api.get(`/rehabilitation/plans/${planId}/statistics`, {
      params: { time_range: timeRange },
    }),

  /** 获取康复运动趋势（metric: difficulty/pain/completion，按天聚合） */
  getPlanTrends: (
    planId: string,
    params?: {
      metric?: 'difficulty' | 'pain' | 'completion';
      days?: number;
      exercise_id?: string;
    }
  ): Promise<{ data: PlanTrendsResponse }> =>
    api.get(`/rehabilitation/plans/${planId}/trends`, { params }),
};

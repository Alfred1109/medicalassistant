/**
 * 康复计划 / 运动的领域类型。
 *
 * 字段命名与后端 API 保持一致(snake_case),
 * 对应 backend/app/schemas/rehabilitation.py。
 * 少数字段(如 completed、scheduledDate)只出现在“计划内的运动条目”上,
 * 因此都是可选的。
 */

// 计划中的运动条目:后端用 exercise_id + schedule + progress 描述
export interface PlanExercise {
  exercise_id?: string;
  exercise?: Exercise;
  schedule?: Record<string, any>;
  progress?: Record<string, any>;
  completed?: boolean;
  [key: string]: any;
}

export interface Exercise {
  id?: string;
  _id?: string;  // MongoDB ID 格式
  name: string;
  description: string;
  body_part?: string;
  difficulty?: 'easy' | 'medium' | 'hard';
  duration_minutes?: number;
  repetitions?: number;
  sets?: number;
  instructions?: string[];
  contraindications?: string[];
  benefits?: string[];
  video_url?: string;
  image_url?: string;
  metadata?: Record<string, any>;
  created_at?: string;
  updated_at?: string;
  // 仅“计划内的运动条目”会带这两个字段
  completed?: boolean;
  scheduledDate?: string;
}

export interface RehabPlan {
  id?: string;
  _id?: string;  // MongoDB ID 格式
  name: string;
  title?: string;              // 兼容旧数据结构
  description: string;
  patient_id?: string;
  patient_name?: string;
  practitioner_id?: string;
  userId?: string;             // 兼容旧数据结构
  start_date?: string;
  startDate?: string;
  end_date?: string;
  endDate?: string;
  condition?: string;
  goal?: string;
  frequency?: string;
  duration?: number;
  duration_days?: number;
  targetBodyPart?: string;
  completed?: boolean;
  status: 'active' | 'completed' | 'archived' | 'cancelled';
  exercises: Exercise[];
  created_at?: string;
  createdAt?: string;
  updated_at?: string;
  updatedAt?: string;
  createdBy?: string;
  tags?: string[];
  notes?: string;
  metadata?: Record<string, any>;
}

export interface Recommendation {
  id?: string;
  _id?: string;
  condition: string;
  goal: string;
  exercises: Exercise[];
  createdAt: string;
  updatedAt: string;
}

export interface RehabState {
  plans: RehabPlan[];
  selectedPlan: RehabPlan | null;
  selectedExercise: Exercise | null;
  exercises: Exercise[];
  /** 后端 /exercises/recommendations 返回的是运动列表 */
  recommendations: Exercise[];
  loading: boolean;
  error: string | null;
}

/** 新建 / 更新运动时提交的数据(对应后端 ExerciseCreate / ExerciseUpdate) */
export interface ExerciseFormValues {
  name: string;
  description: string;
  body_part?: string;
  difficulty?: 'easy' | 'medium' | 'hard';
  duration_minutes?: number;
  repetitions?: number;
  sets?: number;
  instructions?: string[];
  contraindications?: string[];
  benefits?: string[];
  video_url?: string;
  image_url?: string;
  metadata?: Record<string, any>;
}

/** 新建 / 更新康复计划时提交的数据 */
export interface RehabPlanFormValues {
  name: string;
  description: string;
  patient_id?: string;
  practitioner_id?: string;
  start_date?: string;
  end_date?: string;
  condition?: string;
  goal?: string;
  frequency?: string;
  status?: 'active' | 'completed' | 'archived' | 'cancelled';
  exercises?: Exercise[];
  notes?: string;
  metadata?: Record<string, any>;
}

export interface ExerciseCompletionParams {
  planId: string;
  exerciseId: string;
  completed: boolean;
}

export interface RecommendationRequest {
  condition: string;
  goal: string;
  patientId?: string;
  agentId?: string;
}

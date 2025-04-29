export interface Exercise {
  id?: string;
  _id?: string;  // MongoDB ID格式
  name: string;
  description: string;
  bodyPart?: string;
  difficulty?: 'easy' | 'medium' | 'hard';
  sets?: number;
  repetitions?: number;
  duration?: number;
  scheduledDate?: string;
  completed: boolean;
  videoUrl?: string;
  imageUrl?: string;
  instructions?: string[];
  createdAt: string;
  updatedAt: string;
}

export interface PlanExercise extends Exercise {
  planId: string;
  planName: string;
}

export interface RehabPlan {
  id?: string;
  _id?: string;  // MongoDB ID格式
  name: string;
  title?: string; // 兼容旧数据结构
  description: string;
  userId: string;
  status: 'active' | 'completed' | 'archived';
  startDate: string;
  endDate?: string;
  exercises: Exercise[];
  createdAt: string;
  updatedAt: string;
  createdBy?: string;
  tags?: string[];
  notes?: string;
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
  exercises: Exercise[];
  recommendations: Recommendation[];
  loading: boolean;
  error: string | null;
}

export interface ExerciseFormValues {
  name: string;
  description: string;
  bodyPart?: string;
  difficulty?: 'easy' | 'medium' | 'hard';
  sets?: number;
  repetitions?: number;
  duration?: number;
  scheduledDate?: string;
  videoUrl?: string;
  imageUrl?: string;
  instructions?: string[];
}

export interface RehabPlanFormValues {
  name: string;
  description: string;
  status: 'active' | 'completed' | 'archived';
  startDate: string;
  endDate?: string;
  exercises: string[]; // Exercise IDs to include
  tags?: string[];
  notes?: string;
}

export interface ExerciseCompletionParams {
  planId: string;
  exerciseId: string;
  completed: boolean;
}

export interface RecommendationRequest {
  condition: string;
  goal: string;
  agentId?: string;
} 
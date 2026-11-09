// 医生基本信息接口
export interface Doctor {
  id: string;
  name: string;
  department: string;
  title: string;
  specialty: string;
  email: string;
  phone: string;
  status: string;
  patients?: number;
  joinDate?: string;
  organization_id?: string;
}

// 随访记录接口
export interface FollowUp {
  id: string;
  patient_id: string;
  patient_name: string;
  doctor_id: string;
  doctor_name: string;
  planned_date: string;
  status: 'pending' | 'completed' | 'cancelled' | 'rescheduled';
  title: string;
  description?: string;
  notes?: string;
  completion_date?: string;
  created_at: string;
  updated_at: string;
} 
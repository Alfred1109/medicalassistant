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

// 模拟医生数据（作为备份）
export const mockDoctors: Doctor[] = [
  {
    id: "mock-doc-001",
    name: "张医生",
    department: "康复科",
    title: "主任医师",
    specialty: "神经康复",
    email: "zhang@hospital.com",
    phone: "13800138001",
    status: "在职",
    patients: 12,
    joinDate: "2020-01-15"
  },
  {
    id: "mock-doc-002",
    name: "李医生",
    department: "骨科",
    title: "副主任医师",
    specialty: "运动康复",
    email: "li@hospital.com",
    phone: "13800138002",
    status: "在职",
    patients: 8,
    joinDate: "2021-03-20"
  }
];

// 模拟随访记录（作为备份）
export const mockFollowUps: FollowUp[] = [
  {
    id: "follow-1",
    patient_id: "1",
    patient_name: "张三",
    doctor_id: "mock-doc-001",
    doctor_name: "张医生",
    planned_date: "2025-05-15",
    status: "pending",
    title: "术后复查",
    description: "检查腰椎间盘突出术后恢复情况",
    created_at: "2025-04-01",
    updated_at: "2025-04-01"
  },
  {
    id: "follow-2",
    patient_id: "2",
    patient_name: "李四",
    doctor_id: "mock-doc-002",
    doctor_name: "李医生",
    planned_date: "2025-04-20",
    status: "completed",
    title: "康复训练评估",
    description: "评估膝关节康复训练进展",
    notes: "恢复良好，可以适当增加运动量",
    completion_date: "2025-04-20",
    created_at: "2025-03-15",
    updated_at: "2025-04-20"
  }
]; 
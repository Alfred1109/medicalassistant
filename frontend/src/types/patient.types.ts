// 患者基本信息接口
export interface Patient {
  id: string;
  name: string;
  age: number;
  gender: string;
  diagnosis?: string;
  status?: string;
  height?: number;
  weight?: number;
  bloodType?: string;
  allergies?: string[];
  emergencyContact?: string;
  contactNumber?: string;
  email?: string;
  address?: string;
  doctorAssigned?: string;
  treatmentPlan?: string;
  admissionDate?: string;
}

// 病史记录接口
export interface MedicalHistory {
  date: string;
  diagnosis: string;
  doctor: string;
  hospital: string;
}

// 康复历史接口
export interface RehabHistory {
  date: string;
  type: string;
  details: string;
  duration: string;
  frequency: string;
}

// 用药记录接口
export interface Medication {
  name: string;
  dosage: string;
  frequency: string;
  startDate: string;
  endDate: string;
}

// 生命体征接口
export interface VitalSign {
  _id?: string;
  data_type: string;
  data?: Record<string, any>;
  data_content?: Record<string, any>;
  recorded_at?: string;
  metadata?: Record<string, any>;
}

// 患者完整健康记录接口
export interface PatientHealthRecord {
  id: string;
  name: string;
  age: number;
  gender: string;
  height: number;
  weight: number;
  bloodType: string;
  allergies: string[];
  emergencyContact: string;
  medicalHistory: MedicalHistory[];
  rehabHistory: RehabHistory[];
  medications: Medication[];
  vitalSigns: VitalSign[];
} 
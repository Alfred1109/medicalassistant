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
  date: string;
  bp: string;
  pulse: number;
  temp: number;
  respRate: number;
  weight: number;
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

// 模拟患者数据（作为备份）
export const mockPatients: Patient[] = [
  { id: '1', name: '张三', age: 45, gender: '男', diagnosis: '腰椎间盘突出', status: '在治疗' },
  { id: '2', name: '李四', age: 62, gender: '女', diagnosis: '膝关节炎', status: '已完成' },
  { id: '3', name: '王五', age: 38, gender: '男', diagnosis: '肩周炎', status: '在治疗' },
  { id: '4', name: '赵六', age: 55, gender: '女', diagnosis: '颈椎病', status: '随访中' },
  { id: '5', name: '钱七', age: 41, gender: '男', diagnosis: '腕管综合征', status: '已完成' },
];

// 模拟患者健康记录（作为备份）
export const mockHealthRecords: PatientHealthRecord[] = [
  {
    id: '1',
    name: '张三',
    age: 45,
    gender: '男',
    height: 175,
    weight: 72,
    bloodType: 'A',
    allergies: ['青霉素', '花粉'],
    emergencyContact: '李四 (妻子) - 13800138000',
    medicalHistory: [
      { date: '2022-03-15', diagnosis: '腰椎间盘突出', doctor: '王医生', hospital: '仁爱医院' },
      { date: '2021-07-22', diagnosis: '高血压', doctor: '李医生', hospital: '人民医院' },
      { date: '2020-11-05', diagnosis: '感冒', doctor: '赵医生', hospital: '社区医院' },
    ],
    rehabHistory: [
      { date: '2022-04-01', type: '理疗', details: '腰椎牵引', duration: '30分钟', frequency: '每周3次' },
      { date: '2022-04-15', type: '运动治疗', details: '核心肌群稳定训练', duration: '45分钟', frequency: '每周5次' },
      { date: '2022-05-10', type: '按摩治疗', details: '腰部肌肉放松', duration: '60分钟', frequency: '每周2次' },
    ],
    medications: [
      { name: '布洛芬', dosage: '200mg', frequency: '每日2次', startDate: '2022-03-20', endDate: '2022-04-20' },
      { name: '肌松剂', dosage: '10mg', frequency: '每晚1次', startDate: '2022-03-20', endDate: '长期' },
    ],
    vitalSigns: [
      { date: '2022-05-15', bp: '120/80', pulse: 72, temp: 36.5, respRate: 16, weight: 72 },
      { date: '2022-04-30', bp: '125/85', pulse: 75, temp: 36.7, respRate: 17, weight: 73 },
      { date: '2022-04-15', bp: '130/85', pulse: 78, temp: 36.6, respRate: 16, weight: 74 },
    ]
  }
]; 
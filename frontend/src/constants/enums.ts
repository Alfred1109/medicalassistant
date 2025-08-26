/**
 * 枚举常量定义
 * 集中定义系统中使用的枚举类型
 */

// 用户角色
export enum UserRole {
  ADMIN = 'admin',
  DOCTOR = 'doctor',
  HEALTH_MANAGER = 'healthManager',
  PATIENT = 'patient'
}

// 随访方式
export enum FollowUpMethod {
  PHONE = 'phone',
  MESSAGE = 'message',
  IN_PERSON = 'inperson',
  VIDEO = 'video',
  OTHER = 'other'
}

// 随访状态
export enum ReminderStatus {
  PENDING = 'pending',
  COMPLETED = 'completed',
  CANCELLED = 'cancelled',
  OVERDUE = 'overdue'
}

// 优先级
export enum Priority {
  LOW = 'low',
  MEDIUM = 'medium',
  HIGH = 'high'
}

// 健康指标单位
export enum HealthMetricUnit {
  BPM = 'bpm', // 心率单位
  MMHG = 'mmHg', // 血压单位
  PERCENT = '%', // 百分比
  MGDL = 'mg/dL', // 血糖单位
  STEPS = '步', // 步数
  KCAL = 'kcal', // 卡路里
  HOURS = '小时', // 小时
  MINUTES = '分钟', // 分钟
  CELCIUS = '°C', // 摄氏度
  KG = 'kg', // 公斤
  CM = 'cm' // 厘米
}

// 训练难度
export enum TrainingDifficulty {
  EASY = 'easy',
  MEDIUM = 'medium',
  HARD = 'hard'
}

// 时间范围，与ChartTypes中的保持一致
export enum TimeRange {
  DAY = '1d',
  WEEK = '7d',
  MONTH = '30d',
  QUARTER = '90d',
  YEAR = '1y',
  ALL = 'all',
  CUSTOM = 'custom'
}

// 导入数据源类型
export enum ImportSourceType {
  CSV_FILE = 'csv_file',
  EXCEL_FILE = 'excel_file',
  APPLE_HEALTH = 'apple_health',
  GOOGLE_FIT = 'google_fit',
  FITBIT = 'fitbit',
  WITHINGS = 'withings',
  GARMIN = 'garmin',
  CUSTOM_DEVICE = 'custom_device'
}

// 通知类型
export enum NotificationType {
  ALERT = 'alert',
  REMINDER = 'reminder',
  TASK = 'task',
  REHAB = 'rehab',
  MESSAGE = 'message'
} 
/**
 * 映射关系常量定义
 * 集中定义各种状态和显示文本的映射关系
 */
import { FollowUpMethod, ReminderStatus, TrainingDifficulty, UserRole } from './enums';

// 随访方式映射 - 仅保留标签文本
export const FOLLOW_UP_METHOD_LABELS = {
  [FollowUpMethod.PHONE]: '电话随访',
  [FollowUpMethod.MESSAGE]: '短信随访',
  [FollowUpMethod.IN_PERSON]: '面诊随访',
  [FollowUpMethod.VIDEO]: '视频随访',
  [FollowUpMethod.OTHER]: '其他方式'
};

// 随访状态映射
export const REMINDER_STATUS_MAP = {
  [ReminderStatus.PENDING]: { 
    label: '待执行', 
    color: 'primary' as const
  },
  [ReminderStatus.COMPLETED]: { 
    label: '已完成', 
    color: 'success' as const
  },
  [ReminderStatus.CANCELLED]: { 
    label: '已取消', 
    color: 'default' as const
  },
  [ReminderStatus.OVERDUE]: { 
    label: '已过期', 
    color: 'error' as const
  }
};

// 康复计划状态映射 - 不包含图标
export const REHAB_STATUS_MAP = {
  active: { 
    label: '进行中',
    color: 'primary' as const
  },
  completed: { 
    label: '已完成',
    color: 'success' as const
  },
  expired: { 
    label: '已过期',
    color: 'error' as const
  }
};

// 难度级别映射
export const DIFFICULTY_MAP = {
  [TrainingDifficulty.EASY]: { 
    label: '简单', 
    color: 'success' as const 
  },
  [TrainingDifficulty.MEDIUM]: { 
    label: '中等', 
    color: 'warning' as const 
  },
  [TrainingDifficulty.HARD]: { 
    label: '困难', 
    color: 'error' as const 
  }
};

// 用户角色显示名称
export const USER_ROLE_LABEL = {
  [UserRole.ADMIN]: '系统管理员',
  [UserRole.DOCTOR]: '医生',
  [UserRole.HEALTH_MANAGER]: '健康管理师',
  [UserRole.PATIENT]: '患者'
}; 
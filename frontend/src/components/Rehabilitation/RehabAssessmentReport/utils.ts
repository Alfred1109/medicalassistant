import { formatDate, formatDateTime, calculateElapsedDays, calculateRemainingDays } from '../../../utils/dateUtils';
import { formatPercentage, getObjectValue } from '../../../utils/commonUtils';
import { RehabPlan } from './index';

/**
 * 计算康复计划总体完成率
 * @param plan 康复计划对象
 * @returns 完成率百分比
 */
export const calculateCompletionRate = (plan: RehabPlan): number => {
  if (!plan.exercises || plan.exercises.length === 0) return 0;
  
  const completedExercises = plan.exercises.filter(ex => ex.completed).length;
  return Math.round((completedExercises / plan.exercises.length) * 100);
};

// 重新导出来自全局工具的函数，保持向后兼容
export { formatDate, formatDateTime, calculateElapsedDays, calculateRemainingDays, formatPercentage, getObjectValue }; 
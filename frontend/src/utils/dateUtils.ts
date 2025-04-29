import { format, differenceInDays, parseISO, isValid } from 'date-fns';
import { zhCN } from 'date-fns/locale';

/**
 * 日期格式化为中文格式（yyyy年MM月dd日）
 * @param dateString 日期字符串
 * @returns 格式化的日期字符串
 */
export const formatChineseDate = (dateString: string): string => {
  try {
    if (!dateString) return '--';
    const date = parseISO(dateString);
    if (!isValid(date)) return '--';
    return format(date, 'yyyy年MM月dd日', { locale: zhCN });
  } catch (e) {
    console.error("日期格式化错误:", e);
    return dateString || '--';
  }
};

/**
 * 格式化日期字符串为"YYYY-MM-DD"格式
 * @param dateString 日期字符串或Date对象
 * @returns 格式化后的日期字符串
 */
export const formatDate = (dateString: string | Date): string => {
  if (!dateString) return '--';
  
  try {
    const date = typeof dateString === 'string' ? new Date(dateString) : dateString;
    
    if (isNaN(date.getTime())) {
      return '--';
    }
    
    return date.toISOString().split('T')[0];
  } catch (error) {
    console.error('日期格式化错误:', error);
    return '--';
  }
};

/**
 * 格式化时间字符串为"YYYY-MM-DD HH:MM"格式
 * @param dateString 日期时间字符串或Date对象
 * @returns 格式化后的日期时间字符串
 */
export const formatDateTime = (dateString: string | Date): string => {
  if (!dateString) return '--';
  
  try {
    const date = typeof dateString === 'string' ? new Date(dateString) : dateString;
    
    if (isNaN(date.getTime())) {
      return '--';
    }
    
    const datepart = date.toISOString().split('T')[0];
    const timepart = date.toTimeString().split(' ')[0].substring(0, 5);
    
    return `${datepart} ${timepart}`;
  } catch (error) {
    console.error('日期时间格式化错误:', error);
    return '--';
  }
};

/**
 * 计算从某日期到今天的天数
 * @param startDate 开始日期
 * @returns 已经过去的天数
 */
export const calculateElapsedDays = (startDate: string): number => {
  try {
    if (!startDate) return 0;
    const start = parseISO(startDate);
    if (!isValid(start)) return 0;
    const today = new Date();
    return differenceInDays(today, start);
  } catch (e) {
    console.error("日期计算错误:", e);
    return 0;
  }
};

/**
 * 计算从今天到某日期的剩余天数
 * @param endDate 结束日期
 * @returns 剩余天数（如果是过去日期则返回0）
 */
export const calculateRemainingDays = (endDate?: string): number => {
  if (!endDate) return 0;
  
  try {
    const end = parseISO(endDate);
    if (!isValid(end)) return 0;
    const today = new Date();
    const days = differenceInDays(end, today);
    return days > 0 ? days : 0;
  } catch (e) {
    console.error("日期计算错误:", e);
    return 0;
  }
};

/**
 * 获取年龄
 * @param birthDateString 出生日期字符串
 * @returns 年龄
 */
export const calculateAge = (birthDateString: string): number => {
  try {
    if (!birthDateString) return 0;
    const birthDate = parseISO(birthDateString);
    if (!isValid(birthDate)) return 0;
    
    const today = new Date();
    let age = today.getFullYear() - birthDate.getFullYear();
    const m = today.getMonth() - birthDate.getMonth();
    
    if (m < 0 || (m === 0 && today.getDate() < birthDate.getDate())) {
      age--;
    }
    
    return age;
  } catch (e) {
    console.error("年龄计算错误:", e);
    return 0;
  }
}; 
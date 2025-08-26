/**
 * 格式化数值为百分比显示
 * @param value 小数值(0-1)
 * @param decimals 小数位数
 * @returns 格式化后的百分比字符串
 */
export const formatPercentage = (value: number, decimals = 1): string => {
  if (value === undefined || value === null || isNaN(value)) {
    return '--';
  }
  
  return `${(value * 100).toFixed(decimals)}%`;
};

/**
 * 安全访问对象属性，提供默认值
 * @param obj 要访问的对象
 * @param path 属性路径（点分隔符）
 * @param defaultValue 默认值
 * @returns 属性值或默认值
 */
export const getObjectValue = (obj: any, path: string, defaultValue = '--'): any => {
  if (!obj || !path) return defaultValue;
  
  try {
    const parts = path.split('.');
    let current = obj;
    
    for (const part of parts) {
      if (current === undefined || current === null) {
        return defaultValue;
      }
      current = current[part];
    }
    
    return current === undefined || current === null ? defaultValue : current;
  } catch (error) {
    console.error('属性访问错误:', error);
    return defaultValue;
  }
};

/**
 * 延迟执行函数
 * @param ms 延迟毫秒数
 * @returns Promise
 */
export const delay = (ms: number): Promise<void> => {
  return new Promise(resolve => setTimeout(resolve, ms));
};

/**
 * 处理错误并生成用户友好的错误消息
 * @param error 错误对象
 * @param defaultMessage 默认错误信息
 * @returns 用户友好的错误消息
 */
export const handleError = (error: any, defaultMessage = '操作失败，请稍后重试'): string => {
  console.error('Error:', error);
  
  if (error?.response?.data?.message) {
    return error.response.data.message;
  }
  
  if (error?.message) {
    return error.message;
  }
  
  return defaultMessage;
};

/**
 * 限制函数调用频率
 * @param func 需要限制的函数
 * @param wait 等待时间
 * @returns 限制频率后的函数
 */
export function debounce<T extends (...args: any[]) => any>(func: T, wait: number): (...args: Parameters<T>) => void {
  let timeout: ReturnType<typeof setTimeout> | null = null;
  
  return function(this: any, ...args: Parameters<T>) {
    const context = this;
    
    if (timeout) clearTimeout(timeout);
    
    timeout = setTimeout(() => {
      func.apply(context, args);
    }, wait);
  };
} 
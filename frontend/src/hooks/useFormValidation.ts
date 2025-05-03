/**
 * 通用表单验证钩子
 * 提供简单易用的表单验证功能
 */
import { useState, useCallback } from 'react';

// 验证规则定义
type ValidationRule<T> = {
  validator: (value: any, formData?: T) => boolean;
  message: string;
};

// 验证规则字典
type ValidationRules<T> = {
  [K in keyof T]?: ValidationRule<T>[];
};

// 错误信息字典
type ValidationErrors<T> = {
  [K in keyof T]?: string;
};

/**
 * 表单验证钩子
 * @param initialData 初始表单数据
 * @param validationRules 验证规则
 */
export const useFormValidation = <T extends Record<string, any>>(
  initialData: T,
  validationRules: ValidationRules<T>
) => {
  const [formData, setFormData] = useState<T>(initialData);
  const [formErrors, setFormErrors] = useState<ValidationErrors<T>>({});
  const [isValid, setIsValid] = useState<boolean>(true);

  // 验证单个字段
  const validateField = useCallback(
    (name: keyof T, value: any) => {
      const fieldRules = validationRules[name];
      if (!fieldRules) return '';

      for (const rule of fieldRules) {
        if (!rule.validator(value, formData)) {
          return rule.message;
        }
      }

      return '';
    },
    [formData, validationRules]
  );

  // 验证整个表单
  const validateForm = useCallback(() => {
    const errors: ValidationErrors<T> = {};
    let valid = true;

    Object.keys(validationRules).forEach((key) => {
      const name = key as keyof T;
      const error = validateField(name, formData[name]);
      if (error) {
        errors[name] = error;
        valid = false;
      }
    });

    setFormErrors(errors);
    setIsValid(valid);
    return valid;
  }, [formData, validateField, validationRules]);

  // 处理输入变化
  const handleChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => {
      const { name, value } = e.target;
      const key = name as keyof T;
      
      setFormData((prev) => ({ ...prev, [key]: value }));
      
      // 实时验证当前字段
      const error = validateField(key, value);
      setFormErrors((prev) => ({
        ...prev,
        [key]: error,
      }));
      
      // 检查整个表单是否有错误
      const hasNoErrors = Object.values({
        ...formErrors,
        [key]: error,
      }).every((err) => !err);
      
      setIsValid(hasNoErrors);
    },
    [formErrors, validateField]
  );

  // 处理数字输入
  const handleNumberInputChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const { name, value } = e.target;
      const key = name as keyof T;
      const numValue = value === '' ? '' : Number(value);

      setFormData((prev) => ({ ...prev, [key]: numValue }));
      
      // 实时验证当前字段
      const error = validateField(key, numValue);
      setFormErrors((prev) => ({
        ...prev,
        [key]: error,
      }));
      
      // 检查整个表单是否有错误
      const hasNoErrors = Object.values({
        ...formErrors,
        [key]: error,
      }).every((err) => !err);
      
      setIsValid(hasNoErrors);
    },
    [formErrors, validateField]
  );

  // 处理复选框变化
  const handleCheckboxChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const { name, checked } = e.target;
      const key = name as keyof T;
      
      setFormData((prev) => ({ ...prev, [key]: checked }));
      
      // 实时验证当前字段
      const error = validateField(key, checked);
      setFormErrors((prev) => ({
        ...prev,
        [key]: error,
      }));
      
      // 检查整个表单是否有错误
      const hasNoErrors = Object.values({
        ...formErrors,
        [key]: error,
      }).every((err) => !err);
      
      setIsValid(hasNoErrors);
    },
    [formErrors, validateField]
  );

  // 设置表单字段值
  const setFieldValue = useCallback(
    (name: keyof T, value: any) => {
      const key = name as keyof T;
      
      setFormData((prev) => ({ ...prev, [key]: value }));
      
      // 实时验证当前字段
      const error = validateField(key, value);
      setFormErrors((prev) => ({
        ...prev,
        [key]: error,
      }));
      
      // 检查整个表单是否有错误
      const hasNoErrors = Object.values({
        ...formErrors,
        [key]: error,
      }).every((err) => !err);
      
      setIsValid(hasNoErrors);
    },
    [formErrors, validateField]
  );

  // 重置表单
  const resetForm = useCallback(() => {
    setFormData(initialData);
    setFormErrors({});
    setIsValid(true);
  }, [initialData]);

  return {
    formData,
    formErrors,
    isValid,
    handleChange,
    handleNumberInputChange,
    handleCheckboxChange,
    setFieldValue,
    validateForm,
    resetForm,
    setFormData
  };
};

// 导出常用验证规则
export const ValidationRules = {
  required: (message = '此字段为必填项'): ValidationRule<any> => ({
    validator: (value) => {
      if (value === null || value === undefined) return false;
      if (typeof value === 'string') return value.trim() !== '';
      if (typeof value === 'number') return true;
      if (Array.isArray(value)) return value.length > 0;
      return !!value;
    },
    message,
  }),
  
  minLength: (min: number, message = `最小长度为 ${min} 个字符`): ValidationRule<any> => ({
    validator: (value) => {
      if (typeof value !== 'string') return false;
      return value.length >= min;
    },
    message,
  }),
  
  maxLength: (max: number, message = `最大长度为 ${max} 个字符`): ValidationRule<any> => ({
    validator: (value) => {
      if (typeof value !== 'string') return false;
      return value.length <= max;
    },
    message,
  }),
  
  email: (message = '请输入有效的电子邮箱地址'): ValidationRule<any> => ({
    validator: (value) => {
      if (!value) return true; // 允许为空，如果需要必填可以配合required规则
      const regex = /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/;
      return regex.test(value);
    },
    message,
  }),
  
  min: (min: number, message = `最小值为 ${min}`): ValidationRule<any> => ({
    validator: (value) => {
      if (value === null || value === undefined || value === '') return true;
      return Number(value) >= min;
    },
    message,
  }),
  
  max: (max: number, message = `最大值为 ${max}`): ValidationRule<any> => ({
    validator: (value) => {
      if (value === null || value === undefined || value === '') return true;
      return Number(value) <= max;
    },
    message,
  }),
  
  phone: (message = '请输入有效的手机号码'): ValidationRule<any> => ({
    validator: (value) => {
      if (!value) return true; // 允许为空
      const regex = /^1[3-9]\d{9}$/; // 中国大陆手机号验证
      return regex.test(value);
    },
    message,
  }),
  
  pattern: (regex: RegExp, message: string): ValidationRule<any> => ({
    validator: (value) => {
      if (!value) return true; // 允许为空
      return regex.test(value);
    },
    message,
  }),
  
  custom: <T>(
    validatorFn: (value: any, formData?: T) => boolean,
    message: string
  ): ValidationRule<T> => ({
    validator: validatorFn,
    message,
  }),
}; 
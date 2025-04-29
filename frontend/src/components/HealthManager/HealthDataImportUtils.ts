import { parse as parseCsv } from 'papaparse';
import * as XLSX from 'xlsx';
import { HealthDataRecord } from './HealthDataForm';

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

// 数据行接口（用于验证导入的数据）
export interface DataRow {
  [key: string]: any;
}

// 健康数据字段定义
export interface HealthDataField {
  key: string;
  label: string;
  required: boolean;
  type: 'string' | 'number' | 'date' | 'enum';
  options?: string[];
  description?: string;
}

// 字段映射接口
export interface FieldMapping {
  sourceField: string;
  targetField: string;
}

// 验证结果接口
export interface ValidationResult {
  valid: boolean;
  errors: { row: number; message: string }[];
}

// 支持的健康数据字段
export const healthDataFields: HealthDataField[] = [
  { key: 'data_type', label: '数据类型', required: true, type: 'enum', options: ['vital_signs', 'lab_results'] },
  { key: 'vital_type', label: '生命体征类型', required: false, type: 'enum', options: [
    'blood_pressure', 'heart_rate', 'blood_glucose', 'body_temperature', 
    'weight', 'height', 'oxygen_saturation', 'respiratory_rate', 'step_count'
  ]},
  { key: 'test_name', label: '检测名称', required: false, type: 'string' },
  { key: 'value', label: '数值', required: true, type: 'string' },
  { key: 'unit', label: '单位', required: false, type: 'string' },
  { key: 'measured_at', label: '测量时间', required: true, type: 'date' },
  { key: 'device', label: '设备', required: false, type: 'string' },
  { key: 'notes', label: '备注', required: false, type: 'string' },
  { key: 'tags', label: '标签', required: false, type: 'string' },
];

// 预设的字段映射模板
export const mappingTemplates = {
  // 苹果健康数据映射
  apple_health: {
    'type': 'data_type',
    'value': 'value',
    'unit': 'unit',
    'startDate': 'measured_at',
    'device': 'device',
    'sourceName': 'source',
  },
  // 谷歌健康数据映射
  google_fit: {
    'dataTypeName': 'data_type',
    'value': 'value',
    'unit': 'unit',
    'startTimeNanos': 'measured_at',
    'originDataSourceId': 'device',
  },
  // Fitbit数据映射
  fitbit: {
    'type': 'data_type',
    'value': 'value',
    'dateTime': 'measured_at',
    'source': 'device',
  }
};

/**
 * 解析CSV文件
 * @param file CSV文件对象
 * @returns 解析后的数据行数组和标题行
 */
export const parseCsvFile = (file: File): Promise<{ data: DataRow[], headers: string[] }> => {
  return new Promise((resolve, reject) => {
    parseCsv(file, {
      header: true,
      skipEmptyLines: true,
      complete: (results) => {
        const headers = results.meta.fields || [];
        resolve({ data: results.data as DataRow[], headers });
      },
      error: (error) => {
        reject(new Error(`解析CSV文件失败: ${error.message}`));
      }
    });
  });
};

/**
 * 解析Excel文件
 * @param file Excel文件对象
 * @returns 解析后的数据行数组和标题行
 */
export const parseExcelFile = (file: File): Promise<{ data: DataRow[], headers: string[] }> => {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    
    reader.onload = (event) => {
      try {
        const data = event.target?.result;
        if (!data) {
          throw new Error('无法读取文件数据');
        }
        
        const workbook = XLSX.read(data, { type: 'binary' });
        const firstSheetName = workbook.SheetNames[0];
        const worksheet = workbook.Sheets[firstSheetName];
        
        // 将Excel数据转换为JSON
        const jsonData = XLSX.utils.sheet_to_json(worksheet, { header: 1 });
        
        // 提取标题行
        const headers = jsonData[0] as string[];
        
        // 转换数据行
        const rows: DataRow[] = [];
        for (let i = 1; i < jsonData.length; i++) {
          const row: DataRow = {};
          const currentRow = jsonData[i] as any[];
          
          for (let j = 0; j < headers.length; j++) {
            row[headers[j]] = currentRow[j];
          }
          
          rows.push(row);
        }
        
        resolve({ data: rows, headers });
      } catch (error: any) {
        reject(new Error(`解析Excel文件失败: ${error.message}`));
      }
    };
    
    reader.onerror = () => {
      reject(new Error('读取文件时发生错误'));
    };
    
    reader.readAsBinaryString(file);
  });
};

/**
 * 根据文件类型解析文件
 * @param file 文件对象
 * @param sourceType 导入源类型
 * @returns 解析后的数据行数组和标题行
 */
export const parseFile = async (file: File, sourceType: ImportSourceType): Promise<{ data: DataRow[], headers: string[] }> => {
  if (sourceType === ImportSourceType.CSV_FILE) {
    return parseCsvFile(file);
  } else if (sourceType === ImportSourceType.EXCEL_FILE) {
    return parseExcelFile(file);
  } else {
    throw new Error('不支持的文件类型');
  }
};

/**
 * 验证导入数据
 * @param data 导入的数据行
 * @param mapping 字段映射
 * @returns 验证结果
 */
export const validateImportData = (data: DataRow[], mapping: FieldMapping[]): ValidationResult => {
  const errors: { row: number; message: string }[] = [];
  
  // 获取所有必填字段
  const requiredFields = healthDataFields
    .filter((field) => field.required)
    .map((field) => field.key);
  
  // 获取映射中的目标字段
  const mappedTargetFields = mapping.map((item) => item.targetField);
  
  // 检查所有必填字段是否都在映射中
  const missingRequiredFields = requiredFields.filter(
    (field) => !mappedTargetFields.includes(field)
  );
  
  if (missingRequiredFields.length > 0) {
    return {
      valid: false,
      errors: [
        {
          row: 0,
          message: `缺少必填字段映射: ${missingRequiredFields.join(', ')}`
        }
      ]
    };
  }
  
  // 验证每一行数据
  data.forEach((row, index) => {
    // 检查每个映射的字段
    mapping.forEach((map) => {
      const { sourceField, targetField } = map;
      const value = row[sourceField];
      
      // 找到对应的字段定义
      const fieldDef = healthDataFields.find((f) => f.key === targetField);
      
      if (!fieldDef) {
        return; // 跳过未知字段
      }
      
      // 检查必填字段是否有值
      if (fieldDef.required && (value === undefined || value === null || value === '')) {
        errors.push({
          row: index + 1,
          message: `第 ${index + 1} 行: ${fieldDef.label} 不能为空`
        });
      }
      
      // 检查类型
      if (value !== undefined && value !== null && value !== '') {
        // 检查数字类型
        if (fieldDef.type === 'number' && isNaN(Number(value))) {
          errors.push({
            row: index + 1,
            message: `第 ${index + 1} 行: ${fieldDef.label} 必须是数字`
          });
        }
        
        // 检查日期类型
        if (fieldDef.type === 'date' && isNaN(Date.parse(String(value)))) {
          errors.push({
            row: index + 1,
            message: `第 ${index + 1} 行: ${fieldDef.label} 必须是有效的日期格式`
          });
        }
        
        // 检查枚举类型
        if (fieldDef.type === 'enum' && fieldDef.options && !fieldDef.options.includes(String(value))) {
          errors.push({
            row: index + 1,
            message: `第 ${index + 1} 行: ${fieldDef.label} 必须是以下值之一: ${fieldDef.options.join(', ')}`
          });
        }
      }
    });
  });
  
  return {
    valid: errors.length === 0,
    errors
  };
};

/**
 * 根据映射将导入数据转换为健康数据记录
 * @param data 导入的数据行
 * @param mapping 字段映射
 * @param patientId 患者ID
 * @returns 健康数据记录数组
 */
export const convertToHealthData = (
  data: DataRow[],
  mapping: FieldMapping[],
  patientId: string
): HealthDataRecord[] => {
  return data.map((row) => {
    const healthData: Partial<HealthDataRecord> = {
      patient_id: patientId
    };
    
    // 根据映射填充字段
    mapping.forEach((map) => {
      const { sourceField, targetField } = map;
      const value = row[sourceField];
      
      // 特殊处理某些字段
      if (targetField === 'tags' && typeof value === 'string') {
        // 将标签字符串分割为数组
        healthData[targetField] = value.split(',').map((tag) => tag.trim());
      } else if (targetField === 'measured_at' && value) {
        // 确保日期格式正确
        healthData[targetField] = new Date(value);
      } else {
        // 其他字段直接赋值
        healthData[targetField] = value;
      }
    });
    
    // 处理血压特殊情况
    if (
      healthData.data_type === 'vital_signs' && 
      healthData.vital_type === 'blood_pressure' &&
      typeof healthData.value === 'string'
    ) {
      const bpMatch = healthData.value.match(/(\d+)\/(\d+)/);
      if (bpMatch) {
        const systolic = parseInt(bpMatch[1], 10);
        const diastolic = parseInt(bpMatch[2], 10);
        
        healthData.additional_info = {
          ...healthData.additional_info,
          systolic,
          diastolic
        };
      }
    }
    
    return healthData as HealthDataRecord;
  });
};

/**
 * 自动生成字段映射，尝试匹配标题行与健康数据字段
 * @param headers 标题行
 * @returns 自动生成的字段映射
 */
export const generateAutoMapping = (headers: string[]): FieldMapping[] => {
  const mapping: FieldMapping[] = [];
  
  // 尝试进行精确匹配
  headers.forEach((header) => {
    // 尝试查找精确匹配的字段
    const exactField = healthDataFields.find((field) => 
      field.key.toLowerCase() === header.toLowerCase() || 
      field.label.toLowerCase() === header.toLowerCase()
    );
    
    if (exactField) {
      mapping.push({
        sourceField: header,
        targetField: exactField.key
      });
      return;
    }
    
    // 尝试进行模糊匹配
    const fuzzyField = healthDataFields.find((field) => 
      header.toLowerCase().includes(field.key.toLowerCase()) || 
      field.key.toLowerCase().includes(header.toLowerCase()) ||
      header.toLowerCase().includes(field.label.toLowerCase()) || 
      field.label.toLowerCase().includes(header.toLowerCase())
    );
    
    if (fuzzyField) {
      mapping.push({
        sourceField: header,
        targetField: fuzzyField.key
      });
    }
  });
  
  return mapping;
};

/**
 * 获取预设映射模板
 * @param sourceType 导入源类型
 * @returns 预设的字段映射
 */
export const getPresetMapping = (sourceType: ImportSourceType): Record<string, string> | null => {
  switch (sourceType) {
    case ImportSourceType.APPLE_HEALTH:
      return mappingTemplates.apple_health;
    case ImportSourceType.GOOGLE_FIT:
      return mappingTemplates.google_fit;
    case ImportSourceType.FITBIT:
      return mappingTemplates.fitbit;
    default:
      return null;
  }
};

/**
 * 从外部设备获取健康数据
 * @param sourceType 设备类型
 * @param params 其他参数
 * @returns 获取的健康数据和标题
 */
export const fetchFromDevice = async (
  sourceType: ImportSourceType,
  params: any
): Promise<{ data: DataRow[], headers: string[] }> => {
  // 这里只是一个示例，实际上需要实现与各种设备API的集成
  // 返回示例数据
  return new Promise((resolve, reject) => {
    // 模拟API调用延迟
    setTimeout(() => {
      try {
        let data: DataRow[] = [];
        let headers: string[] = [];
        
        // 根据设备类型返回不同的示例数据
        switch (sourceType) {
          case ImportSourceType.APPLE_HEALTH:
            headers = ['type', 'value', 'unit', 'startDate', 'endDate', 'device', 'sourceName'];
            data = [
              { type: 'HKQuantityTypeIdentifierHeartRate', value: '72', unit: 'count/min', startDate: '2023-05-10T08:30:00', endDate: '2023-05-10T08:30:10', device: 'Apple Watch Series 7', sourceName: 'Health' },
              { type: 'HKQuantityTypeIdentifierBloodPressureSystolic', value: '120', unit: 'mmHg', startDate: '2023-05-10T09:15:00', endDate: '2023-05-10T09:15:10', device: 'Blood Pressure Monitor', sourceName: 'Health' },
              { type: 'HKQuantityTypeIdentifierBloodPressureDiastolic', value: '80', unit: 'mmHg', startDate: '2023-05-10T09:15:00', endDate: '2023-05-10T09:15:10', device: 'Blood Pressure Monitor', sourceName: 'Health' }
            ];
            break;
            
          case ImportSourceType.GOOGLE_FIT:
            headers = ['dataTypeName', 'value', 'unit', 'startTimeNanos', 'endTimeNanos', 'originDataSourceId'];
            data = [
              { dataTypeName: 'com.google.heart_rate.bpm', value: '68', unit: 'bpm', startTimeNanos: '1683698400000000000', endTimeNanos: '1683698410000000000', originDataSourceId: 'derived:com.google.heart_rate.bpm:com.google.android.gms:merge_heart_rate_bpm' },
              { dataTypeName: 'com.google.weight.kg', value: '70.5', unit: 'kg', startTimeNanos: '1683694800000000000', endTimeNanos: '1683694810000000000', originDataSourceId: 'derived:com.google.weight:com.google.android.gms:merge_weight' }
            ];
            break;
            
          case ImportSourceType.FITBIT:
            headers = ['type', 'value', 'dateTime', 'source'];
            data = [
              { type: 'heart_rate', value: '70', dateTime: '2023-05-10T10:30:00', source: 'Fitbit Charge 5' },
              { type: 'steps', value: '8500', dateTime: '2023-05-10', source: 'Fitbit Charge 5' },
              { type: 'calories', value: '2100', dateTime: '2023-05-10', source: 'Fitbit Charge 5' }
            ];
            break;
            
          default:
            reject(new Error('不支持的设备类型'));
            return;
        }
        
        resolve({ data, headers });
      } catch (error: any) {
        reject(new Error(`获取设备数据失败: ${error.message}`));
      }
    }, 1000);
  });
}; 
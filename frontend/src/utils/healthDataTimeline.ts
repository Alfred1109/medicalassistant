import { healthDataPayload, healthDataType, healthDataQualityFlags, type HealthDataFact } from './healthDataFacts';

// 健康数据时间线项目类型
export interface HealthDataTimelineItem {
  id: string;
  data_type: string;
  title: string;
  description: string;
  value: string | number;
  unit: string;
  timestamp: string;
  metadata?: {
    device?: string;
    location?: string;
    notes?: string;
    tags?: string[];
    alert_status?: string;
    alert_level?: string;
    [key: string]: any;
  };
}

// 数据类型映射
export const dataTypeLabelMap: Record<string, string> = {
  blood_pressure: '血压测量',
  blood_pressure_systolic: '收缩压（独立分量）',
  blood_pressure_diastolic: '舒张压（独立分量）',
  blood_glucose: '血糖检测',
  heart_rate: '心率监测',
  body_temperature: '体温记录',
  weight: '体重记录',
  height: '身高测量',
  sleep: '睡眠记录',
  step_count: '步数统计',
  blood_oxygen: '血氧监测',
  oxygen_saturation: '血氧监测',
  respiratory_rate: '呼吸频率'
};

// 数据类型默认单位
export const getUnitByDataType = (dataType: string): string => {
  const unitMap: Record<string, string> = {
    blood_pressure: 'mmHg',
    blood_pressure_systolic: 'mmHg',
    blood_pressure_diastolic: 'mmHg',
    blood_glucose: 'mmol/L',
    heart_rate: 'bpm',
    body_temperature: '°C',
    weight: 'kg',
    height: 'cm',
    oxygen_saturation: '%',
    blood_oxygen: '%',
    respiratory_rate: '次/分',
    step_count: '步',
  };
  return unitMap[dataType] || '';
};

// 获取显示值（血压支持 {systolic, diastolic} 结构）
export const getDisplayValue = (data: HealthDataFact): string | number => {
  const payload = healthDataPayload(data);
  const value = data.data_type === 'lab_result' ? payload.result_value ?? payload.value : payload.value;
  if (value && typeof value === 'object') {
    const bp = value as { systolic?: number; diastolic?: number };
    if (bp.systolic != null && bp.diastolic != null) {
      return `${bp.systolic}/${bp.diastolic}`;
    }
    return JSON.stringify(value);
  }
  return value != null ? (value as string | number) : '-';
};

// 转换健康数据到时间线项目
export const convertHealthDataToTimelineItems = (healthData: HealthDataFact[]): HealthDataTimelineItem[] => {
  return healthData.map(item => {
    const semanticType = healthDataType(item);
    const payload = healthDataPayload(item);
    const qualityFlags = healthDataQualityFlags(item);
    const baseTitle = dataTypeLabelMap[semanticType] || dataTypeLabelMap[item.data_type] || `${item.data_type}记录`;

    // 如果有预警信息，添加预警标记
    let title = baseTitle;
    if (item.alert_level === 'warning') {
      title = `⚠️ ${title} (警告)`;
    } else if (item.alert_level === 'critical') {
      title = `🚨 ${title} (严重)`;
    }

    // 描述：预警信息 + 备注
    let description = '';
    if (item.alert_level) {
      const alertMsg = item.alert_level === 'warning' ? '警告: 数值超出正常范围' : '严重: 数值大幅偏离正常范围';
      description += alertMsg;
      if (item.alert_message) {
        description += ` - ${item.alert_message}`;
      }
      description += '\n';
    }
    if (qualityFlags.length) {
      title = `质量待核查：${title}`;
      description += `质量标记：${qualityFlags.join('、')}（不代表临床诊断）\n`;
    }
    if (payload.notes) description += payload.notes;

    return {
      id: String(item.id ?? item._id ?? ''),
      data_type: item.data_type,
      title,
      description,
      value: getDisplayValue(item),
      unit: payload.unit || getUnitByDataType(semanticType),
      timestamp: item.recorded_at || '',
      metadata: {
        ...item.metadata,
        quality_flags: qualityFlags,
        notes: payload.notes,
        source: item.source,
        alert_status: item.alert_status,
        alert_level: item.alert_level
      }
    };
  });
};

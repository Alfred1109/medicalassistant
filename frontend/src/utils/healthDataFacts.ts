/** HealthDataResponse uses data_content; old in-memory consumers also use data. */
export interface HealthDataFact {
  id?: string;
  _id?: string;
  data_type: string;
  data_content?: Record<string, any>;
  data?: Record<string, any>;
  recorded_at?: string;
  created_at?: string;
  metadata?: Record<string, any>;
  [key: string]: any;
}

const aliases: Record<string, string> = {
  pulse: 'heart_rate', spo2: 'oxygen_saturation', blood_oxygen: 'oxygen_saturation',
  respiration_rate: 'respiratory_rate', systolic_pressure: 'blood_pressure_systolic',
  diastolic_pressure: 'blood_pressure_diastolic',
};

export function healthDataPayload(row: HealthDataFact): Record<string, any> {
  const value = row.data_content ?? row.data;
  return value && typeof value === 'object' && !Array.isArray(value) ? value : {};
}

export function healthDataVitalDisplay(row: HealthDataFact) {
  const data = healthDataPayload(row);
  return {
    type: healthDataType(row),
    value: data.value,
    unit: typeof data.unit === 'string' ? data.unit : '',
  };
}

export function healthDataLabDisplay(row: HealthDataFact) {
  const data = healthDataPayload(row);
  return {
    testName: typeof data.test_name === 'string' ? data.test_name : '',
    value: data.result_value,
    unit: typeof data.unit === 'string' ? data.unit : '',
    reference: typeof data.reference_range === 'string' ? data.reference_range : undefined,
    interpretation: typeof data.interpretation === 'string' ? data.interpretation : undefined,
  };
}

export function healthDataType(row: HealthDataFact): string {
  const data = healthDataPayload(row);
  const type = row.data_type === 'vital_sign' ? (typeof data.type === 'string' && data.type ? data.type : data.vital_type)
    : row.data_type === 'lab_result' ? data.test_name : data.type ?? row.data_type;
  return typeof type === 'string' && type ? aliases[type] ?? type : '';
}

export function healthDataQualityFlags(row: HealthDataFact): string[] {
  const flags = row.metadata?.quality_flags;
  if (flags == null) return [];
  if (!Array.isArray(flags)) return ['无法识别的质量标记'];
  return flags.map(flag => typeof flag === 'string' && flag ? flag : '无法识别的质量标记');
}

export function healthDataNumber(value: unknown): number | null {
  if (typeof value !== 'number' && typeof value !== 'string') return null;
  if (typeof value === 'string' && !value.trim()) return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

export function healthDataValueText(value: unknown): string {
  if (value == null || value === '') return '-';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

export interface HealthObservation {
  id: string;
  type: string;
  timestamp: string;
  value: number | null;
  rawValue: unknown;
  unit: string;
  qualityFlags: string[];
}

export function healthDataTimestamp(value: string): number {
  return new Date(/(?:Z|[+-]\d{2}:?\d{2})$/i.test(value) ? value : `${value}Z`).getTime();
}

export function isTrendObservation(point: HealthObservation): boolean {
  return point.value !== null && point.qualityFlags.length === 0 && Number.isFinite(healthDataTimestamp(point.timestamp));
}

/** Composite historical BP documents may be split; distinct readings are never paired. */
export function healthObservations(rows: HealthDataFact[], dataType = 'vital_sign'): HealthObservation[] {
  return rows.filter(row => row.data_type === dataType).flatMap((row, index) => {
    const data = healthDataPayload(row);
    const type = healthDataType(row);
    if (!type) return [];
    const value = row.data_type === 'lab_result' ? data.result_value ?? data.value : data.value;
    const base = { id: String(row.id ?? row._id ?? index), timestamp: row.recorded_at ?? row.created_at ?? '',
      unit: typeof data.unit === 'string' ? data.unit : '', qualityFlags: healthDataQualityFlags(row) };
    const observation = (metric: string, rawValue: unknown) => ({ ...base, type: metric,
      value: healthDataNumber(rawValue), rawValue });
    if (type === 'blood_pressure') {
      const parts = typeof value === 'string' ? value.split('/') : null;
      const bloodPressure = value && typeof value === 'object' ? value :
        parts?.length === 2 ? { systolic: parts[0], diastolic: parts[1] } : null;
      if (bloodPressure) return [
        observation('blood_pressure_systolic', bloodPressure.systolic),
        observation('blood_pressure_diastolic', bloodPressure.diastolic),
      ].filter(point => point.rawValue != null);
    }
    return [observation(type, value)];
  });
}

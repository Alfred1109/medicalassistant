import React, { useState, useEffect } from 'react';
import {
  Box,
  Typography,
  Paper,
  Grid,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Divider,
  Tabs,
  Tab,
  Card,
  CardContent,
  Stack,
  Chip,
  Alert,
  CircularProgress,
  SelectChangeEvent,
} from '@mui/material';
import { format } from 'date-fns';
import { zhCN } from 'date-fns/locale';

// 导入组件
import HealthDataVisualization from '../../components/HealthManager/HealthDataVisualization';
import HealthDataForm from '../../components/HealthManager/HealthDataForm';
import type { HealthDataRecord as HealthDataFormRecord } from '../../components/HealthManager/HealthDataForm';
import api from '../../services/httpClient';

// 后端患者行形状（GET /api/doctors/patients / GET /api/health-managers/patients，
// 字段见 backend/app/db/crud_services.py 的 _get_patient_data）
interface BackendPatientRow {
  id: string;
  name: string;
  age: number;
  gender: string;
  diagnosis?: string | null;
  status?: string | null;
}

// 后端健康数据行形状（GET /api/health-records/health-data，
// 见 backend/app/api/routers/health_record_router.py 的 list_health_data）
interface BackendHealthDataRow {
  id: string;
  patient_id: string;
  data_type: string; // vital_sign / lab_result / ...
  data: {
    type?: string; // vital_sign：生命体征类型（blood_pressure、heart_rate、body_temperature...）
    value?: number | string | Record<string, number>;
    unit?: string | null;
    notes?: string | null;
    [key: string]: unknown;
  };
  recorded_by?: string | null;
  recorded_at: string;
}

// 页面内部使用的健康数据记录（由后端行归一化而来）
interface HealthDataRecord {
  id: string;
  patient_id: string;
  data_type: string; // vital_sign / lab_result
  vital_type?: string;
  value?: number | string | Record<string, number>;
  unit?: string;
  measured_at: string;
  created_by?: string;
  notes?: string;
  // 与 HealthDataVisualization 的 HealthDataPoint 形状保持兼容
  data: unknown;
  recorded_at: string;
  // lab_result 专用字段
  test_name?: string;
  result_value?: string | Record<string, unknown>;
  reference_range?: string;
  interpretation?: string;
}

// 患者选择器数据（由后端患者行归一化而来）
interface PatientOption {
  id: string;
  name: string;
  age: number;
  gender: string;
}

// 生命体征类型 → 展示名
const vitalTypeNames: Record<string, string> = {
  blood_pressure: '血压',
  heart_rate: '心率',
  blood_glucose: '血糖',
  blood_sugar: '血糖',
  body_temperature: '体温',
  temperature: '体温',
  respiratory_rate: '呼吸频率',
  blood_oxygen: '血氧',
  weight: '体重'
};

// 后端生命体征类型 → 展示名（未覆盖的类型原样展示类型键，不隐藏）
const formatVitalDisplayName = (vitalType: string): string =>
  vitalTypeNames[vitalType] ?? vitalType;

// 生命体征值展示：血压为 {systolic, diastolic} 对象，其余为标量
const formatVitalValue = (record: HealthDataRecord): string => {
  const { value, unit } = record;
  if (value !== null && typeof value === 'object') {
    if ('systolic' in value && 'diastolic' in value) {
      return `${value.systolic}/${value.diastolic}${unit ? ` ${unit}` : ''}`;
    }
    return Object.entries(value)
      .map(([key, val]) => `${key}: ${String(val)}`)
      .join('，');
  }
  return `${value ?? '--'}${unit ? ` ${unit}` : ''}`;
};

// 将后端健康数据行归一化为页面内部记录
const mapBackendHealthDataRow = (row: BackendHealthDataRow): HealthDataRecord => {
  const base: HealthDataRecord = {
    id: row.id,
    patient_id: row.patient_id,
    data_type: row.data_type,
    measured_at: row.recorded_at,
    // 兼容 HealthDataVisualization 的 HealthDataPoint 形状
    data: row.data,
    recorded_at: row.recorded_at,
    created_by: row.recorded_by ?? undefined,
    notes: row.data?.notes ?? undefined
  };

  if (row.data_type === 'vital_sign') {
    return {
      ...base,
      vital_type: String(row.data?.type ?? ''),
      value: row.data?.value,
      unit: row.data?.unit ?? undefined
    };
  }

  if (row.data_type === 'lab_result') {
    return {
      ...base,
      test_name: row.data?.test_name !== undefined ? String(row.data.test_name) : undefined,
      result_value: row.data?.result_value as string | Record<string, unknown> | undefined,
      reference_range:
        row.data?.reference_range !== undefined ? String(row.data.reference_range) : undefined,
      interpretation:
        row.data?.interpretation !== undefined ? String(row.data.interpretation) : undefined
    };
  }

  return base;
};

// 将后端患者行归一化为患者选择器数据
const mapBackendPatientRow = (row: BackendPatientRow): PatientOption => ({
  id: String(row?.id ?? ''),
  name: String(row?.name ?? '未知患者'),
  age: Number(row?.age ?? 0),
  gender: String(row?.gender ?? '未知')
});

interface TabPanelProps {
  children?: React.ReactNode;
  index: number;
  value: number;
}

function TabPanel(props: TabPanelProps) {
  const { children, value, index, ...other } = props;

  return (
    <div
      role="tabpanel"
      hidden={value !== index}
      id={`data-monitoring-tabpanel-${index}`}
      aria-labelledby={`data-monitoring-tab-${index}`}
      {...other}
    >
      {value === index && <Box sx={{ pt: 3 }}>{children}</Box>}
    </div>
  );
}

const DataMonitoring: React.FC = () => {
  const [selectedPatient, setSelectedPatient] = useState<string>('');
  const [patients, setPatients] = useState<PatientOption[]>([]);
  const [patientsLoading, setPatientsLoading] = useState<boolean>(false);
  const [healthData, setHealthData] = useState<HealthDataRecord[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [tabValue, setTabValue] = useState<number>(0);
  const [showForm, setShowForm] = useState<boolean>(false);

  // 加载患者列表（真实端点，按当前登录角色选择）
  useEffect(() => {
    const loadPatients = async () => {
      try {
        setPatientsLoading(true);

        // 后端患者列表按角色分端点：医生 GET /api/doctors/patients、
        // 健康管理师 GET /api/health-managers/patients（均校验角色，见对应 router）
        const userResponse = await api.get('users/me');
        const role = String(userResponse.data?.role ?? '');
        const listUrl =
          role === 'doctor'
            ? 'doctors/patients'
            : role === 'health_manager'
              ? 'health-managers/patients'
              : null;

        if (!listUrl) {
          setError('当前角色没有可用的患者列表数据源');
          return;
        }

        const response = await api.get<BackendPatientRow[]>(listUrl);
        // 后端直接返回数组；兼容可能的 {status, data} 包装
        const payload = response.data as BackendPatientRow[] | { data?: BackendPatientRow[] };
        const rows: BackendPatientRow[] = Array.isArray(payload) ? payload : (payload.data ?? []);

        setPatients(rows.map(mapBackendPatientRow));
        setError(null);
      } catch (err) {
        setError('加载患者列表失败');
        console.error(err);
      } finally {
        setPatientsLoading(false);
      }
    };

    loadPatients();
  }, []);

  // 加载患者健康数据
  useEffect(() => {
    if (selectedPatient) {
      loadHealthData(selectedPatient);
    }
  }, [selectedPatient]);

  // 处理选择患者
  const handlePatientChange = (event: SelectChangeEvent<string>) => {
    setSelectedPatient(event.target.value as string);
  };

  // 加载健康数据（真实端点：GET /api/health-records/health-data，patient_id 必填）
  const loadHealthData = async (patientId: string) => {
    try {
      setLoading(true);

      const response = await api.get<BackendHealthDataRow[]>('health-records/health-data', {
        params: { patient_id: patientId }
      });
      // 后端直接返回数组；兼容可能的 {status, data} 包装
      const payload = response.data as BackendHealthDataRow[] | { data?: BackendHealthDataRow[] };
      const rows: BackendHealthDataRow[] = Array.isArray(payload) ? payload : (payload.data ?? []);

      setHealthData(rows.map(mapBackendHealthDataRow));
      setError(null);
    } catch (err) {
      setError('加载健康数据失败');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };
  
  // 处理标签页变更
  const handleTabChange = (event: React.SyntheticEvent, newValue: number) => {
    setTabValue(newValue);
  };
  
  // 处理添加健康数据
  const handleAddHealthData = () => {
    setShowForm(true);
  };
  
  // 处理健康数据提交（真实端点：POST /api/health-records/health-data，
  // 请求体为 HealthDataCreate：{ patient_id, data_type, data_content, ... }）
  const handleHealthDataSubmit = async (data: HealthDataFormRecord) => {
    try {
      setLoading(true);

      // 表单 data_type 即后端生命体征 vital_type（blood_pressure/heart_rate/...）；
      // 血压的收缩/舒张压存于 additional_info，作为对象值提交；
      // mood/pain/custom 等非生命体征类型后端暂无专用语义，暂以通用健康数据存储
      const isBloodPressure = data.data_type === 'blood_pressure';
      const value = isBloodPressure
        ? {
            systolic: Number(data.additional_info?.systolic ?? 0),
            diastolic: Number(data.additional_info?.diastolic ?? 0)
          }
        : data.value;

      await api.post('health-records/health-data', {
        patient_id: selectedPatient,
        data_type: 'vital_sign',
        data_content: {
          type: data.data_type,
          value,
          unit: data.unit || null,
          notes: data.notes || null
        },
        source: 'manual',
        recorded_at:
          typeof data.measured_at === 'string'
            ? data.measured_at
            : format(data.measured_at, "yyyy-MM-dd'T'HH:mm:ss")
      });

      setShowForm(false);
      // 提交后从后端重新拉取，保证展示与真实数据源一致（不做本地乐观插入）
      await loadHealthData(selectedPatient);
    } catch (err) {
      setError('保存健康数据失败');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };
  
  // 获取选中患者信息
  const selectedPatientInfo = selectedPatient ?
    patients.find(p => p.id === selectedPatient) ?? null : null;

  // 过滤出不同类型的健康数据
  const vitalSigns = healthData.filter(data => data.data_type === 'vital_sign');
  const labResults = healthData.filter(data => data.data_type === 'lab_result');

  // 最新的生命体征数据（按 vital_type 分组取最新一条）
  const latestVitalSigns: Record<string, HealthDataRecord> = {};
  vitalSigns.forEach(data => {
    const type = data.vital_type ?? '';
    if (!latestVitalSigns[type] || new Date(data.measured_at) > new Date(latestVitalSigns[type].measured_at)) {
      latestVitalSigns[type] = data;
    }
  });
  
  return (
    <Box>
      <Typography variant="h5" gutterBottom>
        健康数据监测
      </Typography>
      <Typography variant="body2" color="text.secondary" paragraph>
        监测和分析患者的健康数据，包括生命体征和实验室检查结果。
      </Typography>
      <Divider sx={{ mb: 3 }} />
      
      <Paper sx={{ mb: 3, p: 2 }}>
        <Grid container spacing={2} alignItems="center">
          <Grid item xs={12} md={6}>
            <FormControl fullWidth>
              <InputLabel id="patient-select-label">选择患者</InputLabel>
              <Select
                labelId="patient-select-label"
                id="patient-select"
                value={selectedPatient}
                onChange={handlePatientChange}
                label="选择患者"
              >
                {patients.map(patient => (
                  <MenuItem key={patient.id} value={patient.id}>
                    {patient.name} ({patient.gender}, {patient.age}岁)
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          </Grid>
        </Grid>
      </Paper>

      {!patientsLoading && !error && patients.length === 0 && (
        <Alert severity="info" sx={{ mt: 2 }}>
          暂无患者数据：当前角色名下没有关联患者（后端患者列表为空）
        </Alert>
      )}

      {!selectedPatient && patients.length > 0 && (
        <Alert severity="info" sx={{ mt: 2 }}>请选择一名患者查看健康数据</Alert>
      )}
      
      {loading && (
        <Box sx={{ display: 'flex', justifyContent: 'center', mt: 4 }}>
          <CircularProgress />
        </Box>
      )}
      
      {error && (
        <Alert severity="error" sx={{ mt: 2 }}>{error}</Alert>
      )}
      
      {selectedPatient && !loading && !error && (
        <>
          {/* 患者基本信息卡片 */}
          {selectedPatientInfo && (
            <Paper sx={{ mb: 3, p: 2 }}>
              <Typography variant="h6" gutterBottom>
                患者信息
              </Typography>
              <Grid container spacing={2}>
                <Grid item xs={12} sm={4}>
                  <Typography variant="body2" color="text.secondary">
                    姓名
                  </Typography>
                  <Typography variant="body1">
                    {selectedPatientInfo.name}
                  </Typography>
                </Grid>
                <Grid item xs={12} sm={4}>
                  <Typography variant="body2" color="text.secondary">
                    性别
                  </Typography>
                  <Typography variant="body1">
                    {selectedPatientInfo.gender}
                  </Typography>
                </Grid>
                <Grid item xs={12} sm={4}>
                  <Typography variant="body2" color="text.secondary">
                    年龄
                  </Typography>
                  <Typography variant="body1">
                    {selectedPatientInfo.age}岁
                  </Typography>
                </Grid>
              </Grid>
            </Paper>
          )}
          
          {/* 最新生命体征卡片 */}
          {Object.keys(latestVitalSigns).length > 0 && (
            <Paper sx={{ mb: 3, p: 2 }}>
              <Typography variant="h6" gutterBottom>
                最新生命体征
              </Typography>
              <Grid container spacing={2}>
                {Object.entries(latestVitalSigns).map(([type, data]) => {
                  const displayName = formatVitalDisplayName(type);
                  const displayValue = formatVitalValue(data);

                  return (
                    <Grid item xs={6} sm={4} md={3} key={type}>
                      <Card variant="outlined">
                        <CardContent>
                          <Typography variant="body2" color="text.secondary" gutterBottom>
                            {displayName}
                          </Typography>
                          <Typography variant="h6">
                            {displayValue}
                          </Typography>
                          <Typography variant="caption" color="text.secondary">
                            {format(new Date(data.measured_at), 'yyyy-MM-dd HH:mm', { locale: zhCN })}
                          </Typography>
                        </CardContent>
                      </Card>
                    </Grid>
                  );
                })}
              </Grid>
            </Paper>
          )}
          
          <Box sx={{ borderBottom: 1, borderColor: 'divider' }}>
            <Tabs 
              value={tabValue} 
              onChange={handleTabChange} 
              aria-label="health data tabs"
            >
              <Tab label="数据可视化" />
              <Tab label="数据记录" />
              <Tab label="添加数据" />
            </Tabs>
          </Box>
          
          <TabPanel value={tabValue} index={0}>
            <HealthDataVisualization 
              data={healthData}
              loading={false}
              error={undefined}
              height={400}
            />
          </TabPanel>
          
          <TabPanel value={tabValue} index={1}>
            <Typography variant="h6" gutterBottom>
              生命体征记录
            </Typography>
            <Paper variant="outlined" sx={{ mb: 3 }}>
              {vitalSigns.length === 0 ? (
                <Box sx={{ p: 2 }}>
                  <Typography>暂无生命体征记录</Typography>
                </Box>
              ) : (
                <Box sx={{ maxHeight: '400px', overflow: 'auto' }}>
                  {vitalSigns.map((data, index) => {
                    const displayName = formatVitalDisplayName(data.vital_type ?? '');
                    const displayValue = formatVitalValue(data);

                    return (
                      <React.Fragment key={data.id}>
                        <Box sx={{ p: 2 }}>
                          <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }}>
                            <Chip 
                              label={displayName} 
                              color="primary" 
                              size="small" 
                              variant="outlined" 
                            />
                            <Typography variant="caption" color="text.secondary">
                              {format(new Date(data.measured_at), 'yyyy-MM-dd HH:mm', { locale: zhCN })}
                            </Typography>
                          </Stack>
                          <Typography variant="h6">
                            {displayValue}
                          </Typography>
                          {data.notes && (
                            <Typography variant="body2" color="text.secondary">
                              备注: {data.notes}
                            </Typography>
                          )}
                        </Box>
                        {index < vitalSigns.length - 1 && <Divider />}
                      </React.Fragment>
                    );
                  })}
                </Box>
              )}
            </Paper>
            
            <Typography variant="h6" gutterBottom>
              实验室检查结果
            </Typography>
            <Paper variant="outlined">
              {labResults.length === 0 ? (
                <Box sx={{ p: 2 }}>
                  <Typography>暂无实验室检查结果</Typography>
                </Box>
              ) : (
                <Box sx={{ maxHeight: '400px', overflow: 'auto' }}>
                  {labResults.map((data, index) => (
                    <React.Fragment key={data.id}>
                      <Box sx={{ p: 2 }}>
                        <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }}>
                          <Chip
                            label={data.test_name ?? '未命名检验'}
                            color="secondary"
                            size="small"
                            variant="outlined"
                          />
                          <Typography variant="caption" color="text.secondary">
                            {format(new Date(data.measured_at), 'yyyy-MM-dd HH:mm', { locale: zhCN })}
                          </Typography>
                        </Stack>

                        {/* 后端 lab_result 为单一 result_value（字符串或字典）+ 字符串参考范围 */}
                        {data.result_value !== null && typeof data.result_value === 'object' ? (
                          <Grid container spacing={2} sx={{ mt: 1 }}>
                            {Object.entries(data.result_value).map(([key, value]) => (
                              <Grid item xs={12} sm={6} md={4} key={key}>
                                <Typography variant="body2" color="text.secondary">
                                  {key}
                                </Typography>
                                <Typography variant="body1">
                                  {String(value)}
                                </Typography>
                                {data.reference_range && (
                                  <Typography variant="caption" color="text.secondary">
                                    参考范围: {data.reference_range}
                                  </Typography>
                                )}
                              </Grid>
                            ))}
                          </Grid>
                        ) : (
                          <>
                            <Typography variant="h6">
                              {data.result_value ?? '--'}
                            </Typography>
                            {data.reference_range && (
                              <Typography variant="caption" color="text.secondary">
                                参考范围: {data.reference_range}
                              </Typography>
                            )}
                          </>
                        )}

                        {data.interpretation && (
                          <Typography variant="body2" sx={{ mt: 1 }}>
                            结果解释: {data.interpretation}
                          </Typography>
                        )}

                        {data.notes && (
                          <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
                            备注: {data.notes}
                          </Typography>
                        )}
                      </Box>
                      {index < labResults.length - 1 && <Divider />}
                    </React.Fragment>
                  ))}
                </Box>
              )}
            </Paper>
          </TabPanel>
          
          <TabPanel value={tabValue} index={2}>
            {showForm ? (
              <HealthDataForm
                patientId={selectedPatient}
                onSubmit={handleHealthDataSubmit}
                onCancel={() => setShowForm(false)}
              />
            ) : (
              <Box sx={{ display: 'flex', justifyContent: 'center', p: 4 }}>
                <Typography color="text.secondary">
                  点击"添加数据"按钮来记录新的健康数据
                </Typography>
              </Box>
            )}
          </TabPanel>
        </>
      )}
    </Box>
  );
};

export default DataMonitoring; 
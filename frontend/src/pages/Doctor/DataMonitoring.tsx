import React from 'react';
import {
  Box,
  Typography,
  Paper,
  Grid,
  Card,
  CardContent,
  Divider,
  Tabs,
  Tab,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Button,
  Chip,
  Alert,
  CircularProgress,
  SelectChangeEvent,
} from '@mui/material';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableContainer from '@mui/material/TableContainer';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import RefreshIcon from '@mui/icons-material/Refresh';
import TimelineIcon from '@mui/icons-material/Timeline';
import FavoriteIcon from '@mui/icons-material/Favorite';
import OpacityIcon from '@mui/icons-material/Opacity';
import LocalHospitalIcon from '@mui/icons-material/LocalHospital';
import MonitorWeightIcon from '@mui/icons-material/MonitorWeight';
import { Link } from 'react-router-dom';
import { apiService } from '../../services/api';
import { rehabilitationService, PlanStatisticsResponse } from '../../services/rehabilitationService';
import AnalyticsChart from '../../components/Analytics/AnalyticsChart';

// 选项卡面板属性接口
interface TabPanelProps {
  children?: React.ReactNode;
  index: number;
  value: number;
}

// 后端健康数据文档形状（GET /health-records/health-data，见 HealthDataResponse）
// data_type = "vital_sign" 时 data = { type, value, unit, notes }
// data_type = "lab_result"  时 data = { test_name, result_value, reference_range, unit, interpretation }
interface HealthDataDoc {
  id?: string;
  _id?: string;
  patient_id?: string;
  data_type: string;
  data: {
    type?: string;
    value?: any;
    unit?: string;
    notes?: string;
    test_name?: string;
    result_value?: any;
    reference_range?: string;
    interpretation?: string;
    [key: string]: any;
  };
  source?: string;
  recorded_at?: string;
  created_at?: string;
}

// 患者下拉选项（GET /doctors/patients）
interface PatientOption {
  id: string;
  name: string;
  age?: number;
  gender?: string;
  diagnosis?: string;
}

// 生命体征摘要卡片
interface VitalCard {
  type: string;
  label: string;
  unit: string;
  value: string;
  time: string;
}

// 血压趋势点
interface BPTrendPoint {
  date: string;
  systolic: number;
  diastolic: number;
}

// 血糖记录行
interface GlucoseRow {
  id: string;
  value: string;
  unit: string;
  time: string;
  reference?: string;
  interpretation?: string;
}

// 用药记录行（来自医生健康档案 medications 字段）
interface MedicationRow {
  id: string;
  name: string;
  dosage: string;
  frequency: string;
  purpose: string;
  startDate: string;
  endDate: string;
}

// 康复计划摘要（GET /rehabilitation/plans?patient_id=）
interface RehabPlanSummary {
  id: string;
  name: string;
  status: string;
  goal: string;
  frequency: string;
  startDate: string;
  endDate: string;
  exerciseCount: number;
  progress: number | null; // 仅当 exercises 内含数值型 progress 时可计算
}

// 计划统计响应（GET /rehabilitation/plans/{id}/statistics，形状见 rehabilitationService.ts）
// range_of_motion / muscle_strength 后端无对应字段，如实为 null（unsupported_metrics 列出）
type PlanStatistics = PlanStatisticsResponse;

// 疼痛趋势点（GET /rehabilitation/plans/{id}/trends?metric=pain，按天均值；无值日 value 为 null）
interface PainTrendPoint {
  date: string;
  value: number;
}

// 生命体征类型定义（与后端 vital_type 约定一致，见 schemas/health_record.py:594）
const VITAL_TYPES: Array<{ type: string; label: string; unit: string }> = [
  { type: 'heart_rate', label: '心率', unit: 'bpm' },
  { type: 'body_temperature', label: '体温', unit: '°C' },
  { type: 'respiratory_rate', label: '呼吸频率', unit: '次/分钟' },
  { type: 'blood_oxygen', label: '血氧饱和度', unit: '%' },
  { type: 'weight', label: '体重', unit: 'kg' },
];

// 选项卡面板组件
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
      {value === index && (
        <Box sx={{ p: 3 }}>
          {children}
        </Box>
      )}
    </div>
  );
}

// 将 ISO 时间格式化为展示字符串
const formatTime = (iso?: string): string => {
  if (!iso) return '未知时间';
  const date = new Date(iso);
  if (isNaN(date.getTime())) return String(iso);
  const pad = (n: number) => n.toString().padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
};

// 图表 x 轴短标签
const formatChartLabel = (iso?: string): string => {
  if (!iso) return '';
  const date = new Date(iso);
  if (isNaN(date.getTime())) return String(iso);
  const pad = (n: number) => n.toString().padStart(2, '0');
  return `${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
};

// 解析血压值：支持 "135/85" 字符串与 { systolic, diastolic } 对象
const parseBP = (value: any): { systolic: number; diastolic: number } | null => {
  if (value && typeof value === 'object' && 'systolic' in value) {
    const s = Number(value.systolic);
    const d = Number(value.diastolic);
    if (!isNaN(s) && !isNaN(d)) return { systolic: s, diastolic: d };
    return null;
  }
  const parts = String(value ?? '').split('/');
  if (parts.length === 2) {
    const s = parseFloat(parts[0]);
    const d = parseFloat(parts[1]);
    if (!isNaN(s) && !isNaN(d)) return { systolic: s, diastolic: d };
  }
  return null;
};

// 数值型体征值转字符串（血压等复合值单独处理）
const vitalValueText = (value: any): string => {
  if (value === null || value === undefined || value === '') return '-';
  if (typeof value === 'number') return String(Math.round(value * 10) / 10);
  return String(value);
};

// 患者下拉项展示文案
const patientLabel = (p: PatientOption): string => {
  const traits: string[] = [];
  if (p.age !== undefined) traits.push(`${p.age}岁`);
  if (p.gender) traits.push(p.gender);
  return traits.length > 0 ? `${p.name} (${traits.join(', ')})` : p.name;
};

// 从康复计划 exercises 内的数值型 progress 计算平均完成率；无有效数据时返回 null（不伪造）
const computePlanProgress = (exercises: any[]): number | null => {
  if (!Array.isArray(exercises) || exercises.length === 0) return null;
  const values = exercises
    .map((ex: any) => {
      const raw = ex?.progress ?? ex?.completion_rate ?? ex?.completion;
      const num = typeof raw === 'number' ? raw : parseFloat(String(raw ?? ''));
      return isNaN(num) ? null : num > 1 ? num : num * 100; // 0-1 归一为百分比
    })
    .filter((v): v is number => v !== null);
  if (values.length === 0) return null;
  return Math.round(values.reduce((a, b) => a + b, 0) / values.length);
};

const DataMonitoring: React.FC = () => {
  // 状态管理
  const [tabValue, setTabValue] = React.useState(0);
  const [selectedPatient, setSelectedPatient] = React.useState<string>('');
  const [patients, setPatients] = React.useState<PatientOption[]>([]);
  const [patientsLoading, setPatientsLoading] = React.useState(false);
  const [patientsError, setPatientsError] = React.useState<string | null>(null);

  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [vitals, setVitals] = React.useState<VitalCard[]>([]);
  const [heartRateTrend, setHeartRateTrend] = React.useState<Array<{ date: string; value: number }>>([]);
  const [temperatureTrend, setTemperatureTrend] = React.useState<Array<{ date: string; value: number }>>([]);
  const [bpTrend, setBpTrend] = React.useState<BPTrendPoint[]>([]);
  const [latestBP, setLatestBP] = React.useState<{ value: string; time: string } | null>(null);
  const [glucoseData, setGlucoseData] = React.useState<GlucoseRow[]>([]);
  const [medications, setMedications] = React.useState<MedicationRow[]>([]);
  const [rehabPlan, setRehabPlan] = React.useState<RehabPlanSummary | null>(null);
  // 康复计划统计（statistics/trends 端点已真实实现）
  const [planStatistics, setPlanStatistics] = React.useState<PlanStatistics | null>(null);
  const [planStatsError, setPlanStatsError] = React.useState<string | null>(null);
  const [painTrend, setPainTrend] = React.useState<PainTrendPoint[]>([]);

  // 加载医生的患者列表（真实接口 GET /doctors/patients）
  const loadPatients = React.useCallback(async () => {
    setPatientsLoading(true);
    setPatientsError(null);
    try {
      const response = await apiService.doctor.getPatients();
      const list: any[] = Array.isArray(response.data) ? response.data : [];
      // 后端已诚实化：空库如实返回 []，不再返回 mock_* 模拟患者
      setPatients(list.map(p => ({
        id: String(p?.id ?? p?._id ?? ''),
        name: String(p?.name ?? '未知患者'),
        age: typeof p?.age === 'number' ? p.age : undefined,
        gender: p?.gender ? String(p.gender) : undefined,
        diagnosis: p?.diagnosis ? String(p.diagnosis) : undefined,
      })));
    } catch (err: any) {
      console.error('获取患者列表失败:', err);
      setPatientsError(err?.response?.data?.detail || err?.message || '获取患者列表失败');
    } finally {
      setPatientsLoading(false);
    }
  }, []);

  // 初始加载患者列表
  React.useEffect(() => {
    loadPatients();
  }, [loadPatients]);

  // 加载康复计划统计与疼痛趋势（真实端点：GET /rehabilitation/plans/{id}/statistics 与 /trends，
  // plan_id 来自页面已加载的康复计划前置判断）
  const loadRehabStats = async (planId: string) => {
    setPlanStatsError(null);
    try {
      const [statsRes, painTrendRes] = await Promise.all([
        rehabilitationService.getPlanStatistics(planId),
        // 疼痛趋势（近30天，按天均值）；趋势失败不阻塞统计展示
        rehabilitationService.getPlanTrends(planId, { metric: 'pain', days: 30 }).catch(() => null),
      ]);
      const stats = statsRes.data;
      setPlanStatistics(stats);

      const series = Array.isArray(painTrendRes?.data?.series) ? painTrendRes.data.series : [];
      // 无值日 value 为 null，过滤后仅保留有效均值点
      setPainTrend(
        series
          .filter(p => p?.value !== null && p?.value !== undefined && !isNaN(Number(p.value)))
          .map(p => ({ date: String(p.date), value: Number(p.value) }))
      );
    } catch (err: any) {
      console.error('获取康复计划统计失败:', err);
      setPlanStatistics(null);
      setPainTrend([]);
      setPlanStatsError(err?.response?.data?.detail || err?.message || '获取康复计划统计失败');
    }
  };

  // 加载选中患者的监测数据
  const loadPatientData = async () => {
    if (!selectedPatient) return;
    setLoading(true);
    setError(null);
    setPlanStatistics(null);
    setPainTrend([]);
    setPlanStatsError(null);

    try {
      const [vitalRes, labRes, plansRes, recordRes] = await Promise.all([
        // 生命体征（含血压、血糖体征），真实接口 GET /health-records/health-data
        apiService.getHealthData(selectedPatient, { data_type: 'vital_sign', limit: 200 }),
        // 化验结果（血糖也可能记录在此），真实接口 GET /health-records/health-data?data_type=lab_result
        apiService.getHealthData(selectedPatient, { data_type: 'lab_result', limit: 50 }),
        // 康复计划，真实接口 GET /rehabilitation/plans?patient_id=
        apiService.rehabilitation.getPlans(selectedPatient),
        // 医生侧健康档案（用药记录来源），失败不阻塞其余数据
        apiService.doctor.getPatientHealthRecord(selectedPatient).catch(() => null),
      ]);

      const vitalDocs: HealthDataDoc[] = Array.isArray(vitalRes.data) ? vitalRes.data : [];
      const labDocs: HealthDataDoc[] = Array.isArray(labRes.data) ? labRes.data : [];

      // 按记录时间升序排列，便于取"最新值"与绘制趋势
      const sortedVitals = [...vitalDocs].sort((a, b) =>
        new Date(a.recorded_at ?? a.created_at ?? 0).getTime() - new Date(b.recorded_at ?? b.created_at ?? 0).getTime()
      );

      // 生命体征摘要：每个类型取最新一条
      const latestByType = new Map<string, HealthDataDoc>();
      sortedVitals.forEach(doc => {
        const type = doc?.data?.type;
        if (type) latestByType.set(type, doc);
      });

      const vitalCards: VitalCard[] = VITAL_TYPES
        .filter(v => latestByType.has(v.type))
        .map(v => {
          const doc = latestByType.get(v.type)!;
          return {
            type: v.type,
            label: v.label,
            unit: doc?.data?.unit || v.unit,
            value: vitalValueText(doc?.data?.value),
            time: formatTime(doc?.recorded_at ?? doc?.created_at),
          };
        });
      setVitals(vitalCards);

      // 趋势：心率 / 体温历史
      const trendOf = (type: string) =>
        sortedVitals
          .filter(doc => doc?.data?.type === type && !isNaN(Number(doc?.data?.value)))
          .map(doc => ({ date: formatChartLabel(doc.recorded_at ?? doc.created_at), value: Number(doc.data.value) }));
      setHeartRateTrend(trendOf('heart_rate'));
      setTemperatureTrend(trendOf('body_temperature'));

      // 血压：最新值 + 趋势
      const bpDocs = sortedVitals.filter(doc => doc?.data?.type === 'blood_pressure');
      const bpPoints: BPTrendPoint[] = bpDocs
        .map(doc => {
          const parsed = parseBP(doc?.data?.value);
          return parsed ? { date: formatChartLabel(doc.recorded_at ?? doc.created_at), ...parsed } : null;
        })
        .filter((p): p is BPTrendPoint => p !== null);
      setBpTrend(bpPoints);
      if (bpDocs.length > 0) {
        const latestDoc = bpDocs[bpDocs.length - 1];
        setLatestBP({
          value: vitalValueText(latestDoc?.data?.value),
          time: formatTime(latestDoc?.recorded_at ?? latestDoc?.created_at),
        });
      } else {
        setLatestBP(null);
      }

      // 血糖：体征类型 blood_glucose + 化验结果中含"血糖/葡萄糖"的记录
      const glucoseRows: GlucoseRow[] = [];
      sortedVitals
        .filter(doc => doc?.data?.type === 'blood_glucose')
        .forEach(doc => {
          glucoseRows.push({
            id: String(doc.id ?? doc._id ?? Math.random()),
            value: vitalValueText(doc?.data?.value),
            unit: doc?.data?.unit || '',
            time: formatTime(doc?.recorded_at ?? doc?.created_at),
          });
        });
      labDocs.forEach(doc => {
        const testName = String(doc?.data?.test_name ?? '');
        if (testName.includes('血糖') || testName.includes('葡萄糖')) {
          glucoseRows.push({
            id: String(doc.id ?? doc._id ?? Math.random()),
            value: vitalValueText(doc?.data?.result_value),
            unit: doc?.data?.unit || '',
            time: formatTime(doc?.recorded_at ?? doc?.created_at),
            reference: doc?.data?.reference_range ? String(doc.data.reference_range) : undefined,
            interpretation: doc?.data?.interpretation ? String(doc.data.interpretation) : undefined,
          });
        }
      });
      glucoseRows.sort((a, b) => new Date(b.time).getTime() - new Date(a.time).getTime());
      setGlucoseData(glucoseRows);

      // 用药记录：来自医生健康档案（GET /doctors/health-records/{patient_id} 的 medications 字段）
      const meds = (recordRes?.data as any)?.medications;
      setMedications(Array.isArray(meds)
        ? meds.map((med: any, index: number) => ({
            id: String(med?.id ?? med?._id ?? index),
            name: String(med?.name ?? med?.medication_name ?? med?.drug_name ?? '未知药品'),
            dosage: String(med?.dosage ?? med?.dose ?? '-'),
            frequency: String(med?.frequency ?? med?.dosage_frequency ?? '-'),
            purpose: String(med?.purpose ?? med?.indication ?? '-'),
            startDate: String(med?.start_date ?? med?.startDate ?? '-'),
            endDate: String(med?.end_date ?? med?.endDate ?? '-'),
          }))
        : []);

      // 康复计划：取开始时间最近的一份
      const plans: any[] = Array.isArray(plansRes.data) ? plansRes.data : [];
      if (plans.length > 0) {
        const sortedPlans = [...plans].sort((a, b) =>
          new Date(a?.start_date ?? 0).getTime() - new Date(b?.start_date ?? 0).getTime()
        );
        const plan = sortedPlans[sortedPlans.length - 1];
        const planId = String(plan?._id ?? plan?.id ?? '');
        setRehabPlan({
          id: planId,
          name: String(plan?.name ?? '未命名康复计划'),
          status: String(plan?.status ?? 'unknown'),
          goal: plan?.goal ? String(plan.goal) : '',
          frequency: plan?.frequency ? String(plan.frequency) : '',
          startDate: plan?.start_date ? formatTime(plan.start_date).split(' ')[0] : '-',
          endDate: plan?.end_date ? formatTime(plan.end_date).split(' ')[0] : '-',
          exerciseCount: Array.isArray(plan?.exercises) ? plan.exercises.length : 0,
          progress: computePlanProgress(plan?.exercises ?? []),
        });

        // 已有康复计划时加载计划统计与疼痛趋势（真实端点，失败仅提示不影响其余页签）
        if (planId) {
          await loadRehabStats(planId);
        }
      } else {
        setRehabPlan(null);
      }
    } catch (err: any) {
      console.error('加载患者监测数据失败:', err);
      setError(err?.response?.data?.detail || err?.message || '加载患者监测数据失败，请稍后重试');
    } finally {
      setLoading(false);
    }
  };

  // 处理选项卡变更
  const handleTabChange = (event: React.SyntheticEvent, newValue: number) => {
    setTabValue(newValue);
  };

  // 处理患者选择变更
  const handlePatientChange = (event: SelectChangeEvent<string>) => {
    setSelectedPatient(event.target.value as string);
  };

  // 化验结论标签（后端 interpretation 字段，无则不展示，不自行判定）
  const getInterpretationChip = (interpretation?: string) => {
    if (!interpretation) return null;
    const map: Record<string, { label: string; color: 'success' | 'warning' | 'error' | 'default' }> = {
      normal: { label: '正常', color: 'success' },
      abnormal: { label: '异常', color: 'warning' },
      critical: { label: '危急', color: 'error' },
    };
    const item = map[interpretation] ?? { label: interpretation, color: 'default' as const };
    return <Chip size="small" label={item.label} color={item.color} />;
  };

  return (
    <Box>
      <Typography variant="h5" component="h1" gutterBottom>
        患者数据监测
      </Typography>

      <Paper sx={{ p: 3, mb: 3 }}>
        <Grid container spacing={2} alignItems="center">
          <Grid item xs={12} sm={6} md={4}>
            <FormControl fullWidth>
              <InputLabel id="patient-select-label">选择患者</InputLabel>
              <Select
                labelId="patient-select-label"
                id="patient-select"
                value={selectedPatient}
                label="选择患者"
                onChange={handlePatientChange as any}
                disabled={patientsLoading}
              >
                <MenuItem value="">
                  <em>请选择</em>
                </MenuItem>
                {patients.map((patient) => (
                  <MenuItem key={patient.id} value={patient.id}>
                    {patientLabel(patient)}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          </Grid>
          <Grid item xs={12} sm={6} md={8} textAlign="right">
            <Button
              variant="outlined"
              size="small"
              startIcon={<RefreshIcon />}
              onClick={loadPatients}
              disabled={patientsLoading}
              sx={{ mr: 1 }}
            >
              刷新患者
            </Button>
            <Button
              variant="contained"
              color="primary"
              startIcon={<RefreshIcon />}
              onClick={loadPatientData}
              disabled={!selectedPatient || loading}
              sx={{ mr: 1 }}
            >
              刷新数据
            </Button>
            {selectedPatient && (
              <Button
                component={Link}
                to={`/app/health-manager/health-data-timeline/${selectedPatient}`}
                variant="outlined"
                startIcon={<TimelineIcon />}
              >
                查看时间线
              </Button>
            )}
          </Grid>
        </Grid>
        {patientsError && (
          <Alert severity="error" sx={{ mt: 2 }}>
            {patientsError}
          </Alert>
        )}
      </Paper>

      {!selectedPatient ? (
        <Alert severity="info" sx={{ mt: 2 }}>请选择一位患者以查看其健康数据监测信息</Alert>
      ) : loading ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', mt: 4 }}>
          <CircularProgress />
        </Box>
      ) : error ? (
        <Alert severity="error" sx={{ mt: 2 }}>{error}</Alert>
      ) : (
        <Box sx={{ width: '100%' }}>
          <Box sx={{ borderBottom: 1, borderColor: 'divider' }}>
            <Tabs
              value={tabValue}
              onChange={handleTabChange}
              aria-label="health data tabs"
              variant="scrollable"
              scrollButtons="auto"
            >
              <Tab icon={<FavoriteIcon />} iconPosition="start" label="生命体征" />
              <Tab icon={<OpacityIcon />} iconPosition="start" label="血压/血糖" />
              <Tab icon={<LocalHospitalIcon />} iconPosition="start" label="用药情况" />
              <Tab icon={<MonitorWeightIcon />} iconPosition="start" label="康复进度" />
            </Tabs>
          </Box>

          <Typography variant="caption" color="text.secondary" component="div" sx={{ mt: 1 }}>
            数据来源：患者健康档案中已录入的生命体征与化验记录（GET /health-records/health-data）。
            数据非实时同步，可点击"刷新数据"获取最新记录。
          </Typography>

          {/* 生命体征选项卡 */}
          <TabPanel value={tabValue} index={0}>
            <Grid container spacing={3}>
              {vitals.length === 0 ? (
                <Grid item xs={12}>
                  <Alert severity="info">该患者暂无生命体征记录</Alert>
                </Grid>
              ) : (
                vitals.map((vital) => (
                  <Grid item xs={12} sm={6} md={4} key={vital.type}>
                    <Card variant="outlined">
                      <CardContent sx={{ p: 2, '&:last-child': { pb: 2 } }}>
                        <Box display="flex" justifyContent="space-between" alignItems="center" mb={1}>
                          <Typography variant="subtitle1" component="div">
                            {vital.label}
                          </Typography>
                        </Box>
                        <Box display="flex" alignItems="baseline">
                          <Typography variant="h4" component="span">
                            {vital.value}
                          </Typography>
                          <Typography variant="body2" component="span" sx={{ ml: 1 }}>
                            {vital.unit}
                          </Typography>
                        </Box>
                        <Typography variant="caption" color="text.secondary" component="div">
                          记录时间: {vital.time}
                        </Typography>
                      </CardContent>
                    </Card>
                  </Grid>
                ))
              )}

              {/* 生命体征历史趋势（真实记录绘制） */}
              <Grid item xs={12}>
                <Paper sx={{ p: 2 }}>
                  <Typography variant="h6" gutterBottom>生命体征趋势</Typography>
                  {heartRateTrend.length === 0 && temperatureTrend.length === 0 ? (
                    <Alert severity="info">暂无可用于绘制趋势的体征历史记录</Alert>
                  ) : (
                    <Grid container spacing={2}>
                      <Grid item xs={12} md={6}>
                        <AnalyticsChart
                          type="line"
                          data={heartRateTrend}
                          height={250}
                          xKey="date"
                          yKeys={['value']}
                          title="心率趋势 (bpm)"
                        />
                      </Grid>
                      <Grid item xs={12} md={6}>
                        <AnalyticsChart
                          type="line"
                          data={temperatureTrend}
                          height={250}
                          xKey="date"
                          yKeys={['value']}
                          title="体温趋势 (°C)"
                        />
                      </Grid>
                    </Grid>
                  )}
                </Paper>
              </Grid>
            </Grid>
          </TabPanel>

          {/* 血压/血糖选项卡 */}
          <TabPanel value={tabValue} index={1}>
            <Grid container spacing={3}>
              {/* 血压部分 */}
              <Grid item xs={12}>
                <Paper sx={{ p: 3, mb: 3 }}>
                  <Typography variant="h6" gutterBottom>血压监测</Typography>
                  <Grid container spacing={3}>
                    <Grid item xs={12} md={4}>
                      <Card variant="outlined">
                        <CardContent>
                          <Typography variant="subtitle1" gutterBottom>当前血压</Typography>
                          {latestBP ? (
                            <>
                              <Box display="flex" alignItems="baseline">
                                <Typography variant="h4" component="span">
                                  {latestBP.value}
                                </Typography>
                                <Typography variant="body2" component="span" sx={{ ml: 1 }}>
                                  mmHg
                                </Typography>
                              </Box>
                              <Typography variant="caption" color="text.secondary">
                                记录于 {latestBP.time}
                              </Typography>
                            </>
                          ) : (
                            <Typography variant="body2" color="text.secondary">
                              暂无血压记录
                            </Typography>
                          )}
                        </CardContent>
                      </Card>
                    </Grid>
                    <Grid item xs={12} md={8}>
                      <AnalyticsChart
                        type="line"
                        data={bpTrend}
                        height={250}
                        xKey="date"
                        yKeys={['systolic', 'diastolic']}
                        colors={{ systolic: '#e53935', diastolic: '#1e88e5' }}
                        title="血压趋势 (mmHg)"
                      />
                    </Grid>
                  </Grid>
                </Paper>
              </Grid>

              {/* 血糖部分 */}
              <Grid item xs={12}>
                <Paper sx={{ p: 3 }}>
                  <Typography variant="h6" gutterBottom>血糖监测</Typography>
                  {glucoseData.length === 0 ? (
                    <Alert severity="info">
                      暂无血糖记录（体征记录中无 blood_glucose 类型数据，化验结果中亦无血糖类检测）
                    </Alert>
                  ) : (
                    <>
                      <TableContainer>
                        <Table size="small">
                          <TableHead>
                            <TableRow>
                              <TableCell>数值</TableCell>
                              <TableCell>状态</TableCell>
                              <TableCell>参考范围</TableCell>
                              <TableCell>记录时间</TableCell>
                            </TableRow>
                          </TableHead>
                          <TableBody>
                            {glucoseData.map((row) => (
                              <TableRow key={row.id} hover>
                                <TableCell>
                                  <Box display="flex" alignItems="center">
                                    {row.value} {row.unit}
                                  </Box>
                                </TableCell>
                                <TableCell>
                                  {getInterpretationChip(row.interpretation) ?? (
                                    <Chip size="small" label="未判定" variant="outlined" />
                                  )}
                                </TableCell>
                                <TableCell>{row.reference ?? '-'}</TableCell>
                                <TableCell>{row.time}</TableCell>
                              </TableRow>
                            ))}
                          </TableBody>
                        </Table>
                      </TableContainer>
                      <Box mt={3}>
                        <AnalyticsChart
                          type="line"
                          data={glucoseData
                            .filter(row => !isNaN(Number(row.value)))
                            .map(row => ({ date: row.time, value: Number(row.value) }))
                            .reverse()}
                          height={250}
                          xKey="date"
                          yKeys={['value']}
                          title="血糖记录 (按时间)"
                        />
                      </Box>
                    </>
                  )}
                </Paper>
              </Grid>
            </Grid>
          </TabPanel>

          {/* 用药情况选项卡 */}
          <TabPanel value={tabValue} index={2}>
            <Grid container spacing={3}>
              <Grid item xs={12}>
                <Paper sx={{ p: 3, mb: 3 }}>
                  <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
                    <Typography variant="h6">当前用药</Typography>
                    <Button
                      variant="outlined"
                      size="small"
                      component={Link}
                      to={`/app/doctor/health-records/${selectedPatient}`}
                    >
                      查看完整用药史
                    </Button>
                  </Box>

                  {medications.length === 0 ? (
                    <Alert severity="info">
                      暂无用药记录（该患者健康档案的 medications 字段为空）
                    </Alert>
                  ) : (
                    <TableContainer>
                      <Table>
                        <TableHead>
                          <TableRow>
                            <TableCell>药品名称</TableCell>
                            <TableCell>剂量</TableCell>
                            <TableCell>频率</TableCell>
                            <TableCell>用途</TableCell>
                            <TableCell>起止日期</TableCell>
                          </TableRow>
                        </TableHead>
                        <TableBody>
                          {medications.map((med) => (
                            <TableRow key={med.id} hover>
                              <TableCell>
                                <Typography variant="body2" fontWeight="500">
                                  {med.name}
                                </Typography>
                              </TableCell>
                              <TableCell>{med.dosage}</TableCell>
                              <TableCell>{med.frequency}</TableCell>
                              <TableCell>{med.purpose}</TableCell>
                              <TableCell>
                                {med.startDate} 至 {med.endDate}
                              </TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </TableContainer>
                  )}
                </Paper>
              </Grid>

              <Grid item xs={12}>
                <Paper sx={{ p: 3 }}>
                  <Typography variant="h6" gutterBottom>服药依从性</Typography>
                  <Alert severity="info">
                    暂无数据源：后端未提供服药依从率统计端点，依从率与依从趋势待后端支持后接入。
                  </Alert>
                </Paper>
              </Grid>
            </Grid>
          </TabPanel>

          {/* 康复进度选项卡 */}
          <TabPanel value={tabValue} index={3}>
            {rehabPlan ? (
              <Grid container spacing={3}>
                <Grid item xs={12}>
                  <Paper sx={{ p: 3, mb: 3 }}>
                    <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
                      <Typography variant="h6">康复计划进度</Typography>
                      <Button
                        variant="outlined"
                        size="small"
                        component={Link}
                        to={`/app/rehab-plans`}
                      >
                        查看完整计划
                      </Button>
                    </Box>

                    <Grid container spacing={3}>
                      <Grid item xs={12} md={6}>
                        <Box>
                          <Typography variant="subtitle2" color="text.secondary" gutterBottom>
                            {rehabPlan.name}
                          </Typography>
                          <Box display="flex" gap={1} mb={2}>
                            <Chip
                              size="small"
                              label={
                                rehabPlan.status === 'active' ? '进行中'
                                  : rehabPlan.status === 'completed' ? '已完成'
                                  : rehabPlan.status === 'cancelled' ? '已取消'
                                  : rehabPlan.status
                              }
                              color={rehabPlan.status === 'active' ? 'primary' : 'default'}
                            />
                            {rehabPlan.frequency && (
                              <Chip size="small" variant="outlined" label={`频率: ${rehabPlan.frequency}`} />
                            )}
                          </Box>
                          {rehabPlan.goal && (
                            <Typography variant="body2" gutterBottom>
                              康复目标: {rehabPlan.goal}
                            </Typography>
                          )}
                          <Typography variant="body2" gutterBottom>
                            开始日期: {rehabPlan.startDate}{rehabPlan.endDate !== '-' ? ` 至 ${rehabPlan.endDate}` : ''}
                          </Typography>
                          <Typography variant="body2" gutterBottom>
                            训练项目数: {rehabPlan.exerciseCount}
                          </Typography>
                          <Typography variant="body2">
                            下次复诊: 暂无数据源（后端未提供复诊预约查询端点）
                          </Typography>
                        </Box>
                      </Grid>

                      <Grid item xs={12} md={6}>
                        <Typography variant="subtitle2" color="text.secondary" gutterBottom>
                          计划完成率（按训练项目进度均值估算）
                        </Typography>
                        {rehabPlan.progress !== null ? (
                          <Box sx={{ position: 'relative', display: 'inline-flex', mt: 1 }}>
                            <CircularProgress
                              variant="determinate"
                              value={Math.min(100, rehabPlan.progress)}
                              size={100}
                              thickness={5}
                              color="primary"
                            />
                            <Box
                              sx={{
                                top: 0,
                                left: 0,
                                bottom: 0,
                                right: 0,
                                position: 'absolute',
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'center',
                              }}
                            >
                              <Typography variant="h6" component="div" color="text.secondary">
                                {`${rehabPlan.progress}%`}
                              </Typography>
                            </Box>
                          </Box>
                        ) : (
                          <Alert severity="info" sx={{ mt: 1 }}>
                            计划内训练项目暂无进度记录，无法计算完成率
                          </Alert>
                        )}
                      </Grid>
                    </Grid>
                  </Paper>
                </Grid>

                <Grid item xs={12}>
                  <Paper sx={{ p: 3 }}>
                    <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
                      <Typography variant="h6">康复关键指标</Typography>
                      <Button
                        variant="outlined"
                        size="small"
                        onClick={() => rehabPlan && loadRehabStats(rehabPlan.id)}
                      >
                        刷新统计
                      </Button>
                    </Box>

                    {planStatsError && (
                      <Alert severity="error" sx={{ mb: 2 }}>{planStatsError}</Alert>
                    )}

                    {!planStatistics ? (
                      !planStatsError && (
                        <Alert severity="info">暂无统计数据（点击"刷新统计"重新加载）</Alert>
                      )
                    ) : (
                      <>
                        {/* 统计摘要：statistics 真实聚合字段 */}
                        <Grid container spacing={2} mb={3}>
                          <Grid item xs={6} sm={3}>
                            <Typography variant="caption" color="text.secondary">训练记录数</Typography>
                            <Typography variant="h6">{planStatistics.total_records}</Typography>
                          </Grid>
                          <Grid item xs={6} sm={3}>
                            <Typography variant="caption" color="text.secondary">已完成记录</Typography>
                            <Typography variant="h6">{planStatistics.completed_records}</Typography>
                          </Grid>
                          <Grid item xs={6} sm={3}>
                            <Typography variant="caption" color="text.secondary">完成率</Typography>
                            <Typography variant="h6">
                              {planStatistics.completion_rate !== null ? `${planStatistics.completion_rate}%` : '--'}
                            </Typography>
                          </Grid>
                          <Grid item xs={6} sm={3}>
                            <Typography variant="caption" color="text.secondary">平均疼痛等级</Typography>
                            <Typography variant="h6">
                              {planStatistics.avg_pain_level !== null ? planStatistics.avg_pain_level : '--'}
                            </Typography>
                          </Grid>
                        </Grid>

                        <Grid container spacing={3}>
                          {/* 疼痛趋势：trends(metric=pain)，按天均值，无值日 value 为 null 已过滤 */}
                          <Grid item xs={12} md={6}>
                            <Typography variant="subtitle2" gutterBottom>
                              疼痛趋势（近30天，按天均值）
                            </Typography>
                            {painTrend.length === 0 ? (
                              <Alert severity="info">
                                该计划暂无疼痛记录（训练进度中 pain_level 无非空值）
                              </Alert>
                            ) : (
                              <AnalyticsChart
                                type="line"
                                data={painTrend}
                                height={220}
                                xKey="date"
                                yKeys={['value']}
                                title="疼痛等级趋势 (0-10)"
                              />
                            )}
                          </Grid>

                          {/* 每周训练完成率：statistics.weekly_completion[]（按自然周分桶） */}
                          <Grid item xs={12} md={6}>
                            <Typography variant="subtitle2" gutterBottom>
                              每周训练完成率
                            </Typography>
                            {planStatistics.weekly_completion.length === 0 ? (
                              <Alert severity="info">
                                暂无周完成率数据（计划内无进度记录）
                              </Alert>
                            ) : (
                              <AnalyticsChart
                                type="bar"
                                data={planStatistics.weekly_completion.map(w => ({
                                  week: w.week_start,
                                  rate: w.completion_rate,
                                }))}
                                height={220}
                                xKey="week"
                                yKeys={['rate']}
                                title="每周完成率 (%)"
                              />
                            )}
                          </Grid>
                        </Grid>

                        {/* 后端无对应数据字段的指标：如实保持"暂无数据源" */}
                        <Alert severity="warning" sx={{ mt: 3 }}>
                          暂无数据源：关节活动度（range_of_motion）与肌肉力量（muscle_strength）
                          后端无对应数据字段，统计响应中如实为 null
                          （unsupported_metrics: {planStatistics.unsupported_metrics.join('、')}），
                          待后端补充数据采集后接入。
                        </Alert>

                        <Typography variant="caption" color="text.secondary" component="div" sx={{ mt: 1 }}>
                          数据来源：{planStatistics.data_source}
                          {planStatistics.data_notes.length > 0
                            ? `；备注：${planStatistics.data_notes.join('；')}`
                            : ''}
                        </Typography>
                      </>
                    )}
                  </Paper>
                </Grid>
              </Grid>
            ) : (
              <Alert severity="info">
                未找到当前患者的康复计划（GET /rehabilitation/plans?patient_id= 无记录），请先为该患者创建康复计划。
              </Alert>
            )}
          </TabPanel>
        </Box>
      )}
    </Box>
  );
};

export default DataMonitoring;

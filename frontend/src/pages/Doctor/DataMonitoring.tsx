import { usePatientOptions, type PatientOption } from '../../hooks/usePatientOptions';
import PatientSelect from '../../components/common/PatientSelect';
import { apiErrorMessage } from '../../services/patientErrors';
import { healthDataVitalDisplay, healthDataLabDisplay, healthDataType, healthDataQualityFlags, healthDataNumber, healthObservations, isTrendObservation, healthDataTimestamp, type HealthDataFact, type HealthObservation } from '../../utils/healthDataFacts';
import HealthDataQualityNotice from '../../components/common/HealthDataQualityNotice';
import React from 'react';
import { formatAppDate } from '../../utils/dateTime';
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
  Button,
  Chip,
  Alert,
  CircularProgress,
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
import { useSelector } from 'react-redux';
import { apiService, assignedPatientsApi } from '../../services/api';
import AnalyticsChart from '../../components/Analytics/AnalyticsChart';
import { RootState } from '../../store';

// 选项卡面板属性接口
interface TabPanelProps {
  children?: React.ReactNode;
  index: number;
  value: number;
}

// 健康数据文档统一使用 HealthDataFact；字段兼容由 healthDataFacts 工具集中处理。
// 生命体征摘要卡片
interface VitalCard {
  type: string;
  label: string;
  unit: string;
  value: string;
  time: string;
  qualityFlags: string[];
}

// 血压趋势点
interface BPTrendPoint {
  date: string;
  systolic?: number;
  diastolic?: number;
}

// 血糖记录行
interface GlucoseRow {
  id: string;
  value: string;
  unit: string;
  time: string;
  timestamp: string;
  reference?: string;
  interpretation?: string;
  qualityFlags: string[];
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
}

// 生命体征类型定义（与后端 vital_type 约定一致，见 schemas/health_record.py:594）
const VITAL_TYPES: Array<{ type: string; label: string; unit: string }> = [
  { type: 'heart_rate', label: '心率', unit: 'bpm' },
  { type: 'body_temperature', label: '体温', unit: '°C' },
  { type: 'respiratory_rate', label: '呼吸频率', unit: '次/分钟' },
  { type: 'oxygen_saturation', label: '血氧饱和度', unit: '%' },
  { type: 'weight', label: '体重', unit: 'kg' },
  { type: 'blood_pressure_systolic', label: '收缩压（独立分量）', unit: 'mmHg' },
  { type: 'blood_pressure_diastolic', label: '舒张压（独立分量）', unit: 'mmHg' },
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
const formatTime = (iso?: string): string =>
  formatAppDate(iso, 'minute', { assumeUtc: true, empty: '未知时间', invalid: iso ? String(iso) : '未知时间' });

// 图表 x 轴短标签
const formatChartLabel = (iso?: string): string => {
  return formatAppDate(iso, 'MM-dd HH:mm', { parse: 'native', assumeUtc: true, invalid: iso ? String(iso) : '' });
};

// 数值型体征值转字符串（血压等复合值单独处理）
const vitalValueText = (value: any): string => {
  if (value === null || value === undefined || value === '') return '-';
  if (typeof value === 'number') return String(Math.round(value * 10) / 10);
  return typeof value === 'object' ? JSON.stringify(value) : String(value);
};

// 患者下拉项展示文案
const patientLabel = (p: PatientOption): string => {
  const traits: string[] = [];
  if (p.age !== undefined) traits.push(`${p.age}岁`);
  if (p.gender) traits.push(p.gender);
  return traits.length > 0 ? `${p.name} (${traits.join(', ')})` : p.name;
};

const DataMonitoring: React.FC = () => {
  const actor = useSelector((state: RootState) => state.auth.user);
  const role = actor?.role;
  const recordsBase = role === 'health_manager' ? '/app/health-manager' : '/app/doctor';
  // 状态管理
  const [tabValue, setTabValue] = React.useState(0);
  const [selectedPatient, setSelectedPatient] = React.useState<string>('');
  const { patients, loading: patientsLoading, error: patientFailure, reload: loadPatients } = usePatientOptions(role, actor?.id);
  const patientsError = patientFailure ? apiErrorMessage(patientFailure, '获取患者列表失败') : null;

  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [vitals, setVitals] = React.useState<VitalCard[]>([]);
  const [heartRateTrend, setHeartRateTrend] = React.useState<Array<{ date: string; value: number }>>([]);
  const [temperatureTrend, setTemperatureTrend] = React.useState<Array<{ date: string; value: number }>>([]);
  const [healthObservationsData, setHealthObservationsData] = React.useState<HealthObservation[]>([]);
  const [bpTrend, setBpTrend] = React.useState<BPTrendPoint[]>([]);
  const [latestBP, setLatestBP] = React.useState<{ value: string; time: string; qualityFlags: string[] } | null>(null);
  const [glucoseData, setGlucoseData] = React.useState<GlucoseRow[]>([]);
  const [medications, setMedications] = React.useState<MedicationRow[]>([]);
  const [rehabPlan, setRehabPlan] = React.useState<RehabPlanSummary | null>(null);
  // 加载选中患者的监测数据
  const loadPatientData = async () => {
    if (!selectedPatient) return;
    setLoading(true);
    setError(null);

    try {
      const [vitalRes, labRes, plansRes, recordRes] = await Promise.all([
        // 生命体征（含血压、血糖体征），真实接口 GET /health-records/health-data
        apiService.getHealthData(selectedPatient, { data_type: 'vital_sign', limit: 200 }),
        // 化验结果（血糖也可能记录在此），真实接口 GET /health-records/health-data?data_type=lab_result
        apiService.getHealthData(selectedPatient, { data_type: 'lab_result', limit: 50 }),
        // 康复计划，真实接口 GET /rehabilitation/plans?patient_id=
        apiService.rehabilitation.getPlans(selectedPatient),
        // 医生侧健康档案（用药记录来源），失败不阻塞其余数据
        assignedPatientsApi(role).getPatientHealthRecord(selectedPatient).catch(() => null),
      ]);

      const vitalDocs: HealthDataFact[] = Array.isArray(vitalRes.data) ? vitalRes.data : [];
      const labDocs: HealthDataFact[] = Array.isArray(labRes.data) ? labRes.data : [];
      const observations = healthObservations(vitalDocs);
      setHealthObservationsData(observations);

      // 按记录时间升序排列，便于取"最新值"与绘制趋势
      const sortedVitals = [...vitalDocs].sort((a, b) =>
        healthDataTimestamp(a.recorded_at ?? a.created_at ?? '') - healthDataTimestamp(b.recorded_at ?? b.created_at ?? '')
      );

      // 生命体征摘要：每个类型取最新一条
      const latestByType = new Map<string, HealthDataFact>();
      sortedVitals.forEach(doc => {
        const type = healthDataType(doc);
        if (type) latestByType.set(type, doc);
      });

      const vitalCards: VitalCard[] = VITAL_TYPES
        .filter(v => latestByType.has(v.type))
        .map(v => {
          const doc = latestByType.get(v.type)!;
          const display = healthDataVitalDisplay(doc);
          return {
            type: v.type,
            label: v.label,
            unit: display.unit || v.unit,
            value: vitalValueText(display.value),
            time: formatTime(doc?.recorded_at ?? doc?.created_at),
            qualityFlags: healthDataQualityFlags(doc),
          };
        });
      setVitals(vitalCards);

      // 趋势：心率 / 体温历史
      const trendOf = (type: string) => observations
        .filter(point => point.type === type && isTrendObservation(point))
        .map(point => ({ date: formatChartLabel(point.timestamp), value: point.value! }));
      setHeartRateTrend(trendOf('heart_rate'));
      setTemperatureTrend(trendOf('body_temperature'));

      // 血压：最新值 + 趋势
      const bpDocs = sortedVitals.filter(doc => healthDataType(doc) === 'blood_pressure');
      const bpPoints: BPTrendPoint[] = observations
        .filter(point => ['blood_pressure_systolic', 'blood_pressure_diastolic'].includes(point.type)
          && isTrendObservation(point))
        .map(point => ({ date: formatChartLabel(point.timestamp),
          [point.type === 'blood_pressure_systolic' ? 'systolic' : 'diastolic']: point.value! }));
      setBpTrend(bpPoints);
      if (bpDocs.length > 0) {
        const latestDoc = bpDocs[bpDocs.length - 1];
        const display = healthDataVitalDisplay(latestDoc);
        setLatestBP({
          value: vitalValueText(display.value),
          time: formatTime(latestDoc?.recorded_at ?? latestDoc?.created_at),
          qualityFlags: healthDataQualityFlags(latestDoc),
        });
      } else {
        setLatestBP(null);
      }

      // 血糖：体征类型 blood_glucose + 化验结果中含"血糖/葡萄糖"的记录
      const glucoseRows: GlucoseRow[] = [];
      sortedVitals
        .filter(doc => healthDataType(doc) === 'blood_glucose')
        .forEach(doc => {
          const display = healthDataVitalDisplay(doc);
          glucoseRows.push({
            qualityFlags: healthDataQualityFlags(doc),
            id: String(doc.id ?? doc._id ?? Math.random()),
            value: vitalValueText(display.value),
            unit: display.unit,
            time: formatTime(doc?.recorded_at ?? doc?.created_at),
            timestamp: doc.recorded_at ?? doc.created_at ?? '',
          });
        });
      labDocs.forEach(doc => {
        const display = healthDataLabDisplay(doc);
        const testName = display.testName;
        if (testName.includes('血糖') || testName.includes('葡萄糖')) {
          glucoseRows.push({
            qualityFlags: healthDataQualityFlags(doc),
            id: String(doc.id ?? doc._id ?? Math.random()),
            value: vitalValueText(display.value),
            unit: display.unit,
            time: formatTime(doc?.recorded_at ?? doc?.created_at),
            timestamp: doc.recorded_at ?? doc.created_at ?? '',
            reference: display.reference,
            interpretation: display.interpretation,
          });
        }
      });
      glucoseRows.sort((a, b) => healthDataTimestamp(b.timestamp) - healthDataTimestamp(a.timestamp));
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
        });

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
            <PatientSelect fullWidth label="选择患者" value={selectedPatient} onChange={setSelectedPatient}
              patients={patients.map(patient => ({ ...patient, name: patientLabel(patient) }))} loading={patientsLoading} />
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

          <HealthDataQualityNotice observations={healthObservationsData}
            label={type => VITAL_TYPES.find(item => item.type === type)?.label || type} />
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
                        {vital.qualityFlags.length > 0 && <Chip size="small" color="warning" label={`质量待核查：${vital.qualityFlags.join('、')}`} />}
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
                          <Typography variant="subtitle1" gutterBottom>最近完整血压记录</Typography>
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
                              {latestBP.qualityFlags.length > 0 && <Chip size="small" color="warning" label={`质量待核查：${latestBP.qualityFlags.join('、')}`} />}
                              <Typography variant="caption" color="text.secondary">
                                记录于 {latestBP.time}
                              </Typography>
                            </>
                          ) : (
                            <Typography variant="body2" color="text.secondary">
                              暂无完整血压记录，独立分量见下表
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
                  <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>血压分量按各自测量时间展示，不将独立读数配对为一次完整血压。</Typography>
                  <Table size="small">
                    <TableHead><TableRow><TableCell>分量</TableCell><TableCell>原始数值</TableCell><TableCell>记录时间</TableCell><TableCell>质量标记</TableCell></TableRow></TableHead>
                    <TableBody>{healthObservationsData.filter(point => ['blood_pressure_systolic', 'blood_pressure_diastolic'].includes(point.type)).map((point, index) =>
                      <TableRow key={`${point.id}-${point.type}-${index}`}>
                        <TableCell>{point.type === 'blood_pressure_systolic' ? '收缩压' : '舒张压'}</TableCell>
                        <TableCell>{String(point.rawValue ?? '-')} {point.unit}</TableCell>
                        <TableCell>{formatTime(point.timestamp)}</TableCell>
                        <TableCell>{point.qualityFlags.length ? <Chip size="small" color="warning" label={point.qualityFlags.join('、')} /> : '未附质量标记'}</TableCell>
                      </TableRow>)}</TableBody>
                  </Table>
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
                                  {row.qualityFlags.length ? <Chip size="small" color="warning" label={`质量待核查：${row.qualityFlags.join('、')}`} /> : getInterpretationChip(row.interpretation) ?? (
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
                            .filter(row => row.qualityFlags.length === 0 && healthDataNumber(row.value) !== null)
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
                      to={`${recordsBase}/health-records/${selectedPatient}`}
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
                        <Alert severity="info" action={<Button component={Link} to="/app/rehab-plans">查看患者自述</Button>}>
                          可在新版已发布方案中查看患者自述及感受；训练完成率暂不可计算。
                        </Alert>
                      </Grid>
                    </Grid>
                  </Paper>
                </Grid>

                <Grid item xs={12}>
                  <Alert severity="info" action={<Button component={Link} to="/app/rehab-plans">打开新版方案工作台</Button>}>
                    本页保留计划和健康事实。训练状态来自患者自述，不再从旧计划进度数组推算完成率、训练次数或疼痛趋势。
                  </Alert>
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

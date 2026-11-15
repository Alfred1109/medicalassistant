import React, { useCallback, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useSelector } from 'react-redux';
import {
  Box,
  Typography,
  Paper,
  Tabs,
  Tab,
  Divider,
  Grid,
  Card,
  CardContent,
  List,
  ListItem,
  ListItemText,
  Chip,
  Button,
  IconButton,
  TextField,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  CircularProgress,
  Alert,
} from '@mui/material';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import EditIcon from '@mui/icons-material/Edit';
import AddIcon from '@mui/icons-material/Add';
import RefreshIcon from '@mui/icons-material/Refresh';
import { assignedPatientsApi } from '../../services/api';
import { useAsyncResource } from '../../hooks/useAsyncResource';
import { RootState } from '../../store';
import { PatientHealthRecord } from '../../types/patient.types';
import { healthDataPayload, healthDataQualityFlags, healthDataType, healthDataValueText } from '../../utils/healthDataFacts';
import { formatAppDate } from '../../utils/dateTime';

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
      id={`simple-tabpanel-${index}`}
      aria-labelledby={`simple-tab-${index}`}
      {...other}
    >
      {value === index && <Box p={3}>{children}</Box>}
    </div>
  );
}

// 空的健康记录模板，在没有数据时使用
const emptyHealthRecord: PatientHealthRecord = {
  id: '',
  name: '',
  age: 0,
  gender: '',
  height: 0,
  weight: 0,
  bloodType: '',
  allergies: [],
  emergencyContact: '',
  medicalHistory: [],
  rehabHistory: [],
  medications: [],
  vitalSigns: []
};

const HealthRecords: React.FC = () => {
  const { patientId } = useParams<{ patientId: string }>();
  const navigate = useNavigate();
  const [tabValue, setTabValue] = useState(0);
  const role = useSelector((state: RootState) => state.auth.user?.role);
  const patientsPath = role === 'health_manager' ? '/app/health-manager/patients' : '/app/doctor/patients';

  // 使用API钩子获取患者健康记录（医生与健康管理师各走自己的授权端点）
  const loadRecord = useCallback(async (signal: AbortSignal) => {
    const response = await assignedPatientsApi(role).getPatientHealthRecord(patientId!, signal);
    return response.data;
  }, [role, patientId]);
  const { data: healthRecord, loading, error: loadError, reload } =
    useAsyncResource(loadRecord, Boolean(patientId) && (role === 'doctor' || role === 'health_manager'));
  const error = loadError instanceof Error ? loadError : loadError ? new Error('获取健康记录失败') : null;

  // 如果没有提供patientId，返回错误信息
  if (!patientId) {
    return (
      <Box p={3}>
        <Typography color="error">错误：未提供患者ID</Typography>
        <Button 
          variant="contained" 
          startIcon={<ArrowBackIcon />}
          onClick={() => navigate(patientsPath)}
          sx={{ mt: 2 }}
        >
          返回患者列表
        </Button>
      </Box>
    );
  }

  // 处理重试请求
  const handleRetry = () => {
    reload();
  };

  // 使用实际的健康记录或使用空记录（而不是模拟数据）
  const record = healthRecord || emptyHealthRecord;

  const handleTabChange = (event: React.SyntheticEvent, newValue: number) => {
    setTabValue(newValue);
  };

  return (
    <Box p={3}>
      <Box display="flex" alignItems="center" mb={3}>
        <IconButton onClick={() => navigate(patientsPath)} sx={{ mr: 1 }}>
          <ArrowBackIcon />
        </IconButton>
        <Typography variant="h4">患者健康档案</Typography>
        
        {error && (
          <Button 
            variant="outlined" 
            color="error" 
            startIcon={<RefreshIcon />} 
            sx={{ ml: 2 }}
            onClick={handleRetry}
          >
            重新加载
          </Button>
        )}
      </Box>

      {/* 显示错误信息 */}
      {error && (
        <Alert severity="error" sx={{ mb: 3 }}>
          获取健康记录失败: {error.message}
        </Alert>
      )}

      {loading ? (
        <Box display="flex" justifyContent="center" alignItems="center" height="50vh">
          <CircularProgress />
          <Typography variant="body1" sx={{ ml: 2 }}>
            加载患者健康记录...
          </Typography>
        </Box>
      ) : (
        <Grid container spacing={3}>
          <Grid item xs={12} md={4}>
            <Card>
              <CardContent>
                <Box display="flex" justifyContent="space-between" alignItems="flex-start">
                  <Typography variant="h5" gutterBottom>
                    {record.name || '未知患者'}
                  </Typography>
                  <IconButton color="primary">
                    <EditIcon />
                  </IconButton>
                </Box>
                <Typography color="textSecondary" gutterBottom>
                  基本信息
                </Typography>
                <Divider sx={{ my: 1 }} />
                <Grid container spacing={1}>
                  <Grid item xs={6}>
                    <Typography variant="subtitle2">年龄</Typography>
                    <Typography variant="body2">{record.age || '未知'} {record.age ? '岁' : ''}</Typography>
                  </Grid>
                  <Grid item xs={6}>
                    <Typography variant="subtitle2">性别</Typography>
                    <Typography variant="body2">{record.gender || '未知'}</Typography>
                  </Grid>
                  <Grid item xs={6}>
                    <Typography variant="subtitle2">身高</Typography>
                    <Typography variant="body2">{record.height ? `${record.height} cm` : '未知'}</Typography>
                  </Grid>
                  <Grid item xs={6}>
                    <Typography variant="subtitle2">体重</Typography>
                    <Typography variant="body2">{record.weight ? `${record.weight} kg` : '未知'}</Typography>
                  </Grid>
                  <Grid item xs={6}>
                    <Typography variant="subtitle2">血型</Typography>
                    <Typography variant="body2">{record.bloodType || '未知'}</Typography>
                  </Grid>
                  <Grid item xs={12}>
                    <Typography variant="subtitle2" gutterBottom>
                      过敏史
                    </Typography>
                    <Box>
                      {record.allergies && record.allergies.length > 0 ? (
                        record.allergies.map((allergy, index) => (
                          <Chip
                            key={index}
                            label={allergy}
                            size="small"
                            color="error"
                            sx={{ mr: 0.5, mb: 0.5 }}
                          />
                        ))
                      ) : (
                        <Typography variant="body2" color="text.secondary">无过敏史</Typography>
                      )}
                    </Box>
                  </Grid>
                  <Grid item xs={12}>
                    <Typography variant="subtitle2">紧急联系人</Typography>
                    <Typography variant="body2">{record.emergencyContact || '无紧急联系人'}</Typography>
                  </Grid>
                </Grid>
              </CardContent>
            </Card>
          </Grid>

          <Grid item xs={12} md={8}>
            <Paper sx={{ width: '100%' }}>
              <Tabs value={tabValue} onChange={handleTabChange} aria-label="health record tabs">
                <Tab label="病史记录" />
                <Tab label="康复记录" />
                <Tab label="用药记录" />
                <Tab label="生命体征" />
              </Tabs>

              <TabPanel value={tabValue} index={0}>
                <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
                  <Typography variant="h6">病史记录</Typography>
                  <Button startIcon={<AddIcon />} variant="outlined" size="small">
                    添加记录
                  </Button>
                </Box>
                {record.medicalHistory && record.medicalHistory.length > 0 ? (
                  <List>
                    {record.medicalHistory.map((history, index) => (
                      <React.Fragment key={index}>
                        <ListItem alignItems="flex-start">
                          <ListItemText
                            primary={
                              <Box display="flex" justifyContent="space-between">
                                <Typography variant="subtitle1">{history.diagnosis}</Typography>
                                <Typography variant="body2" color="textSecondary">
                                  {history.date}
                                </Typography>
                              </Box>
                            }
                            secondary={
                              <>
                                <Typography component="span" variant="body2" color="textPrimary">
                                  医生: {history.doctor}
                                </Typography>
                                <Typography component="span" variant="body2" display="block">
                                  医院: {history.hospital}
                                </Typography>
                              </>
                            }
                          />
                        </ListItem>
                        {index < record.medicalHistory.length - 1 && <Divider />}
                      </React.Fragment>
                    ))}
                  </List>
                ) : (
                  <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>
                    暂无病史记录
                  </Typography>
                )}
              </TabPanel>

              <TabPanel value={tabValue} index={1}>
                <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
                  <Typography variant="h6">康复记录</Typography>
                  <Button startIcon={<AddIcon />} variant="outlined" size="small">
                    添加记录
                  </Button>
                </Box>
                {record.rehabHistory && record.rehabHistory.length > 0 ? (
                  <List>
                    {record.rehabHistory.map((rehab, index) => (
                      <React.Fragment key={index}>
                        <ListItem alignItems="flex-start">
                          <ListItemText
                            primary={
                              <Box display="flex" justifyContent="space-between">
                                <Typography variant="subtitle1">{rehab.type}</Typography>
                                <Typography variant="body2" color="textSecondary">
                                  {rehab.date}
                                </Typography>
                              </Box>
                            }
                            secondary={
                              <>
                                <Typography component="span" variant="body2" color="textPrimary">
                                  详情: {rehab.details}
                                </Typography>
                                <Typography component="span" variant="body2" display="block">
                                  频率: {rehab.frequency}, 时长: {rehab.duration}
                                </Typography>
                              </>
                            }
                          />
                        </ListItem>
                        {index < record.rehabHistory.length - 1 && <Divider />}
                      </React.Fragment>
                    ))}
                  </List>
                ) : (
                  <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>
                    暂无康复记录
                  </Typography>
                )}
              </TabPanel>

              <TabPanel value={tabValue} index={2}>
                <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
                  <Typography variant="h6">用药记录</Typography>
                  <Button startIcon={<AddIcon />} variant="outlined" size="small">
                    添加记录
                  </Button>
                </Box>
                {record.medications && record.medications.length > 0 ? (
                  <List>
                    {record.medications.map((medication, index) => (
                      <React.Fragment key={index}>
                        <ListItem alignItems="flex-start">
                          <ListItemText
                            primary={
                              <Box display="flex" justifyContent="space-between">
                                <Typography variant="subtitle1">{medication.name}</Typography>
                                <Chip
                                  label={medication.endDate === '长期' ? '长期用药' : '短期用药'}
                                  color={medication.endDate === '长期' ? 'warning' : 'info'}
                                  size="small"
                                />
                              </Box>
                            }
                            secondary={
                              <>
                                <Typography component="span" variant="body2" color="textPrimary">
                                  剂量: {medication.dosage}, 频率: {medication.frequency}
                                </Typography>
                                <Typography component="span" variant="body2" display="block">
                                  开始时间: {medication.startDate}, 结束时间: {medication.endDate}
                                </Typography>
                              </>
                            }
                          />
                        </ListItem>
                        {index < record.medications.length - 1 && <Divider />}
                      </React.Fragment>
                    ))}
                  </List>
                ) : (
                  <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>
                    暂无用药记录
                  </Typography>
                )}
              </TabPanel>

              <TabPanel value={tabValue} index={3}>
                <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
                  <Typography variant="h6">生命体征</Typography>
                  <Button startIcon={<AddIcon />} variant="outlined" size="small">
                    添加记录
                  </Button>
                </Box>
                {record.vitalSigns && record.vitalSigns.length > 0 ? (
                  <List>
                    {record.vitalSigns.map((vitalSign, index) => (
                      <React.Fragment key={index}>
                        <ListItem alignItems="flex-start">
                          <ListItemText
                            disableTypography
                            primary={
                              <Box display="flex" justifyContent="space-between">
                                <Typography variant="subtitle1">{healthDataType(vitalSign) || '体征记录'}</Typography>
                                <Typography variant="body2" color="textSecondary">
                                  {formatAppDate(vitalSign.recorded_at, 'localeZh24', { assumeUtc: true, empty: '时间未提供' })}
                                </Typography>
                              </Box>
                            }
                            secondary={
                              <Box>
                                <Typography variant="body2">
                                  {healthDataValueText(healthDataPayload(vitalSign).value)} {healthDataPayload(vitalSign).unit || ''}
                                </Typography>
                                {!!healthDataQualityFlags(vitalSign).length && <Typography variant="body2" color="warning.main">
                                  数据质量标记：{healthDataQualityFlags(vitalSign).join('、')}
                                </Typography>}
                              </Box>
                            }
                          />
                        </ListItem>
                        {index < record.vitalSigns.length - 1 && <Divider />}
                      </React.Fragment>
                    ))}
                  </List>
                ) : (
                  <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>
                    暂无生命体征记录
                  </Typography>
                )}
              </TabPanel>
            </Paper>
          </Grid>
        </Grid>
      )}
    </Box>
  );
};

export default HealthRecords;

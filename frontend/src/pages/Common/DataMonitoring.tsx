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
  CircularProgress
} from '@mui/material';
import { format } from 'date-fns';
import { zhCN } from 'date-fns/locale';

// 导入组件
import HealthDataVisualization from '../../components/HealthManager/HealthDataVisualization';
import HealthDataForm from '../../components/HealthManager/HealthDataForm';

// 模拟数据
const mockPatients = [
  { id: '1', name: '张三', age: 45, gender: '男' },
  { id: '2', name: '李四', age: 32, gender: '女' },
  { id: '3', name: '王五', age: 58, gender: '男' },
  { id: '4', name: '赵六', age: 27, gender: '女' },
  { id: '5', name: '孙七', age: 62, gender: '男' }
];

// 模拟健康数据
const generateMockHealthData = (patientId: string) => {
  const today = new Date();
  const data = [];
  
  // 生成过去30天的模拟数据
  for (let i = 0; i < 30; i++) {
    const date = new Date();
    date.setDate(today.getDate() - i);
    
    // 模拟血压数据
    if (i % 2 === 0) {
      data.push({
        id: `bp-${i}`,
        patient_id: patientId,
        data_type: 'vital_signs',
        vital_sign_type: 'blood_pressure',
        value: { systolic: Math.floor(110 + Math.random() * 30), diastolic: Math.floor(70 + Math.random() * 20) },
        unit: 'mmHg',
        measured_at: format(date, "yyyy-MM-dd'T'HH:mm:ss'Z'"),
        created_at: format(date, "yyyy-MM-dd'T'HH:mm:ss'Z'"),
        created_by: 'user1',
        notes: i % 10 === 0 ? '服用降压药后测量' : ''
      });
    }
    
    // 模拟血糖数据
    if (i % 3 === 0) {
      data.push({
        id: `bs-${i}`,
        patient_id: patientId,
        data_type: 'vital_signs',
        vital_sign_type: 'blood_sugar',
        value: Math.floor(4 + Math.random() * 3 * 10) / 10,
        unit: 'mmol/L',
        measured_at: format(date, "yyyy-MM-dd'T'HH:mm:ss'Z'"),
        created_at: format(date, "yyyy-MM-dd'T'HH:mm:ss'Z'"),
        created_by: 'user1',
        notes: i % 9 === 0 ? '餐后两小时测量' : ''
      });
    }
    
    // 模拟体温数据
    if (i % 5 === 0) {
      data.push({
        id: `temp-${i}`,
        patient_id: patientId,
        data_type: 'vital_signs',
        vital_sign_type: 'temperature',
        value: 36.2 + Math.random() * 1.5,
        unit: '°C',
        measured_at: format(date, "yyyy-MM-dd'T'HH:mm:ss'Z'"),
        created_at: format(date, "yyyy-MM-dd'T'HH:mm:ss'Z'"),
        created_by: 'user1',
        notes: ''
      });
    }
    
    // 模拟心率数据
    if (i % 2 === 1) {
      data.push({
        id: `hr-${i}`,
        patient_id: patientId,
        data_type: 'vital_signs',
        vital_sign_type: 'heart_rate',
        value: Math.floor(60 + Math.random() * 30),
        unit: 'bpm',
        measured_at: format(date, "yyyy-MM-dd'T'HH:mm:ss'Z'"),
        created_at: format(date, "yyyy-MM-dd'T'HH:mm:ss'Z'"),
        created_by: 'user1',
        notes: ''
      });
    }
    
    // 模拟呼吸频率数据
    if (i % 7 === 0) {
      data.push({
        id: `rr-${i}`,
        patient_id: patientId,
        data_type: 'vital_signs',
        vital_sign_type: 'respiratory_rate',
        value: Math.floor(12 + Math.random() * 8),
        unit: 'breaths/min',
        measured_at: format(date, "yyyy-MM-dd'T'HH:mm:ss'Z'"),
        created_at: format(date, "yyyy-MM-dd'T'HH:mm:ss'Z'"),
        created_by: 'user1',
        notes: ''
      });
    }
    
    // 模拟体重数据
    if (i % 10 === 0) {
      data.push({
        id: `weight-${i}`,
        patient_id: patientId,
        data_type: 'vital_signs',
        vital_sign_type: 'weight',
        value: Math.floor(50 + Math.random() * 40 * 10) / 10,
        unit: 'kg',
        measured_at: format(date, "yyyy-MM-dd'T'HH:mm:ss'Z'"),
        created_at: format(date, "yyyy-MM-dd'T'HH:mm:ss'Z'"),
        created_by: 'user1',
        notes: ''
      });
    }
    
    // 模拟实验室检查结果
    if (i % 15 === 0) {
      data.push({
        id: `lab-${i}`,
        patient_id: patientId,
        data_type: 'lab_result',
        test_name: '血常规',
        result: {
          'WBC': `${(4 + Math.random() * 6).toFixed(2)} x10^9/L`,
          'RBC': `${(3.5 + Math.random() * 2).toFixed(2)} x10^12/L`,
          'HGB': `${(120 + Math.random() * 40).toFixed(1)} g/L`,
          'PLT': `${(150 + Math.random() * 250).toFixed(0)} x10^9/L`
        },
        reference_range: {
          'WBC': '4.0-10.0 x10^9/L',
          'RBC': '3.5-5.5 x10^12/L',
          'HGB': '120-160 g/L',
          'PLT': '100-300 x10^9/L'
        },
        measured_at: format(date, "yyyy-MM-dd'T'HH:mm:ss'Z'"),
        created_at: format(date, "yyyy-MM-dd'T'HH:mm:ss'Z'"),
        created_by: 'lab_tech_1',
        notes: ''
      });
    }
  }
  
  return data;
};

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
  const [healthData, setHealthData] = useState<any[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [tabValue, setTabValue] = useState<number>(0);
  const [showForm, setShowForm] = useState<boolean>(false);
  
  // 加载患者健康数据
  useEffect(() => {
    if (selectedPatient) {
      loadHealthData(selectedPatient);
    }
  }, [selectedPatient]);
  
  // 处理选择患者
  const handlePatientChange = (event: React.ChangeEvent<{ value: unknown }>) => {
    setSelectedPatient(event.target.value as string);
  };
  
  // 加载健康数据（模拟API调用）
  const loadHealthData = async (patientId: string) => {
    try {
      setLoading(true);
      
      // 模拟API延迟
      await new Promise(resolve => setTimeout(resolve, 800));
      
      // 获取模拟数据
      const data = generateMockHealthData(patientId);
      setHealthData(data);
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
  
  // 处理健康数据提交
  const handleHealthDataSubmit = async (data: any) => {
    try {
      setLoading(true);
      
      // 模拟API延迟
      await new Promise(resolve => setTimeout(resolve, 500));
      
      // 添加模拟ID和时间戳
      const newData = {
        id: `new-${Date.now()}`,
        patient_id: selectedPatient,
        created_at: new Date().toISOString(),
        created_by: 'current_user',
        ...data
      };
      
      // 更新本地数据
      setHealthData(prevData => [newData, ...prevData]);
      setShowForm(false);
    } catch (err) {
      setError('保存健康数据失败');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };
  
  // 获取选中患者信息
  const selectedPatientInfo = selectedPatient ? 
    mockPatients.find(p => p.id === selectedPatient) : null;
  
  // 过滤出不同类型的健康数据
  const vitalSigns = healthData.filter(data => data.data_type === 'vital_signs');
  const labResults = healthData.filter(data => data.data_type === 'lab_result');
  
  // 最新的生命体征数据
  const latestVitalSigns = {};
  vitalSigns.forEach(data => {
    const type = data.vital_sign_type;
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
                {mockPatients.map(patient => (
                  <MenuItem key={patient.id} value={patient.id}>
                    {patient.name} ({patient.gender}, {patient.age}岁)
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          </Grid>
        </Grid>
      </Paper>
      
      {!selectedPatient && (
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
                {Object.entries(latestVitalSigns).map(([type, data]: [string, any]) => {
                  let displayValue = '';
                  let displayName = '';
                  
                  switch (type) {
                    case 'blood_pressure':
                      displayName = '血压';
                      displayValue = `${data.value.systolic}/${data.value.diastolic} ${data.unit}`;
                      break;
                    case 'blood_sugar':
                      displayName = '血糖';
                      displayValue = `${data.value} ${data.unit}`;
                      break;
                    case 'temperature':
                      displayName = '体温';
                      displayValue = `${data.value.toFixed(1)} ${data.unit}`;
                      break;
                    case 'heart_rate':
                      displayName = '心率';
                      displayValue = `${data.value} ${data.unit}`;
                      break;
                    case 'respiratory_rate':
                      displayName = '呼吸频率';
                      displayValue = `${data.value} ${data.unit}`;
                      break;
                    case 'weight':
                      displayName = '体重';
                      displayValue = `${data.value} ${data.unit}`;
                      break;
                    default:
                      displayName = type;
                      displayValue = `${data.value} ${data.unit}`;
                  }
                  
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
              error={null}
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
                    let displayValue = '';
                    let displayName = '';
                    
                    switch (data.vital_sign_type) {
                      case 'blood_pressure':
                        displayName = '血压';
                        displayValue = `${data.value.systolic}/${data.value.diastolic} ${data.unit}`;
                        break;
                      case 'blood_sugar':
                        displayName = '血糖';
                        displayValue = `${data.value} ${data.unit}`;
                        break;
                      case 'temperature':
                        displayName = '体温';
                        displayValue = `${data.value.toFixed(1)} ${data.unit}`;
                        break;
                      case 'heart_rate':
                        displayName = '心率';
                        displayValue = `${data.value} ${data.unit}`;
                        break;
                      case 'respiratory_rate':
                        displayName = '呼吸频率';
                        displayValue = `${data.value} ${data.unit}`;
                        break;
                      case 'weight':
                        displayName = '体重';
                        displayValue = `${data.value} ${data.unit}`;
                        break;
                      default:
                        displayName = data.vital_sign_type;
                        displayValue = `${data.value} ${data.unit}`;
                    }
                    
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
                            label={data.test_name} 
                            color="secondary" 
                            size="small" 
                            variant="outlined" 
                          />
                          <Typography variant="caption" color="text.secondary">
                            {format(new Date(data.measured_at), 'yyyy-MM-dd HH:mm', { locale: zhCN })}
                          </Typography>
                        </Stack>
                        
                        <Grid container spacing={2} sx={{ mt: 1 }}>
                          {Object.entries(data.result).map(([key, value]) => (
                            <Grid item xs={12} sm={6} md={4} key={key}>
                              <Typography variant="body2" color="text.secondary">
                                {key}
                              </Typography>
                              <Typography variant="body1">
                                {value as string}
                              </Typography>
                              <Typography variant="caption" color="text.secondary">
                                参考范围: {data.reference_range[key] as string}
                              </Typography>
                            </Grid>
                          ))}
                        </Grid>
                        
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
                onSave={handleHealthDataSubmit}
                onCancel={() => setShowForm(false)}
                loading={loading}
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
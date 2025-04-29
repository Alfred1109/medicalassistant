import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
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
} from '@mui/material';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import EditIcon from '@mui/icons-material/Edit';
import AddIcon from '@mui/icons-material/Add';

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
      id={`health-record-tabpanel-${index}`}
      aria-labelledby={`health-record-tab-${index}`}
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

// 模拟患者数据
const mockPatients = [
  {
    id: '1',
    name: '张三',
    age: 45,
    gender: '男',
    height: 175,
    weight: 72,
    bloodType: 'A',
    allergies: ['青霉素', '花粉'],
    emergencyContact: '李四 (妻子) - 13800138000',
    medicalHistory: [
      { date: '2022-03-15', diagnosis: '腰椎间盘突出', doctor: '王医生', hospital: '仁爱医院' },
      { date: '2021-07-22', diagnosis: '高血压', doctor: '李医生', hospital: '人民医院' },
      { date: '2020-11-05', diagnosis: '感冒', doctor: '赵医生', hospital: '社区医院' },
    ],
    rehabHistory: [
      { date: '2022-04-01', type: '理疗', details: '腰椎牵引', duration: '30分钟', frequency: '每周3次' },
      { date: '2022-04-15', type: '运动治疗', details: '核心肌群稳定训练', duration: '45分钟', frequency: '每周5次' },
      { date: '2022-05-10', type: '按摩治疗', details: '腰部肌肉放松', duration: '60分钟', frequency: '每周2次' },
    ],
    medications: [
      { name: '布洛芬', dosage: '200mg', frequency: '每日2次', startDate: '2022-03-20', endDate: '2022-04-20' },
      { name: '肌松剂', dosage: '10mg', frequency: '每晚1次', startDate: '2022-03-20', endDate: '长期' },
    ],
    vitalSigns: [
      { date: '2022-05-15', bp: '120/80', pulse: 72, temp: 36.5, respRate: 16, weight: 72 },
      { date: '2022-04-30', bp: '125/85', pulse: 75, temp: 36.7, respRate: 17, weight: 73 },
      { date: '2022-04-15', bp: '130/85', pulse: 78, temp: 36.6, respRate: 16, weight: 74 },
    ]
  },
  // 可以添加更多患者数据
];

const HealthRecords: React.FC = () => {
  const { patientId } = useParams<{ patientId: string }>();
  const navigate = useNavigate();
  const [tabValue, setTabValue] = useState(0);
  const [patient, setPatient] = useState<any>(null);
  const [editMedicalDialogOpen, setEditMedicalDialogOpen] = useState(false);
  const [editMedicationDialogOpen, setEditMedicationDialogOpen] = useState(false);
  const [selectedRecord, setSelectedRecord] = useState<any>(null);

  useEffect(() => {
    // 在实际应用中，这里会从API获取数据
    if (patientId) {
      const foundPatient = mockPatients.find(p => p.id === patientId);
      if (foundPatient) {
        setPatient(foundPatient);
      }
    }
  }, [patientId]);

  const handleTabChange = (event: React.SyntheticEvent, newValue: number) => {
    setTabValue(newValue);
  };

  const handleBack = () => {
    navigate('/doctor/patients');
  };

  const handleOpenMedicalDialog = (record: any = null) => {
    setSelectedRecord(record);
    setEditMedicalDialogOpen(true);
  };

  const handleOpenMedicationDialog = (medication: any = null) => {
    setSelectedRecord(medication);
    setEditMedicationDialogOpen(true);
  };

  const handleCloseMedicalDialog = () => {
    setEditMedicalDialogOpen(false);
    setSelectedRecord(null);
  };

  const handleCloseMedicationDialog = () => {
    setEditMedicationDialogOpen(false);
    setSelectedRecord(null);
  };

  if (!patient) {
    return (
      <Box>
        <Typography variant="h5">未找到患者信息</Typography>
        <Button startIcon={<ArrowBackIcon />} onClick={handleBack} sx={{ mt: 2 }}>
          返回患者列表
        </Button>
      </Box>
    );
  }

  return (
    <Box>
      <Box display="flex" alignItems="center" mb={3}>
        <IconButton onClick={handleBack} sx={{ mr: 1 }}>
          <ArrowBackIcon />
        </IconButton>
        <Typography variant="h5" component="h1">
          {patient.name}的健康档案
        </Typography>
      </Box>
      
      <Paper sx={{ width: '100%', mt: 2 }}>
        <Tabs
          value={tabValue}
          onChange={handleTabChange}
          indicatorColor="primary"
          textColor="primary"
          variant="fullWidth"
        >
          <Tab label="基本信息" />
          <Tab label="病史记录" />
          <Tab label="康复历史" />
          <Tab label="用药情况" />
          <Tab label="生命体征" />
        </Tabs>
        
        <TabPanel value={tabValue} index={0}>
          <Grid container spacing={3}>
            <Grid item xs={12} md={6}>
              <Card>
                <CardContent>
                  <Typography variant="h6" gutterBottom>个人信息</Typography>
                  <Divider sx={{ mb: 2 }} />
                  
                  <Grid container spacing={2}>
                    <Grid item xs={6}>
                      <Typography variant="subtitle2" color="text.secondary">姓名</Typography>
                      <Typography variant="body1">{patient.name}</Typography>
                    </Grid>
                    <Grid item xs={6}>
                      <Typography variant="subtitle2" color="text.secondary">年龄</Typography>
                      <Typography variant="body1">{patient.age}岁</Typography>
                    </Grid>
                    <Grid item xs={6}>
                      <Typography variant="subtitle2" color="text.secondary">性别</Typography>
                      <Typography variant="body1">{patient.gender}</Typography>
                    </Grid>
                    <Grid item xs={6}>
                      <Typography variant="subtitle2" color="text.secondary">血型</Typography>
                      <Typography variant="body1">{patient.bloodType}型</Typography>
                    </Grid>
                    <Grid item xs={6}>
                      <Typography variant="subtitle2" color="text.secondary">身高</Typography>
                      <Typography variant="body1">{patient.height} cm</Typography>
                    </Grid>
                    <Grid item xs={6}>
                      <Typography variant="subtitle2" color="text.secondary">体重</Typography>
                      <Typography variant="body1">{patient.weight} kg</Typography>
                    </Grid>
                  </Grid>
                </CardContent>
              </Card>
            </Grid>
            
            <Grid item xs={12} md={6}>
              <Card sx={{ height: '100%' }}>
                <CardContent>
                  <Typography variant="h6" gutterBottom>其他信息</Typography>
                  <Divider sx={{ mb: 2 }} />
                  
                  <Typography variant="subtitle2" color="text.secondary" gutterBottom>过敏史</Typography>
                  <Box mb={2}>
                    {patient.allergies.length > 0 ? (
                      patient.allergies.map((allergy: string, index: number) => (
                        <Chip key={index} label={allergy} color="warning" size="small" sx={{ mr: 1 }} />
                      ))
                    ) : (
                      <Typography variant="body2">无</Typography>
                    )}
                  </Box>
                  
                  <Typography variant="subtitle2" color="text.secondary" gutterBottom>紧急联系人</Typography>
                  <Typography variant="body1">{patient.emergencyContact}</Typography>
                </CardContent>
              </Card>
            </Grid>
          </Grid>
        </TabPanel>
        
        <TabPanel value={tabValue} index={1}>
          <Box display="flex" justifyContent="flex-end" mb={2}>
            <Button 
              startIcon={<AddIcon />} 
              variant="contained" 
              color="primary"
              onClick={() => handleOpenMedicalDialog()}
            >
              添加新记录
            </Button>
          </Box>
          <List>
            {patient.medicalHistory.map((record: any, index: number) => (
              <React.Fragment key={index}>
                <ListItem 
                  alignItems="flex-start"
                  secondaryAction={
                    <IconButton edge="end" aria-label="编辑" onClick={() => handleOpenMedicalDialog(record)}>
                      <EditIcon />
                    </IconButton>
                  }
                >
                  <ListItemText
                    primary={
                      <Box display="flex" justifyContent="space-between">
                        <Typography variant="subtitle1">{record.diagnosis}</Typography>
                        <Typography variant="body2" color="text.secondary">{record.date}</Typography>
                      </Box>
                    }
                    secondary={
                      <>
                        <Typography variant="body2" component="span">
                          {`主治医生: ${record.doctor}`}
                        </Typography>
                        <br />
                        <Typography variant="body2" component="span">
                          {`就诊医院: ${record.hospital}`}
                        </Typography>
                      </>
                    }
                  />
                </ListItem>
                {index < patient.medicalHistory.length - 1 && <Divider variant="inset" component="li" />}
              </React.Fragment>
            ))}
          </List>
        </TabPanel>
        
        <TabPanel value={tabValue} index={2}>
          <List>
            {patient.rehabHistory.map((record: any, index: number) => (
              <React.Fragment key={index}>
                <ListItem alignItems="flex-start">
                  <ListItemText
                    primary={
                      <Box display="flex" justifyContent="space-between">
                        <Typography variant="subtitle1">{record.type}</Typography>
                        <Typography variant="body2" color="text.secondary">{record.date}</Typography>
                      </Box>
                    }
                    secondary={
                      <>
                        <Typography variant="body2" component="span">
                          {`详情: ${record.details}`}
                        </Typography>
                        <br />
                        <Typography variant="body2" component="span">
                          {`时长: ${record.duration} | 频率: ${record.frequency}`}
                        </Typography>
                      </>
                    }
                  />
                </ListItem>
                {index < patient.rehabHistory.length - 1 && <Divider variant="inset" component="li" />}
              </React.Fragment>
            ))}
          </List>
        </TabPanel>
        
        <TabPanel value={tabValue} index={3}>
          <Box display="flex" justifyContent="flex-end" mb={2}>
            <Button 
              startIcon={<AddIcon />} 
              variant="contained" 
              color="primary"
              onClick={() => handleOpenMedicationDialog()}
            >
              添加用药
            </Button>
          </Box>
          <List>
            {patient.medications.map((med: any, index: number) => (
              <React.Fragment key={index}>
                <ListItem 
                  alignItems="flex-start"
                  secondaryAction={
                    <IconButton edge="end" aria-label="编辑" onClick={() => handleOpenMedicationDialog(med)}>
                      <EditIcon />
                    </IconButton>
                  }
                >
                  <ListItemText
                    primary={
                      <Box display="flex" justifyContent="space-between">
                        <Typography variant="subtitle1">{med.name}</Typography>
                        <Chip 
                          label={med.endDate === '长期' ? '长期用药' : '阶段用药'} 
                          color={med.endDate === '长期' ? 'primary' : 'default'} 
                          size="small" 
                        />
                      </Box>
                    }
                    secondary={
                      <>
                        <Typography variant="body2" component="span">
                          {`剂量: ${med.dosage} | 频率: ${med.frequency}`}
                        </Typography>
                        <br />
                        <Typography variant="body2" component="span">
                          {`开始日期: ${med.startDate} | 结束日期: ${med.endDate}`}
                        </Typography>
                      </>
                    }
                  />
                </ListItem>
                {index < patient.medications.length - 1 && <Divider variant="inset" component="li" />}
              </React.Fragment>
            ))}
          </List>
        </TabPanel>
        
        <TabPanel value={tabValue} index={4}>
          <Grid container spacing={2}>
            <Grid item xs={12}>
              <Typography variant="h6" gutterBottom>近期生命体征记录</Typography>
            </Grid>
            {patient.vitalSigns.map((vital: any, index: number) => (
              <Grid item xs={12} md={4} key={index}>
                <Card>
                  <CardContent>
                    <Typography variant="subtitle1" gutterBottom>
                      {vital.date}
                    </Typography>
                    <Divider sx={{ mb: 2 }} />
                    
                    <Box display="flex" justifyContent="space-between" mb={1}>
                      <Typography variant="body2" color="text.secondary">血压</Typography>
                      <Typography variant="body1">{vital.bp} mmHg</Typography>
                    </Box>
                    
                    <Box display="flex" justifyContent="space-between" mb={1}>
                      <Typography variant="body2" color="text.secondary">脉搏</Typography>
                      <Typography variant="body1">{vital.pulse} bpm</Typography>
                    </Box>
                    
                    <Box display="flex" justifyContent="space-between" mb={1}>
                      <Typography variant="body2" color="text.secondary">体温</Typography>
                      <Typography variant="body1">{vital.temp} ℃</Typography>
                    </Box>
                    
                    <Box display="flex" justifyContent="space-between" mb={1}>
                      <Typography variant="body2" color="text.secondary">呼吸频率</Typography>
                      <Typography variant="body1">{vital.respRate} 次/分</Typography>
                    </Box>
                    
                    <Box display="flex" justifyContent="space-between">
                      <Typography variant="body2" color="text.secondary">体重</Typography>
                      <Typography variant="body1">{vital.weight} kg</Typography>
                    </Box>
                  </CardContent>
                </Card>
              </Grid>
            ))}
          </Grid>
        </TabPanel>
      </Paper>

      {/* 编辑病史记录对话框 */}
      <Dialog open={editMedicalDialogOpen} onClose={handleCloseMedicalDialog} maxWidth="sm" fullWidth>
        <DialogTitle>{selectedRecord ? '编辑病史记录' : '添加病史记录'}</DialogTitle>
        <DialogContent>
          <Grid container spacing={2} sx={{ mt: 1 }}>
            <Grid item xs={12}>
              <TextField
                fullWidth
                label="诊断"
                defaultValue={selectedRecord?.diagnosis || ''}
              />
            </Grid>
            <Grid item xs={12}>
              <TextField
                fullWidth
                label="就诊日期"
                type="date"
                defaultValue={selectedRecord?.date || new Date().toISOString().split('T')[0]}
                InputLabelProps={{
                  shrink: true,
                }}
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="主治医生"
                defaultValue={selectedRecord?.doctor || ''}
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="就诊医院"
                defaultValue={selectedRecord?.hospital || ''}
              />
            </Grid>
          </Grid>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCloseMedicalDialog}>取消</Button>
          <Button onClick={handleCloseMedicalDialog} variant="contained" color="primary">
            保存
          </Button>
        </DialogActions>
      </Dialog>

      {/* 编辑用药情况对话框 */}
      <Dialog open={editMedicationDialogOpen} onClose={handleCloseMedicationDialog} maxWidth="sm" fullWidth>
        <DialogTitle>{selectedRecord ? '编辑用药情况' : '添加用药情况'}</DialogTitle>
        <DialogContent>
          <Grid container spacing={2} sx={{ mt: 1 }}>
            <Grid item xs={12}>
              <TextField
                fullWidth
                label="药物名称"
                defaultValue={selectedRecord?.name || ''}
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="剂量"
                defaultValue={selectedRecord?.dosage || ''}
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="频率"
                defaultValue={selectedRecord?.frequency || ''}
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="开始日期"
                type="date"
                defaultValue={selectedRecord?.startDate || new Date().toISOString().split('T')[0]}
                InputLabelProps={{
                  shrink: true,
                }}
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="结束日期"
                defaultValue={selectedRecord?.endDate === '长期' ? '' : selectedRecord?.endDate}
                placeholder="留空表示长期用药"
              />
            </Grid>
          </Grid>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCloseMedicationDialog}>取消</Button>
          <Button onClick={handleCloseMedicationDialog} variant="contained" color="primary">
            保存
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default HealthRecords; 
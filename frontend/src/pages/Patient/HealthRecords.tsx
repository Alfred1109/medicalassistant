import React, { useState } from 'react';
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
} from '@mui/material';

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

// 模拟数据
const basicInfo = {
  name: '张三',
  age: 45,
  gender: '男',
  height: 175,
  weight: 72,
  bloodType: 'A',
  allergies: ['青霉素', '花粉'],
  emergencyContact: '李四 (妻子) - 13800138000',
};

const medicalHistory = [
  { date: '2022-03-15', diagnosis: '腰椎间盘突出', doctor: '王医生', hospital: '仁爱医院' },
  { date: '2021-07-22', diagnosis: '高血压', doctor: '李医生', hospital: '人民医院' },
  { date: '2020-11-05', diagnosis: '感冒', doctor: '赵医生', hospital: '社区医院' },
];

const rehabHistory = [
  { date: '2022-04-01', type: '理疗', details: '腰椎牵引', duration: '30分钟', frequency: '每周3次' },
  { date: '2022-04-15', type: '运动治疗', details: '核心肌群稳定训练', duration: '45分钟', frequency: '每周5次' },
  { date: '2022-05-10', type: '按摩治疗', details: '腰部肌肉放松', duration: '60分钟', frequency: '每周2次' },
];

const currentMedications = [
  { name: '布洛芬', dosage: '200mg', frequency: '每日2次', startDate: '2022-03-20', endDate: '2022-04-20' },
  { name: '肌松剂', dosage: '10mg', frequency: '每晚1次', startDate: '2022-03-20', endDate: '长期' },
];

const HealthRecords: React.FC = () => {
  const [tabValue, setTabValue] = useState(0);

  const handleTabChange = (event: React.SyntheticEvent, newValue: number) => {
    setTabValue(newValue);
  };

  return (
    <Box>
      <Typography variant="h5" gutterBottom>
        健康档案
      </Typography>
      
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
                      <Typography variant="body1">{basicInfo.name}</Typography>
                    </Grid>
                    <Grid item xs={6}>
                      <Typography variant="subtitle2" color="text.secondary">年龄</Typography>
                      <Typography variant="body1">{basicInfo.age}岁</Typography>
                    </Grid>
                    <Grid item xs={6}>
                      <Typography variant="subtitle2" color="text.secondary">性别</Typography>
                      <Typography variant="body1">{basicInfo.gender}</Typography>
                    </Grid>
                    <Grid item xs={6}>
                      <Typography variant="subtitle2" color="text.secondary">血型</Typography>
                      <Typography variant="body1">{basicInfo.bloodType}型</Typography>
                    </Grid>
                    <Grid item xs={6}>
                      <Typography variant="subtitle2" color="text.secondary">身高</Typography>
                      <Typography variant="body1">{basicInfo.height} cm</Typography>
                    </Grid>
                    <Grid item xs={6}>
                      <Typography variant="subtitle2" color="text.secondary">体重</Typography>
                      <Typography variant="body1">{basicInfo.weight} kg</Typography>
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
                    {basicInfo.allergies.length > 0 ? (
                      basicInfo.allergies.map((allergy, index) => (
                        <Chip key={index} label={allergy} color="warning" size="small" sx={{ mr: 1 }} />
                      ))
                    ) : (
                      <Typography variant="body2">无</Typography>
                    )}
                  </Box>
                  
                  <Typography variant="subtitle2" color="text.secondary" gutterBottom>紧急联系人</Typography>
                  <Typography variant="body1">{basicInfo.emergencyContact}</Typography>
                </CardContent>
              </Card>
            </Grid>
          </Grid>
        </TabPanel>
        
        <TabPanel value={tabValue} index={1}>
          <List>
            {medicalHistory.map((record, index) => (
              <React.Fragment key={index}>
                <ListItem alignItems="flex-start">
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
                {index < medicalHistory.length - 1 && <Divider variant="inset" component="li" />}
              </React.Fragment>
            ))}
          </List>
        </TabPanel>
        
        <TabPanel value={tabValue} index={2}>
          <List>
            {rehabHistory.map((record, index) => (
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
                {index < rehabHistory.length - 1 && <Divider variant="inset" component="li" />}
              </React.Fragment>
            ))}
          </List>
        </TabPanel>
        
        <TabPanel value={tabValue} index={3}>
          <List>
            {currentMedications.map((med, index) => (
              <React.Fragment key={index}>
                <ListItem alignItems="flex-start">
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
                {index < currentMedications.length - 1 && <Divider variant="inset" component="li" />}
              </React.Fragment>
            ))}
          </List>
        </TabPanel>
      </Paper>
    </Box>
  );
};

export default HealthRecords; 
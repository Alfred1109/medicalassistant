import React from 'react';
import {
  Box,
  Typography,
  Button,
  Paper,
  Grid,
  TextField,
  InputAdornment,
  Chip,
  IconButton,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Tabs,
  Tab,
} from '@mui/material';
import SearchIcon from '@mui/icons-material/Search';
import AddIcon from '@mui/icons-material/Add';
import EditIcon from '@mui/icons-material/Edit';
import DeleteIcon from '@mui/icons-material/Delete';
import VisibilityIcon from '@mui/icons-material/Visibility';
import FilterListIcon from '@mui/icons-material/FilterList';
import AssignmentIndIcon from '@mui/icons-material/AssignmentInd';

// 模拟患者数据
const mockPatients = [
  {
    id: 'P001',
    name: '张三',
    age: 45,
    gender: '男',
    contactNumber: '13800138001',
    email: 'zhangsan@example.com',
    address: '北京市海淀区',
    diagnosis: '腰椎间盘突出',
    doctorAssigned: '王医生',
    treatmentPlan: '物理治疗',
    admissionDate: '2023-05-01',
    status: '接受治疗中'
  },
  {
    id: 'P002',
    name: '李四',
    age: 58,
    gender: '男',
    contactNumber: '13800138002',
    email: 'lisi@example.com',
    address: '北京市朝阳区',
    diagnosis: '膝关节退行性病变',
    doctorAssigned: '赵医生',
    treatmentPlan: '康复训练',
    admissionDate: '2023-04-15',
    status: '接受治疗中'
  },
  {
    id: 'P003',
    name: '王五',
    age: 35,
    gender: '女',
    contactNumber: '13800138003',
    email: 'wangwu@example.com',
    address: '上海市浦东新区',
    diagnosis: '颈椎病',
    doctorAssigned: '李医生',
    treatmentPlan: '针灸+康复训练',
    admissionDate: '2023-05-10',
    status: '接受治疗中'
  },
  {
    id: 'P004',
    name: '赵六',
    age: 62,
    gender: '男',
    contactNumber: '13800138004',
    email: 'zhaoliu@example.com',
    address: '广州市天河区',
    diagnosis: '脑卒中后遗症',
    doctorAssigned: '钱医生',
    treatmentPlan: '综合康复训练',
    admissionDate: '2023-03-20',
    status: '康复中'
  },
  {
    id: 'P005',
    name: '钱七',
    age: 28,
    gender: '女',
    contactNumber: '13800138005',
    email: 'qianqi@example.com',
    address: '深圳市南山区',
    diagnosis: '运动损伤',
    doctorAssigned: '孙医生',
    treatmentPlan: '物理治疗+康复训练',
    admissionDate: '2023-05-20',
    status: '接受治疗中'
  }
];

// 模拟医生列表
const doctors = [
  { id: 'D001', name: '王医生', department: '康复科' },
  { id: 'D002', name: '李医生', department: '神经内科' },
  { id: 'D003', name: '赵医生', department: '骨科' },
  { id: 'D004', name: '钱医生', department: '康复科' },
  { id: 'D005', name: '孙医生', department: '康复科' },
];

// 模拟康复计划列表
const treatmentPlans = [
  '物理治疗',
  '康复训练',
  '针灸治疗',
  '综合康复训练',
  '运动康复',
  '神经康复'
];

const PatientManagement: React.FC = () => {
  const [patients, setPatients] = React.useState(mockPatients);
  const [filteredPatients, setFilteredPatients] = React.useState(mockPatients);
  const [searchTerm, setSearchTerm] = React.useState('');
  const [openDialog, setOpenDialog] = React.useState(false);
  const [selectedPatient, setSelectedPatient] = React.useState<any>(null);
  const [filterStatus, setFilterStatus] = React.useState('全部');
  const [tabValue, setTabValue] = React.useState(0);
  const [detailDialog, setDetailDialog] = React.useState(false);

  React.useEffect(() => {
    filterPatients();
  }, [searchTerm, filterStatus]);

  const filterPatients = () => {
    let filtered = patients;
    
    // 根据状态筛选
    if (filterStatus !== '全部') {
      filtered = filtered.filter(patient => patient.status === filterStatus);
    }
    
    // 根据搜索词筛选
    if (searchTerm) {
      filtered = filtered.filter(patient =>
        patient.name.includes(searchTerm) ||
        patient.id.includes(searchTerm) ||
        patient.diagnosis.includes(searchTerm) ||
        patient.doctorAssigned.includes(searchTerm)
      );
    }
    
    setFilteredPatients(filtered);
  };

  const handleSearchChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    setSearchTerm(event.target.value);
  };

  const handleAddPatient = () => {
    setSelectedPatient(null);
    setOpenDialog(true);
  };

  const handleEditPatient = (patient: any) => {
    setSelectedPatient(patient);
    setOpenDialog(true);
  };

  const handleViewPatient = (patient: any) => {
    setSelectedPatient(patient);
    setDetailDialog(true);
  };

  const handleDeletePatient = (patientId: string) => {
    setPatients(patients.filter(patient => patient.id !== patientId));
    setFilteredPatients(filteredPatients.filter(patient => patient.id !== patientId));
  };

  const handleCloseDialog = () => {
    setOpenDialog(false);
    setDetailDialog(false);
    setSelectedPatient(null);
  };

  const handleSavePatient = () => {
    // 这里会处理添加/编辑患者的逻辑
    handleCloseDialog();
  };

  const handleFilterStatusChange = (event: React.ChangeEvent<{ value: unknown }>) => {
    setFilterStatus(event.target.value as string);
  };

  const handleTabChange = (event: React.SyntheticEvent, newValue: number) => {
    setTabValue(newValue);
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case '接受治疗中':
        return 'primary';
      case '康复中':
        return 'info';
      case '已康复':
        return 'success';
      case '转诊':
        return 'warning';
      case '中止治疗':
        return 'error';
      default:
        return 'default';
    }
  };

  return (
    <Box>
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
        <Typography variant="h5" component="h1">
          患者管理
        </Typography>
        <Button 
          variant="contained" 
          color="primary" 
          startIcon={<AddIcon />}
          onClick={handleAddPatient}
        >
          添加患者
        </Button>
      </Box>

      <Paper sx={{ p: 2, mb: 3 }}>
        <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
          <TextField
            placeholder="搜索患者姓名、ID、诊断或医生..."
            variant="outlined"
            size="small"
            value={searchTerm}
            onChange={handleSearchChange}
            InputProps={{
              startAdornment: (
                <InputAdornment position="start">
                  <SearchIcon />
                </InputAdornment>
              ),
            }}
            sx={{ width: 300 }}
          />
          <Box display="flex" alignItems="center">
            <FilterListIcon sx={{ mr: 1 }} />
            <FormControl variant="outlined" size="small" sx={{ width: 150 }}>
              <InputLabel>状态</InputLabel>
              <Select
                value={filterStatus}
                onChange={handleFilterStatusChange}
                label="状态"
              >
                <MenuItem value="全部">全部</MenuItem>
                <MenuItem value="接受治疗中">接受治疗中</MenuItem>
                <MenuItem value="康复中">康复中</MenuItem>
                <MenuItem value="已康复">已康复</MenuItem>
                <MenuItem value="转诊">转诊</MenuItem>
                <MenuItem value="中止治疗">中止治疗</MenuItem>
              </Select>
            </FormControl>
          </Box>
        </Box>

        <Tabs value={tabValue} onChange={handleTabChange} sx={{ borderBottom: 1, borderColor: 'divider' }}>
          <Tab label="列表视图" />
          <Tab label="卡片视图" />
        </Tabs>

        <Box sx={{ mt: 2 }}>
          {tabValue === 0 ? (
            <TableContainer>
              <Table>
                <TableHead>
                  <TableRow>
                    <TableCell>患者ID</TableCell>
                    <TableCell>姓名</TableCell>
                    <TableCell>年龄/性别</TableCell>
                    <TableCell>诊断</TableCell>
                    <TableCell>主治医生</TableCell>
                    <TableCell>治疗方案</TableCell>
                    <TableCell>状态</TableCell>
                    <TableCell align="right">操作</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {filteredPatients.map((patient) => (
                    <TableRow key={patient.id}>
                      <TableCell>{patient.id}</TableCell>
                      <TableCell>{patient.name}</TableCell>
                      <TableCell>{`${patient.age}岁/${patient.gender}`}</TableCell>
                      <TableCell>{patient.diagnosis}</TableCell>
                      <TableCell>{patient.doctorAssigned}</TableCell>
                      <TableCell>{patient.treatmentPlan}</TableCell>
                      <TableCell>
                        <Chip 
                          label={patient.status} 
                          color={getStatusColor(patient.status) as any} 
                          size="small"
                        />
                      </TableCell>
                      <TableCell align="right">
                        <IconButton 
                          size="small" 
                          color="primary"
                          onClick={() => handleViewPatient(patient)}
                        >
                          <VisibilityIcon fontSize="small" />
                        </IconButton>
                        <IconButton 
                          size="small" 
                          color="primary"
                          onClick={() => handleEditPatient(patient)}
                        >
                          <EditIcon fontSize="small" />
                        </IconButton>
                        <IconButton 
                          size="small" 
                          color="error"
                          onClick={() => handleDeletePatient(patient.id)}
                        >
                          <DeleteIcon fontSize="small" />
                        </IconButton>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          ) : (
            <Grid container spacing={2} sx={{ mt: 1 }}>
              {filteredPatients.map((patient) => (
                <Grid item xs={12} sm={6} md={4} key={patient.id}>
                  <Paper sx={{ p: 2 }}>
                    <Box display="flex" justifyContent="space-between" alignItems="center" mb={1}>
                      <Typography variant="h6">{patient.name}</Typography>
                      <Chip 
                        label={patient.status} 
                        color={getStatusColor(patient.status) as any} 
                        size="small"
                      />
                    </Box>
                    <Typography variant="body2" color="text.secondary" gutterBottom>
                      ID: {patient.id} | {patient.age}岁 | {patient.gender}
                    </Typography>
                    <Typography variant="body2" gutterBottom>
                      <strong>诊断:</strong> {patient.diagnosis}
                    </Typography>
                    <Typography variant="body2" gutterBottom>
                      <strong>主治医生:</strong> {patient.doctorAssigned}
                    </Typography>
                    <Typography variant="body2" gutterBottom>
                      <strong>治疗方案:</strong> {patient.treatmentPlan}
                    </Typography>
                    <Typography variant="body2" gutterBottom>
                      <strong>入院日期:</strong> {patient.admissionDate}
                    </Typography>
                    <Box display="flex" justifyContent="flex-end" mt={2}>
                      <IconButton 
                        size="small" 
                        color="primary"
                        onClick={() => handleViewPatient(patient)}
                      >
                        <VisibilityIcon fontSize="small" />
                      </IconButton>
                      <IconButton 
                        size="small" 
                        color="primary"
                        onClick={() => handleEditPatient(patient)}
                      >
                        <EditIcon fontSize="small" />
                      </IconButton>
                      <IconButton 
                        size="small" 
                        color="error"
                        onClick={() => handleDeletePatient(patient.id)}
                      >
                        <DeleteIcon fontSize="small" />
                      </IconButton>
                    </Box>
                  </Paper>
                </Grid>
              ))}
            </Grid>
          )}
        </Box>
      </Paper>

      {/* 患者详细信息对话框 */}
      <Dialog open={detailDialog} onClose={handleCloseDialog} maxWidth="md" fullWidth>
        <DialogTitle>
          患者详细信息
        </DialogTitle>
        <DialogContent>
          {selectedPatient && (
            <Grid container spacing={2}>
              <Grid item xs={12}>
                <Box display="flex" alignItems="center" mb={2}>
                  <AssignmentIndIcon sx={{ fontSize: 40, mr: 2, color: 'primary.main' }} />
                  <Box>
                    <Typography variant="h6">{selectedPatient.name}</Typography>
                    <Typography variant="body2" color="text.secondary">
                      ID: {selectedPatient.id} | {selectedPatient.age}岁 | {selectedPatient.gender}
                    </Typography>
                  </Box>
                </Box>
              </Grid>
              <Grid item xs={12} sm={6}>
                <Typography variant="subtitle2" gutterBottom>基本信息</Typography>
                <Typography variant="body2" gutterBottom>
                  <strong>联系电话:</strong> {selectedPatient.contactNumber}
                </Typography>
                <Typography variant="body2" gutterBottom>
                  <strong>电子邮箱:</strong> {selectedPatient.email}
                </Typography>
                <Typography variant="body2" gutterBottom>
                  <strong>居住地址:</strong> {selectedPatient.address}
                </Typography>
              </Grid>
              <Grid item xs={12} sm={6}>
                <Typography variant="subtitle2" gutterBottom>医疗信息</Typography>
                <Typography variant="body2" gutterBottom>
                  <strong>诊断:</strong> {selectedPatient.diagnosis}
                </Typography>
                <Typography variant="body2" gutterBottom>
                  <strong>主治医生:</strong> {selectedPatient.doctorAssigned}
                </Typography>
                <Typography variant="body2" gutterBottom>
                  <strong>治疗方案:</strong> {selectedPatient.treatmentPlan}
                </Typography>
              </Grid>
              <Grid item xs={12}>
                <Typography variant="subtitle2" gutterBottom>治疗记录</Typography>
                <Typography variant="body2">
                  <strong>入院日期:</strong> {selectedPatient.admissionDate}
                </Typography>
                <Typography variant="body2">
                  <strong>当前状态:</strong> {selectedPatient.status}
                </Typography>
              </Grid>
            </Grid>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCloseDialog}>关闭</Button>
          <Button 
            variant="contained" 
            color="primary"
            onClick={() => {
              handleCloseDialog();
              handleEditPatient(selectedPatient);
            }}
          >
            编辑信息
          </Button>
        </DialogActions>
      </Dialog>

      {/* 添加/编辑患者对话框 */}
      <Dialog open={openDialog} onClose={handleCloseDialog} maxWidth="md" fullWidth>
        <DialogTitle>
          {selectedPatient ? '编辑患者信息' : '添加新患者'}
        </DialogTitle>
        <DialogContent>
          <Grid container spacing={2} sx={{ mt: 1 }}>
            <Grid item xs={12} sm={6}>
              <TextField
                label="姓名"
                fullWidth
                defaultValue={selectedPatient?.name || ''}
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                label="患者ID"
                fullWidth
                defaultValue={selectedPatient?.id || ''}
                disabled={!!selectedPatient}
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                label="年龄"
                type="number"
                fullWidth
                defaultValue={selectedPatient?.age || ''}
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <FormControl fullWidth>
                <InputLabel>性别</InputLabel>
                <Select
                  label="性别"
                  defaultValue={selectedPatient?.gender || ''}
                >
                  <MenuItem value="男">男</MenuItem>
                  <MenuItem value="女">女</MenuItem>
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                label="联系电话"
                fullWidth
                defaultValue={selectedPatient?.contactNumber || ''}
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                label="电子邮箱"
                fullWidth
                defaultValue={selectedPatient?.email || ''}
              />
            </Grid>
            <Grid item xs={12}>
              <TextField
                label="居住地址"
                fullWidth
                defaultValue={selectedPatient?.address || ''}
              />
            </Grid>
            <Grid item xs={12}>
              <TextField
                label="诊断"
                fullWidth
                defaultValue={selectedPatient?.diagnosis || ''}
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <FormControl fullWidth>
                <InputLabel>主治医生</InputLabel>
                <Select
                  label="主治医生"
                  defaultValue={selectedPatient?.doctorAssigned || ''}
                >
                  {doctors.map(doctor => (
                    <MenuItem key={doctor.id} value={doctor.name}>
                      {doctor.name} - {doctor.department}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} sm={6}>
              <FormControl fullWidth>
                <InputLabel>治疗方案</InputLabel>
                <Select
                  label="治疗方案"
                  defaultValue={selectedPatient?.treatmentPlan || ''}
                >
                  {treatmentPlans.map(plan => (
                    <MenuItem key={plan} value={plan}>
                      {plan}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                label="入院日期"
                type="date"
                fullWidth
                InputLabelProps={{ shrink: true }}
                defaultValue={selectedPatient?.admissionDate || new Date().toISOString().substr(0, 10)}
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <FormControl fullWidth>
                <InputLabel>状态</InputLabel>
                <Select
                  label="状态"
                  defaultValue={selectedPatient?.status || '接受治疗中'}
                >
                  <MenuItem value="接受治疗中">接受治疗中</MenuItem>
                  <MenuItem value="康复中">康复中</MenuItem>
                  <MenuItem value="已康复">已康复</MenuItem>
                  <MenuItem value="转诊">转诊</MenuItem>
                  <MenuItem value="中止治疗">中止治疗</MenuItem>
                </Select>
              </FormControl>
            </Grid>
          </Grid>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCloseDialog}>取消</Button>
          <Button onClick={handleSavePatient} variant="contained" color="primary">
            保存
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default PatientManagement; 
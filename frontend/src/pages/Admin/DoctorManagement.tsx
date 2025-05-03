import React, { useState, useEffect } from 'react';
import {
  Box,
  Typography,
  Button,
  Paper,
  IconButton,
  Chip,
  TextField,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Grid,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Avatar,
  ListItemAvatar,
  ListItemText,
  List,
  ListItem,
  Divider,
  Tabs,
  Tab,
  Stack,
  CircularProgress
} from '@mui/material';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableContainer from '@mui/material/TableContainer';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import InputAdornment from '@mui/material/InputAdornment';
import SearchIcon from '@mui/icons-material/Search';
import AddIcon from '@mui/icons-material/Add';
import EditIcon from '@mui/icons-material/Edit';
import DeleteIcon from '@mui/icons-material/Delete';
import MoreVertIcon from '@mui/icons-material/MoreVert';
import FilterListIcon from '@mui/icons-material/FilterList';
import LocalHospitalIcon from '@mui/icons-material/LocalHospital';
import PersonIcon from '@mui/icons-material/Person';
import AlternateEmailIcon from '@mui/icons-material/AlternateEmail';
import PhoneIcon from '@mui/icons-material/Phone';
import WorkIcon from '@mui/icons-material/Work';
import EventIcon from '@mui/icons-material/Event';
import ArrowForwardIosIcon from '@mui/icons-material/ArrowForwardIos';
import PeopleIcon from '@mui/icons-material/People';
import { apiService } from '../../services/api';
import { Doctor } from '../../types/doctor.types';

// 模拟部门数据
const departments = [
  '全部',
  '骨科',
  '神经内科',
  '康复科',
  '内科',
  '外科',
  '儿科',
  '妇科',
];

// 模拟职称数据
const titles = ['全部', '主任医师', '副主任医师', '主治医师', '住院医师'];

const DoctorManagement: React.FC = () => {
  // 状态管理
  const [isLoading, setIsLoading] = useState(true);
  const [doctors, setDoctors] = useState<Doctor[]>([]);
  const [filteredDoctors, setFilteredDoctors] = useState<Doctor[]>([]);
  const [searchTerm, setSearchTerm] = useState('');
  const [openDialog, setOpenDialog] = useState(false);
  const [selectedDoctor, setSelectedDoctor] = useState<Doctor | null>(null);
  const [filterDepartment, setFilterDepartment] = useState('全部');
  const [filterTitle, setFilterTitle] = useState('全部');
  const [detailDialogOpen, setDetailDialogOpen] = useState(false);
  const [viewMode, setViewMode] = useState<'list' | 'card'>('list');
  const [tabValue, setTabValue] = useState(0);
  const [error, setError] = useState<string | null>(null);

  // 从API加载医生数据
  useEffect(() => {
    const fetchDoctors = async () => {
      setIsLoading(true);
      setError(null);
      
      console.log('==== 开始请求医生数据 ====');
      console.log('当前token:', localStorage.getItem('token'));
      
      // 添加超时控制
      const timeoutPromise = new Promise((_, reject) => {
        setTimeout(() => {
          reject(new Error('请求超时，请检查网络连接或后端服务'));
        }, 5000); // 5秒超时
      });
      
      try {
        const params: any = {};
        if (filterDepartment !== '全部') {
          params.department = filterDepartment;
        }
        
        console.log('正在获取医生数据，参数:', params);
        // 使用Promise.race实现请求超时控制
        const response = await Promise.race([
          apiService.admin.getDoctors(params),
          timeoutPromise
        ]) as any;
        
        console.log('医生数据API响应:', response);
        
        if (response && response.data) {
          console.log('获取到医生数据:', response.data);
          setDoctors(response.data);
          setFilteredDoctors(response.data);
        } else {
          console.warn('API返回了空数据或格式不正确:', response);
          // 使用模拟数据
          const mockDoctors = [
            {
              id: "mock-doc-001",
              name: "张医生",
              department: "康复科",
              title: "主任医师",
              specialty: "神经康复",
              email: "zhang@hospital.com",
              phone: "13800138001",
              status: "在职",
              patients: 12,
              joinDate: "2020-01-15"
            },
            {
              id: "mock-doc-002",
              name: "李医生",
              department: "骨科",
              title: "副主任医师",
              specialty: "运动康复",
              email: "li@hospital.com",
              phone: "13800138002",
              status: "在职",
              patients: 8,
              joinDate: "2021-03-20"
            }
          ];
          console.log('使用模拟数据:', mockDoctors);
          setDoctors(mockDoctors);
          setFilteredDoctors(mockDoctors);
        }
      } catch (err: any) {
        console.error('获取医生数据失败:', err);
        // 显示更详细的错误信息
        const errorMessage = err.response 
          ? `获取医生数据失败: ${err.response.status} - ${err.response.statusText}${err.response.data?.detail ? ` (${err.response.data.detail})` : ''}` 
          : `获取医生数据失败: ${err.message || '未知错误'}`;
        console.error(errorMessage);
        setError(errorMessage);
        
        // 使用模拟数据替代
        const mockDoctors = [
          {
            id: "mock-doc-001",
            name: "张医生",
            department: "康复科",
            title: "主任医师",
            specialty: "神经康复",
            email: "zhang@hospital.com",
            phone: "13800138001",
            status: "在职",
            patients: 12,
            joinDate: "2020-01-15"
          },
          {
            id: "mock-doc-002",
            name: "李医生",
            department: "骨科",
            title: "副主任医师",
            specialty: "运动康复",
            email: "li@hospital.com",
            phone: "13800138002",
            status: "在职",
            patients: 8,
            joinDate: "2021-03-20"
          }
        ];
        console.log('出错后使用模拟数据:', mockDoctors);
        setDoctors(mockDoctors);
        setFilteredDoctors(mockDoctors);
        // 继续展示页面
      } finally {
        setIsLoading(false);
      }
    };
    
    fetchDoctors();
  }, [filterDepartment]); // 当部门筛选条件变更时重新加载

  // Use raw doctors list when filtering effect is disabled
  useEffect(() => {
    setFilteredDoctors(doctors);
  }, [doctors]);

  const handleSearchChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    setSearchTerm(event.target.value);
  };

  const handleCreateDoctor = () => {
    setSelectedDoctor(null);
    setOpenDialog(true);
  };

  const handleEditDoctor = (doctor: Doctor) => {
    setSelectedDoctor(doctor);
    setOpenDialog(true);
  };

  const handleViewDoctor = (doctor: Doctor) => {
    setSelectedDoctor(doctor);
    setDetailDialogOpen(true);
  };

  const handleDeleteDoctor = (doctorId: string) => {
    setDoctors(doctors.filter((doctor: Doctor) => doctor.id !== doctorId));
    setFilteredDoctors(filteredDoctors.filter((doctor: Doctor) => doctor.id !== doctorId));
  };

  const handleCloseDialog = () => {
    setOpenDialog(false);
    setDetailDialogOpen(false);
    setSelectedDoctor(null);
  };

  const handleSaveDoctor = () => {
    // 这里会处理创建/编辑医生的逻辑
    handleCloseDialog();
  };

  const handleFilterDepartmentChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    setFilterDepartment(event.target.value);
  };

  const handleFilterTitleChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    setFilterTitle(event.target.value);
  };

  const handleTabChange = (event: React.SyntheticEvent, newValue: number) => {
    setTabValue(newValue);
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case '在职':
        return 'success';
      case '休假':
        return 'warning';
      case '离职':
        return 'error';
      default:
        return 'default';
    }
  };

  // 如果仍在加载中，显示加载状态
  if (isLoading) {
    return (
      <Box display="flex" justifyContent="center" alignItems="center" height="300px">
        <CircularProgress />
        <Typography variant="body1" sx={{ ml: 2 }}>
          医生数据加载中...
        </Typography>
      </Box>
    );
  }
  
  // 如果发生错误
  if (error) {
    return (
      <Box display="flex" justifyContent="center" alignItems="center" height="300px">
        <Typography color="error" variant="body1">
          {error}
        </Typography>
      </Box>
    );
  }

  return (
    <Box>
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
        <Typography variant="h5" component="h1">
          医生管理
        </Typography>
        <Button 
          variant="contained" 
          color="primary" 
          startIcon={<AddIcon />}
          onClick={handleCreateDoctor}
        >
          添加医生
        </Button>
      </Box>

      <Box mb={3} display="flex" alignItems="flex-start">
        <TextField
          fullWidth
          placeholder="搜索医生姓名、科室或专长..."
          variant="outlined"
          value={searchTerm}
          onChange={handleSearchChange}
          sx={{ mr: 2 }}
          InputProps={{
            startAdornment: (
              <InputAdornment position="start">
                <SearchIcon />
              </InputAdornment>
            ),
          }}
        />
        
        <FormControl sx={{ minWidth: 120, mr: 2 }}>
          <InputLabel>科室</InputLabel>
          <Select
            value={filterDepartment}
            label="科室"
            onChange={handleFilterDepartmentChange}
            size="medium"
          >
            {departments.map((dept) => (
              <MenuItem key={dept} value={dept}>{dept}</MenuItem>
            ))}
          </Select>
        </FormControl>
        
        <FormControl sx={{ minWidth: 120 }}>
          <InputLabel>职称</InputLabel>
          <Select
            value={filterTitle}
            label="职称"
            onChange={handleFilterTitleChange}
            size="medium"
          >
            {titles.map((title) => (
              <MenuItem key={title} value={title}>{title}</MenuItem>
            ))}
          </Select>
        </FormControl>
      </Box>

      <Box sx={{ borderBottom: 1, borderColor: 'divider', mb: 2 }}>
        <Tabs value={tabValue} onChange={handleTabChange}>
          <Tab label="列表视图" />
          <Tab label="卡片视图" />
        </Tabs>
      </Box>

      {tabValue === 0 && (
        <TableContainer component={Paper}>
          <Table>
            <TableHead>
              <TableRow>
                <TableCell>医生姓名</TableCell>
                <TableCell>科室</TableCell>
                <TableCell>职称</TableCell>
                <TableCell>专长</TableCell>
                <TableCell>联系方式</TableCell>
                <TableCell>患者数</TableCell>
                <TableCell>状态</TableCell>
                <TableCell align="center">操作</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {filteredDoctors.map((doctor: Doctor) => (
                <TableRow key={doctor.id}>
                  <TableCell>
                    <Box display="flex" alignItems="center">
                      <Avatar sx={{ mr: 1, bgcolor: 'primary.main' }}>
                        {doctor.name.charAt(0)}
                      </Avatar>
                      {doctor.name}
                    </Box>
                  </TableCell>
                  <TableCell>{doctor.department}</TableCell>
                  <TableCell>{doctor.title}</TableCell>
                  <TableCell>{doctor.specialty}</TableCell>
                  <TableCell>
                    <Typography variant="body2" color="text.secondary">
                      {doctor.phone}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      {doctor.email}
                    </Typography>
                  </TableCell>
                  <TableCell>{doctor.patients ?? 'N/A'}</TableCell>
                  <TableCell>
                    <Chip 
                      label={doctor.status} 
                      color={getStatusColor(doctor.status)} 
                      size="small" 
                    />
                  </TableCell>
                  <TableCell align="center">
                    <IconButton
                      color="primary"
                      onClick={() => handleViewDoctor(doctor)}
                    >
                      <MoreVertIcon />
                    </IconButton>
                    <IconButton
                      color="primary"
                      onClick={() => handleEditDoctor(doctor)}
                    >
                      <EditIcon />
                    </IconButton>
                    <IconButton
                      color="error"
                      onClick={() => handleDeleteDoctor(doctor.id)}
                    >
                      <DeleteIcon />
                    </IconButton>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      )}

      {tabValue === 1 && (
        <Grid container spacing={2}>
          {filteredDoctors.map((doctor: Doctor) => (
            <Grid item xs={12} sm={6} md={4} key={doctor.id}>
              <Paper sx={{ p: 2 }}>
                <Box display="flex" alignItems="center" mb={2}>
                  <Avatar 
                    sx={{ width: 56, height: 56, mr: 2, bgcolor: 'primary.main' }}
                  >
                    {doctor.name.charAt(0)}
                  </Avatar>
                  <Box>
                    <Typography variant="h6">{doctor.name}</Typography>
                    <Typography variant="body2" color="text.secondary">
                      {doctor.title} - {doctor.department}
                    </Typography>
                  </Box>
                </Box>
                
                <Divider sx={{ my: 1.5 }} />
                
                <List dense>
                  <ListItem>
                    <ListItemAvatar>
                      <WorkIcon color="primary" fontSize="small" />
                    </ListItemAvatar>
                    <ListItemText 
                      primary="专长"
                      secondary={doctor.specialty}
                    />
                  </ListItem>
                  <ListItem>
                    <ListItemAvatar>
                      <PhoneIcon color="primary" fontSize="small" />
                    </ListItemAvatar>
                    <ListItemText 
                      primary="电话"
                      secondary={doctor.phone}
                    />
                  </ListItem>
                  <ListItem>
                    <ListItemAvatar>
                      <PeopleIcon color="primary" fontSize="small" />
                    </ListItemAvatar>
                    <ListItemText 
                      primary="管理患者数"
                      secondary={doctor.patients ?? 'N/A'}
                    />
                  </ListItem>
                  <ListItem>
                    <ListItemAvatar>
                      <EventIcon color="primary" fontSize="small" />
                    </ListItemAvatar>
                    <ListItemText 
                      primary="入职日期"
                      secondary={doctor.joinDate ?? '未知'}
                    />
                  </ListItem>
                </List>
                
                <Box display="flex" justifyContent="space-between" alignItems="center" mt={2}>
                  <Chip 
                    label={doctor.status} 
                    color={getStatusColor(doctor.status)} 
                    size="small" 
                  />
                  <Box>
                    <IconButton
                      size="small"
                      color="primary"
                      onClick={() => handleEditDoctor(doctor)}
                    >
                      <EditIcon />
                    </IconButton>
                    <IconButton
                      size="small"
                      color="primary"
                      onClick={() => handleViewDoctor(doctor)}
                    >
                      <ArrowForwardIosIcon fontSize="small" />
                    </IconButton>
                  </Box>
                </Box>
              </Paper>
            </Grid>
          ))}
        </Grid>
      )}

      {/* 创建/编辑医生对话框 */}
      <Dialog open={openDialog} onClose={handleCloseDialog} maxWidth="md" fullWidth>
        <DialogTitle>{selectedDoctor ? '编辑医生信息' : '添加新医生'}</DialogTitle>
        <DialogContent>
          <Grid container spacing={2} sx={{ mt: 1 }}>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="姓名"
                defaultValue={selectedDoctor?.name || ''}
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <FormControl fullWidth>
                <InputLabel>科室</InputLabel>
                <Select
                  label="科室"
                  defaultValue={selectedDoctor?.department || ''}
                >
                  {departments.filter(d => d !== '全部').map((dept) => (
                    <MenuItem key={dept} value={dept}>{dept}</MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} sm={6}>
              <FormControl fullWidth>
                <InputLabel>职称</InputLabel>
                <Select
                  label="职称"
                  defaultValue={selectedDoctor?.title || ''}
                >
                  {titles.filter(t => t !== '全部').map((title) => (
                    <MenuItem key={title} value={title}>{title}</MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="专长"
                defaultValue={selectedDoctor?.specialty || ''}
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="电话"
                defaultValue={selectedDoctor?.phone || ''}
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="邮箱"
                defaultValue={selectedDoctor?.email || ''}
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <FormControl fullWidth>
                <InputLabel>状态</InputLabel>
                <Select
                  label="状态"
                  defaultValue={selectedDoctor?.status || '在职'}
                >
                  <MenuItem value="在职">在职</MenuItem>
                  <MenuItem value="休假">休假</MenuItem>
                  <MenuItem value="离职">离职</MenuItem>
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="入职日期"
                type="date"
                defaultValue={selectedDoctor?.joinDate || new Date().toISOString().split('T')[0]}
                InputLabelProps={{
                  shrink: true,
                }}
              />
            </Grid>
          </Grid>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCloseDialog}>取消</Button>
          <Button onClick={handleSaveDoctor} variant="contained" color="primary">
            保存
          </Button>
        </DialogActions>
      </Dialog>

      {/* 医生详情对话框 */}
      <Dialog open={detailDialogOpen} onClose={handleCloseDialog} maxWidth="md" fullWidth>
        <DialogTitle>
          <Box display="flex" alignItems="center">
            <Avatar 
              sx={{ width: 56, height: 56, mr: 2, bgcolor: 'primary.main' }}
            >
              {selectedDoctor?.name.charAt(0)}
            </Avatar>
            <Box>
              <Typography variant="h6">{selectedDoctor?.name}</Typography>
              <Typography variant="body2" color="text.secondary">
                {selectedDoctor?.title} - {selectedDoctor?.department}
              </Typography>
            </Box>
          </Box>
        </DialogTitle>
        <DialogContent>
          <Grid container spacing={3}>
            <Grid item xs={12} md={6}>
              <Paper sx={{ p: 2 }}>
                <Typography variant="h6" gutterBottom>基本信息</Typography>
                <Divider sx={{ mb: 2 }} />
                
                <List dense>
                  <ListItem>
                    <ListItemAvatar>
                      <WorkIcon color="primary" />
                    </ListItemAvatar>
                    <ListItemText 
                      primary="专长"
                      secondary={selectedDoctor?.specialty}
                    />
                  </ListItem>
                  <ListItem>
                    <ListItemAvatar>
                      <PhoneIcon color="primary" />
                    </ListItemAvatar>
                    <ListItemText 
                      primary="电话"
                      secondary={selectedDoctor?.phone}
                    />
                  </ListItem>
                  <ListItem>
                    <ListItemAvatar>
                      <AlternateEmailIcon color="primary" />
                    </ListItemAvatar>
                    <ListItemText 
                      primary="邮箱"
                      secondary={selectedDoctor?.email}
                    />
                  </ListItem>
                  <ListItem>
                    <ListItemAvatar>
                      <PeopleIcon color="primary" />
                    </ListItemAvatar>
                    <ListItemText 
                      primary="管理患者数"
                      secondary={selectedDoctor?.patients ?? 'N/A'}
                    />
                  </ListItem>
                  <ListItem>
                    <ListItemAvatar>
                      <EventIcon color="primary" />
                    </ListItemAvatar>
                    <ListItemText 
                      primary="入职日期"
                      secondary={selectedDoctor?.joinDate ?? '未知'}
                    />
                  </ListItem>
                </List>
              </Paper>
            </Grid>
            
            <Grid item xs={12} md={6}>
              <Paper sx={{ p: 2, height: '100%' }}>
                <Typography variant="h6" gutterBottom>资质认证</Typography>
                <Divider sx={{ mb: 2 }} />
                
                <List>
                  <ListItem>
                    <ListItemText primary="暂无资质信息" />
                  </ListItem>
                </List>
              </Paper>
            </Grid>
            
            <Grid item xs={12}>
              <Paper sx={{ p: 2 }}>
                <Typography variant="h6" gutterBottom>统计数据</Typography>
                <Divider sx={{ mb: 2 }} />
                
                <Stack direction="row" spacing={2} justifyContent="space-around">
                  <Box textAlign="center">
                    <Typography variant="h4" color="primary">
                      {selectedDoctor?.patients ?? 'N/A'}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      当前患者
                    </Typography>
                  </Box>
                  <Box textAlign="center">
                    <Typography variant="h4" color="secondary">
                      {Math.floor(Math.random() * 100)}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      本月随访
                    </Typography>
                  </Box>
                  <Box textAlign="center">
                    <Typography variant="h4" color="success.main">
                      {Math.floor(Math.random() * 500)}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      累计病例
                    </Typography>
                  </Box>
                </Stack>
              </Paper>
            </Grid>
          </Grid>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCloseDialog}>关闭</Button>
          <Button 
            variant="contained" 
            color="primary"
            onClick={() => {
              handleCloseDialog();
              handleEditDoctor(selectedDoctor);
            }}
          >
            编辑信息
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default DoctorManagement; 
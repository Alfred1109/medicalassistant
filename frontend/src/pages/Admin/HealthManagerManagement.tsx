import React from 'react';
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

// 模拟数据
const mockHealthManagers = [
  {
    id: '1',
    name: '张管理',
    avatar: '',
    department: '康复科',
    title: '高级健康管理师',
    specialty: '运动康复指导',
    email: 'zhang@hospital.com',
    phone: '13900139001',
    patients: 35,
    status: '在职',
    joinDate: '2016-06-15',
    certifications: ['健康管理师资格证', '营养师证书', '康复指导资格证'],
  },
  {
    id: '2',
    name: '刘管理',
    avatar: '',
    department: '营养科',
    title: '中级健康管理师',
    specialty: '饮食营养指导',
    email: 'liu@hospital.com',
    phone: '13900139002',
    patients: 28,
    status: '在职',
    joinDate: '2018-03-25',
    certifications: ['健康管理师资格证', '营养师证书'],
  },
  {
    id: '3',
    name: '杨管理',
    avatar: '',
    department: '心理科',
    title: '初级健康管理师',
    specialty: '心理健康疏导',
    email: 'yang@hospital.com',
    phone: '13900139003',
    patients: 20,
    status: '在职',
    joinDate: '2020-09-01',
    certifications: ['健康管理师资格证', '心理咨询师证书'],
  },
  {
    id: '4',
    name: '周管理',
    avatar: '',
    department: '康复科',
    title: '高级健康管理师',
    specialty: '慢病管理',
    email: 'zhou@hospital.com',
    phone: '13900139004',
    patients: 32,
    status: '休假',
    joinDate: '2017-07-20',
    certifications: ['健康管理师资格证', '慢病管理师证书'],
  },
  {
    id: '5',
    name: '吴管理',
    avatar: '',
    department: '预防科',
    title: '中级健康管理师',
    specialty: '健康教育',
    email: 'wu@hospital.com',
    phone: '13900139005',
    patients: 25,
    status: '在职',
    joinDate: '2019-05-10',
    certifications: ['健康管理师资格证', '健康教育师证书'],
  },
];

// 模拟部门数据
const departments = [
  '全部',
  '康复科',
  '营养科',
  '心理科',
  '预防科',
  '体检科',
];

// 模拟职称数据
const titles = ['全部', '高级健康管理师', '中级健康管理师', '初级健康管理师'];

const HealthManagerManagement: React.FC = () => {
  const [healthManagers, setHealthManagers] = React.useState(mockHealthManagers);
  const [filteredHealthManagers, setFilteredHealthManagers] = React.useState(mockHealthManagers);
  const [searchTerm, setSearchTerm] = React.useState('');
  const [openDialog, setOpenDialog] = React.useState(false);
  const [selectedHealthManager, setSelectedHealthManager] = React.useState<any>(null);
  const [filterDepartment, setFilterDepartment] = React.useState('全部');
  const [filterTitle, setFilterTitle] = React.useState('全部');
  const [detailDialogOpen, setDetailDialogOpen] = React.useState(false);
  const [tabValue, setTabValue] = React.useState(0);

  React.useEffect(() => {
    filterHealthManagers();
  }, [searchTerm, filterDepartment, filterTitle]);

  const filterHealthManagers = () => {
    let filtered = mockHealthManagers;
    
    // 根据部门筛选
    if (filterDepartment !== '全部') {
      filtered = filtered.filter(manager => manager.department === filterDepartment);
    }
    
    // 根据职称筛选
    if (filterTitle !== '全部') {
      filtered = filtered.filter(manager => manager.title === filterTitle);
    }
    
    // 根据搜索词筛选
    if (searchTerm) {
      filtered = filtered.filter(manager => 
        manager.name.includes(searchTerm) || 
        manager.department.includes(searchTerm) ||
        manager.specialty.includes(searchTerm)
      );
    }
    
    setFilteredHealthManagers(filtered);
  };

  const handleSearchChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    setSearchTerm(event.target.value);
  };

  const handleCreateHealthManager = () => {
    setSelectedHealthManager(null);
    setOpenDialog(true);
  };

  const handleEditHealthManager = (manager: any) => {
    setSelectedHealthManager(manager);
    setOpenDialog(true);
  };

  const handleViewHealthManager = (manager: any) => {
    setSelectedHealthManager(manager);
    setDetailDialogOpen(true);
  };

  const handleDeleteHealthManager = (managerId: string) => {
    setHealthManagers(healthManagers.filter(manager => manager.id !== managerId));
    setFilteredHealthManagers(filteredHealthManagers.filter(manager => manager.id !== managerId));
  };

  const handleCloseDialog = () => {
    setOpenDialog(false);
    setDetailDialogOpen(false);
    setSelectedHealthManager(null);
  };

  const handleSaveHealthManager = () => {
    // 这里会处理创建/编辑健康管理师的逻辑
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

  return (
    <Box>
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
        <Typography variant="h5" component="h1">
          健康管理师管理
        </Typography>
        <Button 
          variant="contained" 
          color="primary" 
          startIcon={<AddIcon />}
          onClick={handleCreateHealthManager}
        >
          添加健康管理师
        </Button>
      </Box>

      <Box mb={3} display="flex" alignItems="flex-start">
        <TextField
          fullWidth
          placeholder="搜索管理师姓名、科室或专长..."
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
                <TableCell>姓名</TableCell>
                <TableCell>科室</TableCell>
                <TableCell>职称</TableCell>
                <TableCell>专长</TableCell>
                <TableCell>联系方式</TableCell>
                <TableCell>管理患者数</TableCell>
                <TableCell>状态</TableCell>
                <TableCell align="center">操作</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {filteredHealthManagers.map((manager) => (
                <TableRow key={manager.id}>
                  <TableCell>
                    <Box display="flex" alignItems="center">
                      <Avatar sx={{ mr: 1, bgcolor: 'primary.main' }}>
                        {manager.name.charAt(0)}
                      </Avatar>
                      {manager.name}
                    </Box>
                  </TableCell>
                  <TableCell>{manager.department}</TableCell>
                  <TableCell>{manager.title}</TableCell>
                  <TableCell>{manager.specialty}</TableCell>
                  <TableCell>
                    <Typography variant="body2" color="text.secondary">
                      {manager.phone}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      {manager.email}
                    </Typography>
                  </TableCell>
                  <TableCell>{manager.patients}</TableCell>
                  <TableCell>
                    <Chip 
                      label={manager.status} 
                      color={getStatusColor(manager.status)} 
                      size="small" 
                    />
                  </TableCell>
                  <TableCell align="center">
                    <IconButton
                      color="primary"
                      onClick={() => handleViewHealthManager(manager)}
                    >
                      <MoreVertIcon />
                    </IconButton>
                    <IconButton
                      color="primary"
                      onClick={() => handleEditHealthManager(manager)}
                    >
                      <EditIcon />
                    </IconButton>
                    <IconButton
                      color="error"
                      onClick={() => handleDeleteHealthManager(manager.id)}
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
          {filteredHealthManagers.map((manager) => (
            <Grid item xs={12} sm={6} md={4} key={manager.id}>
              <Paper sx={{ p: 2 }}>
                <Box display="flex" alignItems="center" mb={2}>
                  <Avatar 
                    sx={{ width: 56, height: 56, mr: 2, bgcolor: 'primary.main' }}
                  >
                    {manager.name.charAt(0)}
                  </Avatar>
                  <Box>
                    <Typography variant="h6">{manager.name}</Typography>
                    <Typography variant="body2" color="text.secondary">
                      {manager.title} - {manager.department}
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
                      secondary={manager.specialty}
                    />
                  </ListItem>
                  <ListItem>
                    <ListItemAvatar>
                      <PhoneIcon color="primary" fontSize="small" />
                    </ListItemAvatar>
                    <ListItemText 
                      primary="电话"
                      secondary={manager.phone}
                    />
                  </ListItem>
                  <ListItem>
                    <ListItemAvatar>
                      <PeopleIcon color="primary" fontSize="small" />
                    </ListItemAvatar>
                    <ListItemText 
                      primary="管理患者数"
                      secondary={manager.patients}
                    />
                  </ListItem>
                  <ListItem>
                    <ListItemAvatar>
                      <EventIcon color="primary" fontSize="small" />
                    </ListItemAvatar>
                    <ListItemText 
                      primary="入职日期"
                      secondary={manager.joinDate}
                    />
                  </ListItem>
                </List>
                
                <Box display="flex" justifyContent="space-between" alignItems="center" mt={2}>
                  <Chip 
                    label={manager.status} 
                    color={getStatusColor(manager.status)} 
                    size="small" 
                  />
                  <Box>
                    <IconButton
                      size="small"
                      color="primary"
                      onClick={() => handleEditHealthManager(manager)}
                    >
                      <EditIcon />
                    </IconButton>
                    <IconButton
                      size="small"
                      color="primary"
                      onClick={() => handleViewHealthManager(manager)}
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

      {/* 创建/编辑健康管理师对话框 */}
      <Dialog open={openDialog} onClose={handleCloseDialog} maxWidth="md" fullWidth>
        <DialogTitle>{selectedHealthManager ? '编辑健康管理师信息' : '添加新健康管理师'}</DialogTitle>
        <DialogContent>
          <Grid container spacing={2} sx={{ mt: 1 }}>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="姓名"
                defaultValue={selectedHealthManager?.name || ''}
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <FormControl fullWidth>
                <InputLabel>科室</InputLabel>
                <Select
                  label="科室"
                  defaultValue={selectedHealthManager?.department || ''}
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
                  defaultValue={selectedHealthManager?.title || ''}
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
                defaultValue={selectedHealthManager?.specialty || ''}
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="电话"
                defaultValue={selectedHealthManager?.phone || ''}
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="邮箱"
                defaultValue={selectedHealthManager?.email || ''}
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <FormControl fullWidth>
                <InputLabel>状态</InputLabel>
                <Select
                  label="状态"
                  defaultValue={selectedHealthManager?.status || '在职'}
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
                defaultValue={selectedHealthManager?.joinDate || new Date().toISOString().split('T')[0]}
                InputLabelProps={{
                  shrink: true,
                }}
              />
            </Grid>
          </Grid>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCloseDialog}>取消</Button>
          <Button onClick={handleSaveHealthManager} variant="contained" color="primary">
            保存
          </Button>
        </DialogActions>
      </Dialog>

      {/* 健康管理师详情对话框 */}
      <Dialog open={detailDialogOpen} onClose={handleCloseDialog} maxWidth="md" fullWidth>
        <DialogTitle>
          <Box display="flex" alignItems="center">
            <Avatar 
              sx={{ width: 56, height: 56, mr: 2, bgcolor: 'primary.main' }}
            >
              {selectedHealthManager?.name.charAt(0)}
            </Avatar>
            <Box>
              <Typography variant="h6">{selectedHealthManager?.name}</Typography>
              <Typography variant="body2" color="text.secondary">
                {selectedHealthManager?.title} - {selectedHealthManager?.department}
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
                      secondary={selectedHealthManager?.specialty}
                    />
                  </ListItem>
                  <ListItem>
                    <ListItemAvatar>
                      <PhoneIcon color="primary" />
                    </ListItemAvatar>
                    <ListItemText 
                      primary="电话"
                      secondary={selectedHealthManager?.phone}
                    />
                  </ListItem>
                  <ListItem>
                    <ListItemAvatar>
                      <AlternateEmailIcon color="primary" />
                    </ListItemAvatar>
                    <ListItemText 
                      primary="邮箱"
                      secondary={selectedHealthManager?.email}
                    />
                  </ListItem>
                  <ListItem>
                    <ListItemAvatar>
                      <PeopleIcon color="primary" />
                    </ListItemAvatar>
                    <ListItemText 
                      primary="管理患者数"
                      secondary={selectedHealthManager?.patients}
                    />
                  </ListItem>
                  <ListItem>
                    <ListItemAvatar>
                      <EventIcon color="primary" />
                    </ListItemAvatar>
                    <ListItemText 
                      primary="入职日期"
                      secondary={selectedHealthManager?.joinDate}
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
                  {selectedHealthManager?.certifications.map((cert: string, index: number) => (
                    <ListItem key={index}>
                      <ListItemAvatar>
                        <LocalHospitalIcon color="primary" />
                      </ListItemAvatar>
                      <ListItemText primary={cert} />
                    </ListItem>
                  ))}
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
                      {selectedHealthManager?.patients}
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
                      本月指导
                    </Typography>
                  </Box>
                  <Box textAlign="center">
                    <Typography variant="h4" color="success.main">
                      {Math.floor(Math.random() * 500)}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      累计方案
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
              handleEditHealthManager(selectedHealthManager);
            }}
          >
            编辑信息
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default HealthManagerManagement; 
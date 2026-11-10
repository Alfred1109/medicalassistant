import React, { useState, useEffect, useMemo } from 'react';
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
  CircularProgress,
  SelectChangeEvent,
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
import MoreVertIcon from '@mui/icons-material/MoreVert';
import PhoneIcon from '@mui/icons-material/Phone';
import WorkIcon from '@mui/icons-material/Work';
import EventIcon from '@mui/icons-material/Event';
import ArrowForwardIosIcon from '@mui/icons-material/ArrowForwardIos';
import PeopleIcon from '@mui/icons-material/People';
import { apiService } from '../../services/api';
import apiClient from '../../services/api';
import AccountCreateDialog from '../../components/Admin/AccountCreateDialog';
import { Doctor } from '../../types/doctor.types';

// 医生管理：列表数据来自真实接口 GET /api/admin/doctors（后端已实现查询）
// 创建/编辑/删除：后端 POST /admin/doctors 未持久化，且无 PUT/DELETE，故禁用相关入口
const DoctorManagement: React.FC = () => {
  const [isLoading, setIsLoading] = useState(true);
  const [doctors, setDoctors] = useState<Doctor[]>([]);
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedDoctor, setSelectedDoctor] = useState<Doctor | null>(null);
  const [filterDepartment, setFilterDepartment] = useState('全部');
  const [filterTitle, setFilterTitle] = useState('全部');
  const [detailDialogOpen, setDetailDialogOpen] = useState(false);
  const [viewMode, setViewMode] = useState<'list' | 'card'>('list');
  const [tabValue, setTabValue] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [createOpen, setCreateOpen] = useState(false);

  // 从API加载医生数据（真实接口，失败时展示错误状态并提供重试）
  useEffect(() => {
    let cancelled = false;

    const fetchDoctors = async () => {
      setIsLoading(true);
      setError(null);

      try {
        const response = await apiService.admin.getDoctors();
        if (!cancelled) {
          setDoctors(Array.isArray(response.data) ? response.data : []);
        }
      } catch (err: any) {
        if (!cancelled) {
          const errorMessage = err.response
            ? `获取医生数据失败: ${err.response.status} ${err.response.statusText || ''}${err.response.data?.detail ? ` (${err.response.data.detail})` : ''}`
            : `获取医生数据失败: ${err.message || '未知错误'}`;
          setError(errorMessage);
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
      }
    };

    fetchDoctors();
    return () => {
      cancelled = true;
    };
  }, [reloadKey]);

  // 科室/职称筛选选项从真实数据中提取
  const departmentOptions = useMemo(() => {
    const deps = Array.from(new Set(doctors.map(d => d.department).filter(Boolean)));
    return ['全部', ...deps];
  }, [doctors]);

  const titleOptions = useMemo(() => {
    const ts = Array.from(new Set(doctors.map(d => d.title).filter(Boolean)));
    return ['全部', ...ts];
  }, [doctors]);

  // 客户端筛选：科室 + 职称 + 关键词搜索
  const filteredDoctors = useMemo(() => {
    const keyword = searchTerm.trim().toLowerCase();
    return doctors.filter(doctor => {
      if (filterDepartment !== '全部' && doctor.department !== filterDepartment) {
        return false;
      }
      if (filterTitle !== '全部' && doctor.title !== filterTitle) {
        return false;
      }
      if (keyword) {
        const haystack = [doctor.name, doctor.department, doctor.specialty, doctor.email, doctor.phone]
          .filter(Boolean)
          .join(' ')
          .toLowerCase();
        if (!haystack.includes(keyword)) {
          return false;
        }
      }
      return true;
    });
  }, [doctors, filterDepartment, filterTitle, searchTerm]);

  const handleSearchChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    setSearchTerm(event.target.value);
  };

  const handleViewDoctor = (doctor: Doctor) => {
    setSelectedDoctor(doctor);
    setDetailDialogOpen(true);
  };

  const handleCloseDialog = () => {
    setDetailDialogOpen(false);
    setSelectedDoctor(null);
  };

  const handleFilterDepartmentChange = (event: SelectChangeEvent<string>) => {
    setFilterDepartment(event.target.value);
  };

  const handleFilterTitleChange = (event: SelectChangeEvent<string>) => {
    setFilterTitle(event.target.value);
  };

  const handleTabChange = (event: React.SyntheticEvent, newValue: number) => {
    setTabValue(newValue);
    setViewMode(newValue === 0 ? 'list' : 'card');
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

  // 加载中
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

  // 加载失败：真实错误状态 + 重试
  if (error) {
    return (
      <Box display="flex" flexDirection="column" justifyContent="center" alignItems="center" height="300px">
        <Typography color="error" variant="body1" gutterBottom>
          {error}
        </Typography>
        <Button variant="outlined" onClick={() => setReloadKey(key => key + 1)}>
          重试
        </Button>
      </Box>
    );
  }

  return (
    <Box>
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
        <Typography variant="h5" component="h1">
          医生管理
        </Typography>
        <Box textAlign="right">
          <Button variant="contained" color="primary" startIcon={<AddIcon />} onClick={() => setCreateOpen(true)}>
            添加医生
          </Button>
        </Box>
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
            {departmentOptions.map((dept) => (
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
            {titleOptions.map((title) => (
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

      {filteredDoctors.length === 0 ? (
        <Paper sx={{ p: 4, textAlign: 'center' }}>
          <Typography variant="body1" color="text.secondary">
            暂无医生数据
          </Typography>
        </Paper>
      ) : viewMode === 'list' ? (
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
                        {doctor.name?.charAt(0) || '?'}
                      </Avatar>
                      {doctor.name}
                    </Box>
                  </TableCell>
                  <TableCell>{doctor.department || '—'}</TableCell>
                  <TableCell>{doctor.title || '—'}</TableCell>
                  <TableCell>{doctor.specialty || '—'}</TableCell>
                  <TableCell>
                    <Typography variant="body2" color="text.secondary">
                      {doctor.phone || '—'}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      {doctor.email || '—'}
                    </Typography>
                  </TableCell>
                  <TableCell>{doctor.patients ?? '暂无'}</TableCell>
                  <TableCell>
                    <Chip
                      label={doctor.status || '未知'}
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
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      ) : (
        <Grid container spacing={2}>
          {filteredDoctors.map((doctor: Doctor) => (
            <Grid item xs={12} sm={6} md={4} key={doctor.id}>
              <Paper sx={{ p: 2 }}>
                <Box display="flex" alignItems="center" mb={2}>
                  <Avatar
                    sx={{ width: 56, height: 56, mr: 2, bgcolor: 'primary.main' }}
                  >
                    {doctor.name?.charAt(0) || '?'}
                  </Avatar>
                  <Box>
                    <Typography variant="h6">{doctor.name}</Typography>
                    <Typography variant="body2" color="text.secondary">
                      {doctor.title || '—'} - {doctor.department || '—'}
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
                      secondary={doctor.specialty || '—'}
                    />
                  </ListItem>
                  <ListItem>
                    <ListItemAvatar>
                      <PhoneIcon color="primary" fontSize="small" />
                    </ListItemAvatar>
                    <ListItemText
                      primary="电话"
                      secondary={doctor.phone || '—'}
                    />
                  </ListItem>
                  <ListItem>
                    <ListItemAvatar>
                      <PeopleIcon color="primary" fontSize="small" />
                    </ListItemAvatar>
                    <ListItemText
                      primary="管理患者数"
                      secondary={doctor.patients ?? '暂无'}
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
                    label={doctor.status || '未知'}
                    color={getStatusColor(doctor.status)}
                    size="small"
                  />
                  <IconButton
                    size="small"
                    color="primary"
                    onClick={() => handleViewDoctor(doctor)}
                  >
                    <ArrowForwardIosIcon fontSize="small" />
                  </IconButton>
                </Box>
              </Paper>
            </Grid>
          ))}
        </Grid>
      )}

      {/* 医生详情对话框（仅展示真实行数据） */}
      <Dialog open={detailDialogOpen} onClose={handleCloseDialog} maxWidth="md" fullWidth>
        <DialogTitle>
          <Box display="flex" alignItems="center">
            <Avatar
              sx={{ width: 56, height: 56, mr: 2, bgcolor: 'primary.main' }}
            >
              {selectedDoctor?.name?.charAt(0) || '?'}
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
                      secondary={selectedDoctor?.specialty || '—'}
                    />
                  </ListItem>
                  <ListItem>
                    <ListItemAvatar>
                      <PhoneIcon color="primary" />
                    </ListItemAvatar>
                    <ListItemText
                      primary="电话"
                      secondary={selectedDoctor?.phone || '—'}
                    />
                  </ListItem>
                  <ListItem>
                    <ListItemText
                      primary="邮箱"
                      secondary={selectedDoctor?.email || '—'}
                    />
                  </ListItem>
                  <ListItem>
                    <ListItemAvatar>
                      <PeopleIcon color="primary" />
                    </ListItemAvatar>
                    <ListItemText
                      primary="管理患者数"
                      secondary={selectedDoctor?.patients ?? '暂无'}
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
                      {selectedDoctor?.patients ?? '暂无'}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      当前患者
                    </Typography>
                  </Box>
                  <Box textAlign="center">
                    <Typography variant="h4" color="text.disabled">
                      暂无
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      本月随访
                    </Typography>
                  </Box>
                  <Box textAlign="center">
                    <Typography variant="h4" color="text.disabled">
                      暂无
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
          {selectedDoctor?.id && <Button onClick={async () => {
            await apiClient.put(`/admin/accounts/${selectedDoctor.id}/active`, { active: false });
            handleCloseDialog();
            setReloadKey(key => key + 1);
          }}>停用账号</Button>}
          <Button onClick={handleCloseDialog}>关闭</Button>
        </DialogActions>
      </Dialog>
      <AccountCreateDialog open={createOpen} title="添加医生" path="/admin/doctors" role="doctor" onClose={() => setCreateOpen(false)} onCreated={() => setReloadKey(key => key + 1)} />
    </Box>
  );
};

export default DoctorManagement;

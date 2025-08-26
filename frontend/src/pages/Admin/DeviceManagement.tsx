import React from 'react';
import {
  Box,
  Typography,
  Button,
  Paper,
  Grid,
  TextField,
  Chip,
  IconButton,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Card,
  CardContent,
  Divider,
} from '@mui/material';
import Switch from '@mui/material/Switch';
import FormControlLabel from '@mui/material/FormControlLabel';
import AddIcon from '@mui/icons-material/Add';
import EditIcon from '@mui/icons-material/Edit';
import DeleteIcon from '@mui/icons-material/Delete';
import DevicesIcon from '@mui/icons-material/Devices';
import WatchIcon from '@mui/icons-material/Watch';
import SensorsIcon from '@mui/icons-material/Sensors';
import FitnessCenterIcon from '@mui/icons-material/FitnessCenter';
import HealthAndSafetyIcon from '@mui/icons-material/HealthAndSafety';
import SettingsRemoteIcon from '@mui/icons-material/SettingsRemote';
import FilterListIcon from '@mui/icons-material/FilterList';

// 模拟设备数据
const mockDevices = [
  {
    id: 'DEV001',
    name: '智能康复手环',
    type: '可穿戴设备',
    model: 'WB-100',
    manufacturer: '康复科技有限公司',
    purchaseDate: '2023-01-15',
    status: '正常使用',
    location: '康复科',
    assignedTo: '',
    maintenanceDate: '2023-07-15',
    icon: <WatchIcon />,
  },
  {
    id: 'DEV002',
    name: '肌电传感器',
    type: '监测设备',
    model: 'EMG-200',
    manufacturer: '医疗设备制造商',
    purchaseDate: '2022-11-20',
    status: '正常使用',
    location: '神经康复室',
    assignedTo: '李医生',
    maintenanceDate: '2023-05-20',
    icon: <SensorsIcon />,
  },
  {
    id: 'DEV003',
    name: '智能康复训练器',
    type: '训练设备',
    model: 'RT-300',
    manufacturer: '康复科技有限公司',
    purchaseDate: '2022-08-10',
    status: '维修中',
    location: '康复训练室',
    assignedTo: '',
    maintenanceDate: '2023-02-10',
    icon: <FitnessCenterIcon />,
  },
  {
    id: 'DEV004',
    name: '健康监测器',
    type: '监测设备',
    model: 'HM-400',
    manufacturer: '医疗科技公司',
    purchaseDate: '2023-03-05',
    status: '正常使用',
    location: '康复科',
    assignedTo: '王医生',
    maintenanceDate: '2023-09-05',
    icon: <HealthAndSafetyIcon />,
  },
  {
    id: 'DEV005',
    name: '康复评估系统',
    type: '评估设备',
    model: 'AS-500',
    manufacturer: '康复设备厂商',
    purchaseDate: '2022-06-15',
    status: '闲置',
    location: '设备库房',
    assignedTo: '',
    maintenanceDate: '2023-01-15',
    icon: <SettingsRemoteIcon />,
  },
];

// 设备类型
const deviceTypes = [
  '全部',
  '可穿戴设备',
  '监测设备',
  '训练设备',
  '评估设备',
  '治疗设备',
];

// 设备状态
const deviceStatuses = [
  '全部',
  '正常使用',
  '维修中',
  '闲置',
  '报废',
];

const DeviceManagement: React.FC = () => {
  const [devices, setDevices] = React.useState(mockDevices);
  const [filteredDevices, setFilteredDevices] = React.useState(mockDevices);
  const [openDialog, setOpenDialog] = React.useState(false);
  const [selectedDevice, setSelectedDevice] = React.useState<any>(null);
  const [filterType, setFilterType] = React.useState('全部');
  const [filterStatus, setFilterStatus] = React.useState('全部');
  const [searchTerm, setSearchTerm] = React.useState('');
  const [openFilterDialog, setOpenFilterDialog] = React.useState(false);
  const [viewMode, setViewMode] = React.useState<'grid' | 'list'>('grid');
  const [filterOpen, setFilterOpen] = React.useState(false);
  const [filterConditions, setFilterConditions] = React.useState({
    status: 'all',
    type: 'all',
    onlyWarning: false,
  });

  // 过滤设备
  React.useEffect(() => {
    let filtered = devices;
    
    // 按类型过滤
    if (filterType !== '全部') {
      filtered = filtered.filter(device => device.type === filterType);
    }
    
    // 按状态过滤
    if (filterStatus !== '全部') {
      filtered = filtered.filter(device => device.status === filterStatus);
    }
    
    // 搜索过滤
    if (searchTerm) {
      filtered = filtered.filter(
        device => 
          device.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
          device.id.toLowerCase().includes(searchTerm.toLowerCase()) ||
          device.model.toLowerCase().includes(searchTerm.toLowerCase())
      );
    }
    
    setFilteredDevices(filtered);
  }, [devices, filterType, filterStatus, searchTerm]);

  const handleOpenDialog = (device?: any) => {
    setSelectedDevice(device || null);
    setOpenDialog(true);
  };

  const handleCloseDialog = () => {
    setOpenDialog(false);
    setOpenFilterDialog(false);
  };

  const handleSaveDevice = () => {
    // 这里会处理保存设备的逻辑
    setOpenDialog(false);
  };

  const handleDeleteDevice = (deviceId: string) => {
    setDevices(devices.filter(device => device.id !== deviceId));
  };

  const handleSearchChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    setSearchTerm(event.target.value);
  };

  const handleOpenFilter = () => {
    setOpenFilterDialog(true);
  };

  const applyFilters = () => {
    setOpenFilterDialog(false);
  };

  const resetFilters = () => {
    setFilterType('全部');
    setFilterStatus('全部');
    setOpenFilterDialog(false);
  };

  const toggleViewMode = () => {
    setViewMode(viewMode === 'grid' ? 'list' : 'grid');
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case '正常使用':
        return 'success';
      case '维修中':
        return 'warning';
      case '闲置':
        return 'info';
      case '报废':
        return 'error';
      default:
        return 'default';
    }
  };

  const handleFilterChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>, field: string) => {
    setFilterConditions({
      ...filterConditions,
      [field]: e.target.value,
    });
  };

  const handleSwitchChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setFilterConditions({
      ...filterConditions,
      onlyWarning: e.target.checked,
    });
  };

  return (
    <Box>
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
        <Typography variant="h5" component="h1">
          设备管理
        </Typography>
        <Button 
          variant="contained" 
          color="primary" 
          startIcon={<AddIcon />}
          onClick={() => handleOpenDialog()}
        >
          添加设备
        </Button>
      </Box>

      <Box mb={3} display="flex" justifyContent="space-between">
        <Box display="flex" alignItems="center">
          <TextField
            placeholder="搜索设备..."
            variant="outlined"
            size="small"
            value={searchTerm}
            onChange={handleSearchChange}
            sx={{ width: 300, mr: 2 }}
          />
          <Button 
            variant="outlined" 
            startIcon={<FilterListIcon />}
            onClick={handleOpenFilter}
          >
            筛选
          </Button>
        </Box>
        <FormControlLabel
          control={
            <Switch
              checked={viewMode === 'grid'}
              onChange={toggleViewMode}
              color="primary"
            />
          }
          label="网格视图"
        />
      </Box>

      {filterType !== '全部' || filterStatus !== '全部' ? (
        <Box mb={2}>
          <Typography variant="body2" component="span" sx={{ mr: 1 }}>
            当前筛选:
          </Typography>
          {filterType !== '全部' && (
            <Chip 
              label={`类型: ${filterType}`} 
              onDelete={() => setFilterType('全部')} 
              size="small" 
              sx={{ mr: 1 }} 
            />
          )}
          {filterStatus !== '全部' && (
            <Chip 
              label={`状态: ${filterStatus}`} 
              onDelete={() => setFilterStatus('全部')} 
              size="small" 
            />
          )}
        </Box>
      ) : null}

      {viewMode === 'grid' ? (
        <Grid container spacing={3}>
          {filteredDevices.map((device) => (
            <Grid item xs={12} sm={6} md={4} key={device.id}>
              <Card>
                <CardContent>
                  <Box display="flex" alignItems="center" mb={2}>
                    <Box sx={{ mr: 2 }}>
                      {device.icon}
                    </Box>
                    <Box flexGrow={1}>
                      <Typography variant="h6">{device.name}</Typography>
                      <Typography variant="body2" color="text.secondary">
                        {device.id} | {device.model}
                      </Typography>
                    </Box>
                    <Chip
                      label={device.status}
                      color={getStatusColor(device.status) as any}
                      size="small"
                    />
                  </Box>
                  
                  <Divider sx={{ my: 1.5 }} />
                  
                  <Typography variant="body2" sx={{ mb: 0.5 }}>
                    <strong>类型:</strong> {device.type}
                  </Typography>
                  <Typography variant="body2" sx={{ mb: 0.5 }}>
                    <strong>制造商:</strong> {device.manufacturer}
                  </Typography>
                  <Typography variant="body2" sx={{ mb: 0.5 }}>
                    <strong>位置:</strong> {device.location}
                  </Typography>
                  <Typography variant="body2" sx={{ mb: 0.5 }}>
                    <strong>分配给:</strong> {device.assignedTo || '未分配'}
                  </Typography>
                  <Typography variant="body2">
                    <strong>维护日期:</strong> {device.maintenanceDate}
                  </Typography>
                  
                  <Box display="flex" justifyContent="flex-end" mt={2}>
                    <IconButton 
                      color="primary" 
                      size="small"
                      onClick={() => handleOpenDialog(device)}
                    >
                      <EditIcon fontSize="small" />
                    </IconButton>
                    <IconButton 
                      color="error" 
                      size="small"
                      onClick={() => handleDeleteDevice(device.id)}
                    >
                      <DeleteIcon fontSize="small" />
                    </IconButton>
                  </Box>
                </CardContent>
              </Card>
            </Grid>
          ))}
        </Grid>
      ) : (
        <Paper>
          {filteredDevices.map((device, index) => (
            <React.Fragment key={device.id}>
              <Box p={2} display="flex" alignItems="center">
                <Box sx={{ mr: 2 }}>
                  {device.icon}
                </Box>
                <Box flexGrow={1}>
                  <Typography variant="subtitle1">{device.name}</Typography>
                  <Typography variant="body2" color="text.secondary">
                    {device.id} | {device.type} | {device.model}
                  </Typography>
                </Box>
                <Box sx={{ mx: 2 }}>
                  <Chip
                    label={device.status}
                    color={getStatusColor(device.status) as any}
                    size="small"
                  />
                </Box>
                <Box>
                  <IconButton 
                    color="primary" 
                    size="small"
                    onClick={() => handleOpenDialog(device)}
                  >
                    <EditIcon fontSize="small" />
                  </IconButton>
                  <IconButton 
                    color="error" 
                    size="small"
                    onClick={() => handleDeleteDevice(device.id)}
                  >
                    <DeleteIcon fontSize="small" />
                  </IconButton>
                </Box>
              </Box>
              {index < filteredDevices.length - 1 && <Divider />}
            </React.Fragment>
          ))}
        </Paper>
      )}

      {/* 设备表单对话框 */}
      <Dialog open={openDialog} onClose={handleCloseDialog} maxWidth="md" fullWidth>
        <DialogTitle>
          {selectedDevice ? '编辑设备' : '添加设备'}
        </DialogTitle>
        <DialogContent>
          <Grid container spacing={2} sx={{ mt: 1 }}>
            <Grid item xs={12} sm={6}>
              <TextField
                label="设备名称"
                fullWidth
                defaultValue={selectedDevice?.name || ''}
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                label="设备ID"
                fullWidth
                defaultValue={selectedDevice?.id || ''}
                disabled={!!selectedDevice}
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <FormControl fullWidth>
                <InputLabel>设备类型</InputLabel>
                <Select
                  label="设备类型"
                  defaultValue={selectedDevice?.type || ''}
                >
                  {deviceTypes.filter(type => type !== '全部').map((type) => (
                    <MenuItem key={type} value={type}>{type}</MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                label="设备型号"
                fullWidth
                defaultValue={selectedDevice?.model || ''}
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                label="制造商"
                fullWidth
                defaultValue={selectedDevice?.manufacturer || ''}
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                label="购买日期"
                type="date"
                fullWidth
                InputLabelProps={{
                  shrink: true,
                }}
                defaultValue={selectedDevice?.purchaseDate || new Date().toISOString().substr(0, 10)}
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <FormControl fullWidth>
                <InputLabel>设备状态</InputLabel>
                <Select
                  label="设备状态"
                  defaultValue={selectedDevice?.status || '正常使用'}
                >
                  {deviceStatuses.filter(status => status !== '全部').map((status) => (
                    <MenuItem key={status} value={status}>{status}</MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                label="设备位置"
                fullWidth
                defaultValue={selectedDevice?.location || ''}
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                label="分配给"
                fullWidth
                defaultValue={selectedDevice?.assignedTo || ''}
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                label="下次维护日期"
                type="date"
                fullWidth
                InputLabelProps={{
                  shrink: true,
                }}
                defaultValue={selectedDevice?.maintenanceDate || ''}
              />
            </Grid>
          </Grid>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCloseDialog}>取消</Button>
          <Button 
            variant="contained" 
            color="primary"
            onClick={handleSaveDevice}
          >
            保存
          </Button>
        </DialogActions>
      </Dialog>

      {/* 筛选对话框 */}
      <Dialog open={openFilterDialog} onClose={handleCloseDialog} maxWidth="xs" fullWidth>
        <DialogTitle>
          筛选设备
        </DialogTitle>
        <DialogContent>
          <Grid container spacing={2} sx={{ mt: 1 }}>
            <Grid item xs={12}>
              <FormControl fullWidth>
                <InputLabel>设备类型</InputLabel>
                <Select
                  label="设备类型"
                  value={filterType}
                  onChange={(e) => setFilterType(e.target.value as string)}
                >
                  {deviceTypes.map((type) => (
                    <MenuItem key={type} value={type}>{type}</MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12}>
              <FormControl fullWidth>
                <InputLabel>设备状态</InputLabel>
                <Select
                  label="设备状态"
                  value={filterStatus}
                  onChange={(e) => setFilterStatus(e.target.value as string)}
                >
                  {deviceStatuses.map((status) => (
                    <MenuItem key={status} value={status}>{status}</MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Grid>
          </Grid>
        </DialogContent>
        <DialogActions>
          <Button onClick={resetFilters}>重置</Button>
          <Button onClick={applyFilters} variant="contained" color="primary">
            应用筛选
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default DeviceManagement; 
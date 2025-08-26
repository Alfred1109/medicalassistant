import React from 'react';
import {
  Box, Paper, Typography, Button, Grid, FormControl,
  InputLabel, Select, MenuItem, TextField, Divider, Card, CardContent,
  List, ListItem, ListItemIcon, ListItemText, IconButton, Chip, Alert, LinearProgress,
  CircularProgress
} from '@mui/material';
import Checkbox from '@mui/material/Checkbox';
import FormControlLabel from '@mui/material/FormControlLabel';
import FormGroup from '@mui/material/FormGroup';
import ListItemSecondaryAction from '@mui/material/ListItemSecondaryAction';
import { SelectChangeEvent } from '@mui/material/Select';
import DownloadIcon from '@mui/icons-material/Download';
import CalendarTodayIcon from '@mui/icons-material/CalendarToday';
import FileDownloadIcon from '@mui/icons-material/FileDownload';
import DeleteIcon from '@mui/icons-material/Delete';
import DateRangeIcon from '@mui/icons-material/DateRange';
import PersonIcon from '@mui/icons-material/Person';
import DescriptionIcon from '@mui/icons-material/Description';
import AccessTimeIcon from '@mui/icons-material/AccessTime';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import ErrorIcon from '@mui/icons-material/Error';
import FormatListBulletedIcon from '@mui/icons-material/FormatListBulleted';

// 数据类型
type DataType = 'bloodPressure' | 'bloodGlucose' | 'heartRate' | 'exercise' | 'sleep' | 'weight' | 'medication' | 'all';

// 导出格式
type ExportFormat = 'csv' | 'json' | 'pdf' | 'excel';

// 导出状态
type ExportStatus = 'idle' | 'loading' | 'success' | 'error';

// 导出历史记录
interface ExportHistory {
  id: string;
  dataType: DataType | string;
  format: ExportFormat;
  dateRange: {
    start: Date;
    end: Date;
  };
  createdAt: Date;
  status: ExportStatus;
  downloadUrl?: string;
  fileName?: string;
  error?: string;
}

// 组件属性
interface DataExportManagerProps {
  onExportData?: (dataType: DataType, format: ExportFormat, dateRange: { start: Date; end: Date }, options: any) => Promise<string>;
  onDeleteExport?: (exportId: string) => Promise<void>;
  exportHistory?: ExportHistory[];
  patients?: Array<{
    id: string;
    name: string;
  }>;
  loading?: boolean;
  error?: string;
  patientId?: string;
}

const dataTypeOptions = [
  { value: 'all', label: '所有数据' },
  { value: 'bloodPressure', label: '血压' },
  { value: 'bloodGlucose', label: '血糖' },
  { value: 'heartRate', label: '心率' },
  { value: 'exercise', label: '运动' },
  { value: 'sleep', label: '睡眠' },
  { value: 'weight', label: '体重' },
  { value: 'medication', label: '用药' },
];

const formatOptions = [
  { value: 'csv', label: 'CSV' },
  { value: 'json', label: 'JSON' },
  { value: 'excel', label: 'Excel' },
  { value: 'pdf', label: 'PDF' },
];

const DataExportManager: React.FC<DataExportManagerProps> = ({
  onExportData = async () => {
    // 默认实现，模拟导出功能
    return new Promise<void>(resolve => setTimeout(resolve, 2000));
  },
  onDeleteExport,
  exportHistory = [],
  patients = [],
  loading = false,
  error = '',
  patientId
}) => {
  // 状态定义
  const [selectedDataTypes, setSelectedDataTypes] = React.useState<string[]>(['all']);
  const [selectedFormat, setSelectedFormat] = React.useState<string>('csv');
  const [startDate, setStartDate] = React.useState<string>('');
  const [endDate, setEndDate] = React.useState<string>('');
  const [includeDeleted, setIncludeDeleted] = React.useState<boolean>(false);
  const [anonymizeData, setAnonymizeData] = React.useState<boolean>(false);
  const [selectedPatient, setSelectedPatient] = React.useState<string>(patientId || 'all');
  const [exportStatus, setExportStatus] = React.useState<ExportStatus>('idle');
  const [localExportHistory, setLocalExportHistory] = React.useState<ExportHistory[]>([]);
  const [exportError, setExportError] = React.useState<string>('');
  
  // 处理数据类型变更
  const handleDataTypeChange = (event: SelectChangeEvent<string[]>) => {
    setSelectedDataTypes(event.target.value as string[]);
  };
  
  // 处理格式变更
  const handleFormatChange = (event: SelectChangeEvent) => {
    setSelectedFormat(event.target.value as string);
  };
  
  // 处理患者选择变更
  const handlePatientChange = (event: SelectChangeEvent) => {
    setSelectedPatient(event.target.value as string);
  };
  
  // 处理开始日期变更
  const handleStartDateChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    setStartDate(event.target.value);
  };
  
  // 处理结束日期变更
  const handleEndDateChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    setEndDate(event.target.value);
  };
  
  // 处理导出数据
  const handleExport = async () => {
    try {
      setExportStatus('loading');
      
      // 验证日期
      if (startDate && endDate) {
        const startDateObj = new Date(startDate);
        const endDateObj = new Date(endDate);
        
        if (isNaN(startDateObj.getTime()) || isNaN(endDateObj.getTime())) {
          throw new Error('日期格式无效');
        }
        
        if (startDateObj > endDateObj) {
          throw new Error('开始日期不能晚于结束日期');
        }
        
        // 准备选项
        const options = {
          includeDeleted,
          anonymizeData,
          patientId: selectedPatient === 'all' ? undefined : selectedPatient
        };
        
        // 调用导出功能，使用第一个选中的数据类型（为了兼容旧逻辑）
        // 实际应用中可能需要支持多类型导出
        const dataType = selectedDataTypes.length > 0 ? selectedDataTypes[0] as DataType : 'all';
        
        await onExportData(dataType, selectedFormat as ExportFormat, { start: startDateObj, end: endDateObj }, options);
        setExportStatus('success');
        
        // 添加导出历史记录
        const newHistoryItem: ExportHistory = {
          id: Date.now().toString(),
          dataType: dataType,
          format: selectedFormat as ExportFormat,
          dateRange: { start: startDateObj, end: endDateObj },
          createdAt: new Date(),
          status: 'success'
        };
        
        setLocalExportHistory(prev => [newHistoryItem, ...prev]);
      } else {
        throw new Error('请选择导出日期范围');
      }
    } catch (err: any) {
      setExportStatus('error');
      console.error('导出错误:', err.message);
      setExportError(err.message);
    }
  };
  
  // 处理删除导出记录
  const handleDeleteExport = async (exportId: string) => {
    if (!onDeleteExport) return;
    
    try {
      await onDeleteExport(exportId);
    } catch (error) {
      console.error('删除导出记录失败:', error);
    }
  };
  
  // 格式化日期
  const formatDate = (date: Date) => {
    return new Date(date).toLocaleString();
  };
  
  // 获取数据类型标签
  const getDataTypeLabel = (type: string) => {
    const option = dataTypeOptions.find(opt => opt.value === type);
    return option ? option.label : type;
  };
  
  // 渲染状态图标
  const renderStatusIcon = (status: ExportStatus) => {
    switch (status) {
      case 'success':
        return <CheckCircleIcon color="success" />;
      case 'error':
        return <ErrorIcon color="error" />;
      case 'loading':
        return <CircularProgress size={20} />;
      default:
        return null;
    }
  };
  
  // 显示导出历史
  const renderExportHistory = () => {
    // 优先使用从props传入的导出历史，如果没有则使用本地状态的导出历史
    const historyToDisplay = exportHistory.length > 0 ? exportHistory : localExportHistory;
    
    if (historyToDisplay.length === 0) {
      return (
        <Typography variant="body2" color="textSecondary" sx={{ py: 2, textAlign: 'center' }}>
          暂无导出历史记录
        </Typography>
      );
    }
    
    return (
      <List>
        {historyToDisplay.map((item) => (
          <ListItem key={item.id} divider>
            <ListItemIcon>
              {item.format === 'csv' && <DescriptionIcon />}
              {item.format === 'json' && <DescriptionIcon />}
              {item.format === 'pdf' && <DescriptionIcon />}
              {item.format === 'excel' && <DescriptionIcon />}
            </ListItemIcon>
            <ListItemText
              primary={
                <Box sx={{ display: 'flex', alignItems: 'center' }}>
                  <Typography variant="subtitle1" component="span">
                    {item.fileName || `${getDataTypeLabel(item.dataType)}-${item.format}`}
                  </Typography>
                  <Box ml={1} display="inline-flex">
                    {renderStatusIcon(item.status)}
                  </Box>
                </Box>
              }
              secondary={
                <React.Fragment>
                  <Box sx={{ display: 'flex', flexDirection: 'column', mt: 1 }}>
                    <Box sx={{ display: 'flex', alignItems: 'center', mb: 0.5 }}>
                      <DateRangeIcon fontSize="small" sx={{ mr: 0.5, fontSize: 16, color: 'text.secondary' }} />
                      <Typography variant="body2" color="textSecondary" component="span">
                        {formatDate(item.dateRange.start)} - {formatDate(item.dateRange.end)}
                      </Typography>
                    </Box>
                    <Box sx={{ display: 'flex', alignItems: 'center' }}>
                      <AccessTimeIcon fontSize="small" sx={{ mr: 0.5, fontSize: 16, color: 'text.secondary' }} />
                      <Typography variant="body2" color="textSecondary" component="span">
                        {formatDate(item.createdAt)}
                      </Typography>
                    </Box>
                  </Box>
                </React.Fragment>
              }
            />
            <ListItemSecondaryAction>
              {item.status === 'success' && item.downloadUrl && (
                <IconButton 
                  edge="end" 
                  component="a"
                  href={item.downloadUrl}
                  download
                  sx={{ mr: 1 }}
                >
                  <DownloadIcon />
                </IconButton>
              )}
              <IconButton 
                edge="end" 
                onClick={() => handleDeleteExport(item.id)}
              >
                <DeleteIcon />
              </IconButton>
            </ListItemSecondaryAction>
          </ListItem>
        ))}
      </List>
    );
  };
  
  return (
    <Box>
      <Typography variant="h5" gutterBottom>
        数据导出管理
      </Typography>
      
      <Grid container spacing={3}>
        {/* 导出设置卡片 */}
        <Grid item xs={12} md={6}>
          <Card variant="outlined">
            <CardContent>
              <Typography variant="h6" gutterBottom>
                导出设置
              </Typography>
              
              <Grid container spacing={2}>
                <Grid item xs={12} sm={6}>
                  <FormControl fullWidth sx={{ mb: 2 }}>
                    <InputLabel id="data-type-label">数据类型</InputLabel>
                    <Select
                      labelId="data-type-label"
                      value={selectedDataTypes}
                      onChange={handleDataTypeChange}
                      label="数据类型"
                      multiple
                    >
                      {dataTypeOptions.map(option => (
                        <MenuItem key={option.value} value={option.value}>
                          {option.label}
                        </MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                </Grid>
                
                <Grid item xs={12} sm={6}>
                  <FormControl fullWidth sx={{ mb: 2 }}>
                    <InputLabel id="format-label">导出格式</InputLabel>
                    <Select
                      labelId="format-label"
                      value={selectedFormat}
                      onChange={handleFormatChange}
                      label="导出格式"
                    >
                      {formatOptions.map(option => (
                        <MenuItem key={option.value} value={option.value}>
                          {option.label}
                        </MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                </Grid>
                
                <Grid item xs={12}>
                  <FormControl fullWidth margin="normal">
                    <InputLabel id="patient-label">患者</InputLabel>
                    <Select
                      labelId="patient-label"
                      value={selectedPatient}
                      onChange={handlePatientChange}
                      label="患者"
                    >
                      <MenuItem value="">所有患者</MenuItem>
                      {patients.map(patient => (
                        <MenuItem key={patient.id} value={patient.id}>
                          {patient.name}
                        </MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                </Grid>
                
                <Grid item xs={12} sm={6}>
                  <TextField
                    label="开始日期"
                    type="date"
                    fullWidth
                    margin="normal"
                    value={startDate}
                    onChange={handleStartDateChange}
                    InputLabelProps={{
                      shrink: true,
                    }}
                  />
                </Grid>
                
                <Grid item xs={12} sm={6}>
                  <TextField
                    label="结束日期"
                    type="date"
                    fullWidth
                    margin="normal"
                    value={endDate}
                    onChange={handleEndDateChange}
                    InputLabelProps={{
                      shrink: true,
                    }}
                  />
                </Grid>
                
                <Grid item xs={12}>
                  <FormGroup>
                    <FormControlLabel
                      control={
                        <Checkbox
                          checked={includeDeleted}
                          onChange={() => setIncludeDeleted(!includeDeleted)}
                        />
                      }
                      label="包括已删除的数据"
                    />
                    <FormControlLabel
                      control={
                        <Checkbox
                          checked={anonymizeData}
                          onChange={() => setAnonymizeData(!anonymizeData)}
                        />
                      }
                      label="匿名化数据"
                    />
                  </FormGroup>
                </Grid>
                
                <Grid item xs={12}>
                  <Divider sx={{ my: 2 }} />
                  
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <Box>
                      {exportStatus === 'success' && (
                        <Chip
                          icon={<CheckCircleIcon />}
                          label="导出成功"
                          color="success"
                          variant="outlined"
                        />
                      )}
                      
                      {exportStatus === 'error' && (
                        <Typography color="error" variant="body2">
                          {exportError}
                        </Typography>
                      )}
                    </Box>
                    
                    <Button
                      variant="contained"
                      color="primary"
                      startIcon={<FileDownloadIcon />}
                      onClick={handleExport}
                      disabled={exportStatus === 'loading' || !startDate || !endDate}
                    >
                      {exportStatus === 'loading' ? '导出中...' : '导出数据'}
                    </Button>
                  </Box>
                  
                  {exportStatus === 'loading' && (
                    <LinearProgress sx={{ mt: 2 }} />
                  )}
                </Grid>
              </Grid>
            </CardContent>
          </Card>
        </Grid>
        
        {/* 导出历史卡片 */}
        <Grid item xs={12} md={6}>
          <Card variant="outlined" sx={{ height: '100%' }}>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                导出历史
              </Typography>
              
              {loading ? (
                <Box sx={{ display: 'flex', justifyContent: 'center', p: 3 }}>
                  <CircularProgress />
                </Box>
              ) : error ? (
                <Alert severity="error" sx={{ mb: 2 }}>
                  {error}
                </Alert>
              ) : renderExportHistory()}
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </Box>
  );
};

export default DataExportManager; 
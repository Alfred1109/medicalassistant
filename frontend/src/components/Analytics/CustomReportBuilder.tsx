import React, { useState } from 'react';
import {
  Box,
  Paper,
  Typography,
  Grid,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  TextField,
  Button,
  IconButton,
  Card,
  CardContent,
  CardActions,
  Divider,
  Chip,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  FormControlLabel,
  Checkbox,
  CircularProgress,
  Alert
} from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import DeleteIcon from '@mui/icons-material/Delete';
import FileDownloadIcon from '@mui/icons-material/FileDownload';
import LineChartIcon from '@mui/icons-material/ShowChart';
import BarChartIcon from '@mui/icons-material/BarChart';
import PieChartIcon from '@mui/icons-material/PieChart';
import TableChartIcon from '@mui/icons-material/TableChart';
import EmailIcon from '@mui/icons-material/Email';
import { 
  ChartDataType, 
  TimeRange, 
  ChartType, 
  ReportConfig 
} from '../../types/dataAnalysis';

interface CustomReportBuilderProps {
  onSaveReport?: (report: ReportConfig) => Promise<void>;
  onExportReport?: (report: ReportConfig, format: string) => Promise<void>;
  onScheduleReport?: (report: ReportConfig, schedule: any) => Promise<void>;
}

/**
 * 自定义报表生成器组件
 * 允许用户创建、配置和导出自定义报表
 */
const CustomReportBuilder: React.FC<CustomReportBuilderProps> = ({
  onSaveReport,
  onExportReport,
  onScheduleReport
}) => {
  // 状态
  const [reportTitle, setReportTitle] = useState('');
  const [reportDescription, setReportDescription] = useState('');
  const [charts, setCharts] = useState<Array<{
    id: string;
    type: ChartType;
    title: string;
    dataType: ChartDataType;
    timeRange: TimeRange;
  }>>([]);
  const [isScheduleDialogOpen, setIsScheduleDialogOpen] = useState(false);
  const [scheduleConfig, setScheduleConfig] = useState({
    enabled: false,
    frequency: 'weekly',
    recipients: ''
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // 添加图表
  const handleAddChart = () => {
    const newChart = {
      id: `chart-${Date.now()}`,
      type: 'line' as ChartType,
      title: `图表 ${charts.length + 1}`,
      dataType: 'patient' as ChartDataType,
      timeRange: 'month' as TimeRange
    };
    
    setCharts([...charts, newChart]);
  };

  // 移除图表
  const handleRemoveChart = (chartId: string) => {
    setCharts(charts.filter(chart => chart.id !== chartId));
  };

  // 更新图表属性
  const handleChartChange = (chartId: string, property: string, value: any) => {
    setCharts(charts.map(chart => 
      chart.id === chartId 
        ? { ...chart, [property]: value } 
        : chart
    ));
  };

  // 打开调度对话框
  const handleOpenScheduleDialog = () => {
    setIsScheduleDialogOpen(true);
  };

  // 关闭调度对话框
  const handleCloseScheduleDialog = () => {
    setIsScheduleDialogOpen(false);
  };

  // 保存调度配置
  const handleSaveSchedule = () => {
    setIsScheduleDialogOpen(false);
    
    // 显示成功消息
    setSuccessMessage('报表调度计划已保存，将按计划自动发送');
    
    // 清除成功消息
    setTimeout(() => {
      setSuccessMessage(null);
    }, 3000);
  };

  // 导出报表
  const handleExportReport = async (format: string) => {
    if (!reportTitle) {
      setError('请输入报表标题');
      return;
    }
    
    if (charts.length === 0) {
      setError('请至少添加一个图表');
      return;
    }
    
    setError(null);
    setLoading(true);
    
    try {
      const reportConfig: ReportConfig = {
        title: reportTitle,
        description: reportDescription,
        charts: charts,
        createdAt: new Date(),
        ...(scheduleConfig.enabled && {
          scheduledDelivery: {
            enabled: true,
            frequency: scheduleConfig.frequency as 'daily' | 'weekly' | 'monthly',
            recipients: scheduleConfig.recipients.split(',').map(r => r.trim())
          }
        })
      };
      
      if (onExportReport) {
        await onExportReport(reportConfig, format);
      }
      
      setSuccessMessage('报表导出成功');
    } catch (error) {
      setError('报表导出失败');
      console.error('导出报表失败:', error);
    } finally {
      setLoading(false);
      
      // 清除成功消息
      setTimeout(() => {
        setSuccessMessage(null);
      }, 3000);
    }
  };

  // 保存报表
  const handleSaveReport = async () => {
    if (!reportTitle) {
      setError('请输入报表标题');
      return;
    }
    
    if (charts.length === 0) {
      setError('请至少添加一个图表');
      return;
    }
    
    setError(null);
    setLoading(true);
    
    try {
      const reportConfig: ReportConfig = {
        title: reportTitle,
        description: reportDescription,
        charts: charts,
        createdAt: new Date(),
        ...(scheduleConfig.enabled && {
          scheduledDelivery: {
            enabled: true,
            frequency: scheduleConfig.frequency as 'daily' | 'weekly' | 'monthly',
            recipients: scheduleConfig.recipients.split(',').map(r => r.trim())
          }
        })
      };
      
      if (onSaveReport) {
        await onSaveReport(reportConfig);
      }
      
      setSuccessMessage('报表已保存');
    } catch (error) {
      setError('保存报表失败');
      console.error('保存报表失败:', error);
    } finally {
      setLoading(false);
      
      // 清除成功消息
      setTimeout(() => {
        setSuccessMessage(null);
      }, 3000);
    }
  };

  // 渲染图表类型图标
  const renderChartTypeIcon = (type: ChartType) => {
    switch (type) {
      case 'line':
        return <LineChartIcon />;
      case 'bar':
        return <BarChartIcon />;
      case 'pie':
        return <PieChartIcon />;
      default:
        return <TableChartIcon />;
    }
  };

  return (
    <Box>
      <Paper sx={{ p: 3, mb: 3 }}>
        <Typography variant="h6" gutterBottom>
          自定义报表生成器
        </Typography>
        <Divider sx={{ mb: 3 }} />
        
        {/* 报表基本信息 */}
        <Grid container spacing={3} mb={3}>
          <Grid item xs={12} md={6}>
            <TextField
              fullWidth
              label="报表标题"
              value={reportTitle}
              onChange={(e) => setReportTitle(e.target.value)}
              required
              error={!reportTitle}
              helperText={!reportTitle ? '请输入报表标题' : ''}
            />
          </Grid>
          <Grid item xs={12} md={6}>
            <TextField
              fullWidth
              label="报表描述"
              value={reportDescription}
              onChange={(e) => setReportDescription(e.target.value)}
              multiline
              rows={1}
            />
          </Grid>
        </Grid>
        
        {/* 错误和成功消息 */}
        {error && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {error}
          </Alert>
        )}
        
        {successMessage && (
          <Alert severity="success" sx={{ mb: 2 }}>
            {successMessage}
          </Alert>
        )}
        
        {/* 报表图表列表 */}
        <Box mb={3}>
          <Typography variant="subtitle1" gutterBottom>
            报表内容
          </Typography>
          
          <Grid container spacing={3}>
            {charts.map((chart) => (
              <Grid item xs={12} md={6} key={chart.id}>
                <Card variant="outlined">
                  <CardContent>
                    <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
                      <Box display="flex" alignItems="center">
                        {renderChartTypeIcon(chart.type)}
                        <Typography variant="subtitle1" sx={{ ml: 1 }}>
                          {chart.title}
                        </Typography>
                      </Box>
                      <IconButton onClick={() => handleRemoveChart(chart.id)} size="small">
                        <DeleteIcon fontSize="small" />
                      </IconButton>
                    </Box>
                    
                    <Grid container spacing={2}>
                      <Grid item xs={12}>
                        <TextField
                          fullWidth
                          label="图表标题"
                          value={chart.title}
                          onChange={(e) => handleChartChange(chart.id, 'title', e.target.value)}
                          size="small"
                        />
                      </Grid>
                      <Grid item xs={12} sm={4}>
                        <FormControl fullWidth size="small">
                          <InputLabel>图表类型</InputLabel>
                          <Select
                            value={chart.type}
                            label="图表类型"
                            onChange={(e) => handleChartChange(chart.id, 'type', e.target.value)}
                          >
                            <MenuItem value="line">折线图</MenuItem>
                            <MenuItem value="bar">柱状图</MenuItem>
                            <MenuItem value="pie">饼图</MenuItem>
                            <MenuItem value="area">区域图</MenuItem>
                          </Select>
                        </FormControl>
                      </Grid>
                      <Grid item xs={12} sm={4}>
                        <FormControl fullWidth size="small">
                          <InputLabel>数据类型</InputLabel>
                          <Select
                            value={chart.dataType}
                            label="数据类型"
                            onChange={(e) => handleChartChange(chart.id, 'dataType', e.target.value)}
                          >
                            <MenuItem value="patient">患者数据</MenuItem>
                            <MenuItem value="doctor">医生数据</MenuItem>
                            <MenuItem value="device">设备数据</MenuItem>
                            <MenuItem value="rehabilitation">康复数据</MenuItem>
                          </Select>
                        </FormControl>
                      </Grid>
                      <Grid item xs={12} sm={4}>
                        <FormControl fullWidth size="small">
                          <InputLabel>时间范围</InputLabel>
                          <Select
                            value={chart.timeRange}
                            label="时间范围"
                            onChange={(e) => handleChartChange(chart.id, 'timeRange', e.target.value)}
                          >
                            <MenuItem value="day">今日</MenuItem>
                            <MenuItem value="week">本周</MenuItem>
                            <MenuItem value="month">本月</MenuItem>
                            <MenuItem value="quarter">本季度</MenuItem>
                            <MenuItem value="year">本年度</MenuItem>
                          </Select>
                        </FormControl>
                      </Grid>
                    </Grid>
                  </CardContent>
                </Card>
              </Grid>
            ))}
            
            {/* 添加图表按钮 */}
            <Grid item xs={12} md={6}>
              <Card 
                variant="outlined" 
                sx={{ 
                  height: '100%', 
                  display: 'flex', 
                  alignItems: 'center', 
                  justifyContent: 'center',
                  border: '1px dashed grey',
                  cursor: 'pointer'
                }}
                onClick={handleAddChart}
              >
                <CardContent>
                  <Box textAlign="center">
                    <AddIcon fontSize="large" color="primary" />
                    <Typography variant="subtitle1" color="primary">
                      添加图表
                    </Typography>
                  </Box>
                </CardContent>
              </Card>
            </Grid>
          </Grid>
        </Box>
        
        {/* 操作按钮 */}
        <Box display="flex" justifyContent="space-between">
          <Box>
            <Button 
              variant="outlined" 
              startIcon={<EmailIcon />} 
              onClick={handleOpenScheduleDialog}
              sx={{ mr: 1 }}
            >
              定时发送
            </Button>
          </Box>
          <Box>
            <Button 
              variant="outlined" 
              startIcon={<FileDownloadIcon />} 
              onClick={() => handleExportReport('pdf')}
              disabled={loading}
              sx={{ mr: 1 }}
            >
              导出PDF
            </Button>
            <Button 
              variant="outlined" 
              startIcon={<FileDownloadIcon />} 
              onClick={() => handleExportReport('xlsx')}
              disabled={loading}
              sx={{ mr: 1 }}
            >
              导出Excel
            </Button>
            <Button 
              variant="contained" 
              color="primary" 
              onClick={handleSaveReport}
              disabled={loading}
            >
              {loading ? <CircularProgress size={24} /> : '保存报表'}
            </Button>
          </Box>
        </Box>
      </Paper>
      
      {/* 定时发送对话框 */}
      <Dialog open={isScheduleDialogOpen} onClose={handleCloseScheduleDialog}>
        <DialogTitle>定时发送报表</DialogTitle>
        <DialogContent>
          <Box sx={{ pt: 1 }}>
            <FormControlLabel
              control={
                <Checkbox 
                  checked={scheduleConfig.enabled}
                  onChange={(e) => setScheduleConfig({...scheduleConfig, enabled: e.target.checked})}
                />
              }
              label="启用定时发送"
            />
            
            <FormControl fullWidth sx={{ mt: 2 }}>
              <InputLabel>发送频率</InputLabel>
              <Select
                value={scheduleConfig.frequency}
                label="发送频率"
                onChange={(e) => setScheduleConfig({...scheduleConfig, frequency: e.target.value})}
                disabled={!scheduleConfig.enabled}
              >
                <MenuItem value="daily">每日</MenuItem>
                <MenuItem value="weekly">每周</MenuItem>
                <MenuItem value="monthly">每月</MenuItem>
              </Select>
            </FormControl>
            
            <TextField
              fullWidth
              label="收件人邮箱"
              placeholder="多个邮箱使用逗号分隔"
              value={scheduleConfig.recipients}
              onChange={(e) => setScheduleConfig({...scheduleConfig, recipients: e.target.value})}
              disabled={!scheduleConfig.enabled}
              sx={{ mt: 2 }}
            />
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCloseScheduleDialog}>取消</Button>
          <Button onClick={handleSaveSchedule} variant="contained" color="primary">
            保存
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default CustomReportBuilder; 
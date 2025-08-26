import React, { useState, useEffect } from 'react';
import {
  Box,
  Card,
  CardContent,
  CardHeader,
  Chip,
  Divider,
  Grid,
  IconButton,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
  ListItemSecondaryAction,
  Paper,
  Typography,
  Button,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogContentText,
  DialogActions,
  Alert,
  LinearProgress,
  Tooltip,
  Badge
} from '@mui/material';
import {
  Warning as WarningIcon,
  Error as ErrorIcon,
  Info as InfoIcon,
  Notifications as NotificationsIcon,
  NotificationsActive as NotificationsActiveIcon,
  Settings as SettingsIcon,
  MoreVert as MoreVertIcon,
  GetApp as DownloadIcon,
  Close as CloseIcon,
  Visibility as VisibilityIcon,
  CheckCircle as CheckCircleIcon,
  DevicesOther as DeviceIcon,
  BloodtypeOutlined as BloodIcon,
  MonitorHeart as HeartIcon,
  Thermostat as ThermostatIcon,
  Scale as ScaleIcon,
  ReportProblem as ReportIcon,
  AccessTime as TimeIcon
} from '@mui/icons-material';

// 定义数据异常类型
interface DataAnomaly {
  id: string;
  deviceId: string;
  deviceName: string;
  metricName: string;
  metricType: 'heart_rate' | 'blood_pressure' | 'blood_sugar' | 'temperature' | 'weight' | 'oxygen';
  value: number | string;
  thresholdType: 'upper' | 'lower' | 'range' | 'pattern';
  severity: 'info' | 'warning' | 'critical';
  timestamp: string;
  status: 'new' | 'acknowledged' | 'resolved';
  description: string;
  patientId?: string;
  patientName?: string;
}

const DeviceAnomalyAlert: React.FC = () => {
  const [anomalies, setAnomalies] = useState<DataAnomaly[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [selectedAnomaly, setSelectedAnomaly] = useState<DataAnomaly | null>(null);
  const [detailsDialogOpen, setDetailsDialogOpen] = useState<boolean>(false);
  const [filtersDialogOpen, setFiltersDialogOpen] = useState<boolean>(false);
  const [filters, setFilters] = useState({
    showAcknowledged: false,
    showResolved: false,
    severityFilters: ['info', 'warning', 'critical'],
    deviceFilters: []
  });

  // 模拟获取异常数据
  useEffect(() => {
    const fetchAnomalies = async () => {
      setLoading(true);
      
      // 模拟API调用
      setTimeout(() => {
        const mockAnomalies: DataAnomaly[] = [
          {
            id: '1',
            deviceId: 'dev-123',
            deviceName: '心率监测手表',
            metricName: '心率',
            metricType: 'heart_rate',
            value: '115 bpm',
            thresholdType: 'upper',
            severity: 'warning',
            timestamp: new Date(Date.now() - 25 * 60000).toISOString(), // 25分钟前
            status: 'new',
            description: '静息心率超过正常范围(60-100 bpm)',
            patientId: 'pt-001',
            patientName: '张明'
          },
          {
            id: '2',
            deviceId: 'dev-456',
            deviceName: '血压监测仪',
            metricName: '血压',
            metricType: 'blood_pressure',
            value: '160/100 mmHg',
            thresholdType: 'upper',
            severity: 'critical',
            timestamp: new Date(Date.now() - 2 * 60 * 60000).toISOString(), // 2小时前
            status: 'acknowledged',
            description: '血压显著高于正常范围(90-140/60-90 mmHg)',
            patientId: 'pt-002',
            patientName: '李华'
          },
          {
            id: '3',
            deviceId: 'dev-789',
            deviceName: '血糖监测仪',
            metricName: '血糖',
            metricType: 'blood_sugar',
            value: '65 mg/dL',
            thresholdType: 'lower',
            severity: 'warning',
            timestamp: new Date(Date.now() - 10 * 60000).toISOString(), // 10分钟前
            status: 'new',
            description: '血糖低于正常范围(70-140 mg/dL)',
            patientId: 'pt-003',
            patientName: '王芳'
          },
          {
            id: '4',
            deviceId: 'dev-234',
            deviceName: '体温计',
            metricName: '体温',
            metricType: 'temperature',
            value: '38.5 °C',
            thresholdType: 'upper',
            severity: 'warning',
            timestamp: new Date(Date.now() - 45 * 60000).toISOString(), // 45分钟前
            status: 'new',
            description: '体温超过正常范围(36.1-37.2 °C)',
            patientId: 'pt-002',
            patientName: '李华'
          },
          {
            id: '5',
            deviceId: 'dev-123',
            deviceName: '心率监测手表',
            metricName: '心率模式',
            metricType: 'heart_rate',
            value: '异常心率模式',
            thresholdType: 'pattern',
            severity: 'info',
            timestamp: new Date(Date.now() - 3 * 60 * 60000).toISOString(), // 3小时前
            status: 'resolved',
            description: '检测到不规则的心率模式',
            patientId: 'pt-001',
            patientName: '张明'
          }
        ];
        
        setAnomalies(mockAnomalies);
        setLoading(false);
      }, 1000);
    };
    
    fetchAnomalies();
  }, []);

  // 根据筛选条件过滤异常数据
  const filteredAnomalies = anomalies.filter(anomaly => {
    // 筛选状态
    if (anomaly.status === 'acknowledged' && !filters.showAcknowledged) return false;
    if (anomaly.status === 'resolved' && !filters.showResolved) return false;
    
    // 筛选严重程度
    if (!filters.severityFilters.includes(anomaly.severity)) return false;
    
    // 筛选设备类型
    if (filters.deviceFilters.length > 0 && !filters.deviceFilters.includes(anomaly.deviceId)) return false;
    
    return true;
  });

  // 处理查看异常详情
  const handleViewDetails = (anomaly: DataAnomaly) => {
    setSelectedAnomaly(anomaly);
    setDetailsDialogOpen(true);
  };

  // 处理确认异常
  const handleAcknowledge = (anomalyId: string) => {
    setAnomalies(prevAnomalies => 
      prevAnomalies.map(anomaly => 
        anomaly.id === anomalyId 
          ? { ...anomaly, status: 'acknowledged' } 
          : anomaly
      )
    );
    
    if (selectedAnomaly?.id === anomalyId) {
      setSelectedAnomaly({
        ...selectedAnomaly,
        status: 'acknowledged'
      });
    }
  };

  // 处理解决异常
  const handleResolve = (anomalyId: string) => {
    setAnomalies(prevAnomalies => 
      prevAnomalies.map(anomaly => 
        anomaly.id === anomalyId 
          ? { ...anomaly, status: 'resolved' } 
          : anomaly
      )
    );
    
    if (selectedAnomaly?.id === anomalyId) {
      setSelectedAnomaly({
        ...selectedAnomaly,
        status: 'resolved'
      });
    }
    
    setDetailsDialogOpen(false);
  };

  // 获取异常图标
  const getAnomalyIcon = (metricType: string) => {
    switch (metricType) {
      case 'heart_rate':
        return <HeartIcon />;
      case 'blood_pressure':
      case 'blood_sugar':
        return <BloodIcon />;
      case 'temperature':
        return <ThermostatIcon />;
      case 'weight':
        return <ScaleIcon />;
      default:
        return <DeviceIcon />;
    }
  };

  // 获取严重程度颜色和图标
  const getSeverityDetails = (severity: string) => {
    switch (severity) {
      case 'critical':
        return { color: 'error', icon: <ErrorIcon color="error" /> };
      case 'warning':
        return { color: 'warning', icon: <WarningIcon color="warning" /> };
      case 'info':
        return { color: 'info', icon: <InfoIcon color="info" /> };
      default:
        return { color: 'default', icon: <InfoIcon color="disabled" /> };
    }
  };

  // 格式化时间戳
  const formatTimestamp = (timestamp: string) => {
    const date = new Date(timestamp);
    return date.toLocaleString('zh-CN', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  // 计算相对时间
  const getRelativeTime = (timestamp: string) => {
    const now = new Date();
    const date = new Date(timestamp);
    const diffMinutes = Math.floor((now.getTime() - date.getTime()) / (1000 * 60));
    
    if (diffMinutes < 1) return '刚刚';
    if (diffMinutes < 60) return `${diffMinutes}分钟前`;
    
    const diffHours = Math.floor(diffMinutes / 60);
    if (diffHours < 24) return `${diffHours}小时前`;
    
    const diffDays = Math.floor(diffHours / 24);
    return `${diffDays}天前`;
  };

  // 获取状态标签
  const getStatusChip = (status: string) => {
    switch (status) {
      case 'new':
        return <Chip size="small" color="error" label="新异常" />;
      case 'acknowledged':
        return <Chip size="small" color="warning" label="已确认" />;
      case 'resolved':
        return <Chip size="small" color="success" label="已解决" />;
      default:
        return <Chip size="small" label={status} />;
    }
  };

  // 统计异常数量
  const newAnomaliesCount = anomalies.filter(a => a.status === 'new').length;
  const acknowledgedAnomaliesCount = anomalies.filter(a => a.status === 'acknowledged').length;
  const resolvedAnomaliesCount = anomalies.filter(a => a.status === 'resolved').length;

  // 根据严重性统计
  const criticalAnomaliesCount = anomalies.filter(a => a.severity === 'critical').length;
  const warningAnomaliesCount = anomalies.filter(a => a.severity === 'warning').length;
  const infoAnomaliesCount = anomalies.filter(a => a.severity === 'info').length;

  return (
    <Box sx={{ width: '100%' }}>
      {loading ? (
        <Box sx={{ width: '100%', mt: 2 }}>
          <LinearProgress />
          <Typography sx={{ mt: 1, textAlign: 'center' }} variant="body2" color="text.secondary">
            正在加载异常数据...
          </Typography>
        </Box>
      ) : (
        <>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
            <Typography variant="h6" component="h2">
              设备数据异常监控
              {newAnomaliesCount > 0 && (
                <Badge 
                  badgeContent={newAnomaliesCount} 
                  color="error" 
                  sx={{ ml: 1.5 }}
                >
                  <NotificationsActiveIcon color="action" />
                </Badge>
              )}
            </Typography>
            <Box>
              <Button
                variant="outlined"
                startIcon={<SettingsIcon />}
                size="small"
                onClick={() => setFiltersDialogOpen(true)}
              >
                筛选设置
              </Button>
            </Box>
          </Box>

          <Grid container spacing={2} sx={{ mb: 2 }}>
            <Grid item xs={12} sm={4}>
              <Paper sx={{ p: 2, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <Box>
                  <Typography variant="body2" color="text.secondary">新异常</Typography>
                  <Typography variant="h4">{newAnomaliesCount}</Typography>
                </Box>
                <ErrorIcon color="error" sx={{ fontSize: 40 }} />
              </Paper>
            </Grid>
            <Grid item xs={12} sm={4}>
              <Paper sx={{ p: 2, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <Box>
                  <Typography variant="body2" color="text.secondary">已确认</Typography>
                  <Typography variant="h4">{acknowledgedAnomaliesCount}</Typography>
                </Box>
                <WarningIcon color="warning" sx={{ fontSize: 40 }} />
              </Paper>
            </Grid>
            <Grid item xs={12} sm={4}>
              <Paper sx={{ p: 2, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <Box>
                  <Typography variant="body2" color="text.secondary">已解决</Typography>
                  <Typography variant="h4">{resolvedAnomaliesCount}</Typography>
                </Box>
                <CheckCircleIcon color="success" sx={{ fontSize: 40 }} />
              </Paper>
            </Grid>
          </Grid>

          {filteredAnomalies.length === 0 ? (
            <Alert severity="info" sx={{ mt: 2 }}>
              没有符合筛选条件的异常数据
            </Alert>
          ) : (
            <List>
              {filteredAnomalies.map((anomaly) => {
                const severityDetails = getSeverityDetails(anomaly.severity);
                
                return (
                  <Paper
                    key={anomaly.id}
                    variant="outlined"
                    sx={{ 
                      mb: 2, 
                      borderLeft: 4, 
                      borderColor: `${severityDetails.color}.main`,
                      bgcolor: anomaly.status === 'resolved' ? 'action.hover' : 'background.paper'
                    }}
                  >
                    <ListItem
                      secondaryAction={
                        <Box>
                          {getStatusChip(anomaly.status)}
                          <IconButton 
                            edge="end" 
                            onClick={() => handleViewDetails(anomaly)}
                            sx={{ ml: 1 }}
                          >
                            <VisibilityIcon />
                          </IconButton>
                        </Box>
                      }
                    >
                      <ListItemIcon>
                        {getAnomalyIcon(anomaly.metricType)}
                      </ListItemIcon>
                      <ListItemText
                        primary={
                          <Box sx={{ display: 'flex', alignItems: 'center' }}>
                            {severityDetails.icon}
                            <Typography variant="subtitle1" component="span" sx={{ ml: 1 }}>
                              {anomaly.deviceName} - {anomaly.metricName}
                            </Typography>
                          </Box>
                        }
                        secondary={
                          <>
                            <Typography variant="body2" component="span" color="text.primary">
                              值: {anomaly.value}
                            </Typography>
                            <Typography 
                              variant="body2" 
                              component="span" 
                              color="text.secondary"
                              sx={{ display: 'block' }}
                            >
                              患者: {anomaly.patientName} | 
                              <Tooltip title={formatTimestamp(anomaly.timestamp)}>
                                <Box component="span" sx={{ display: 'inline-flex', alignItems: 'center', ml: 1 }}>
                                  <TimeIcon fontSize="small" sx={{ mr: 0.5, fontSize: 16 }} />
                                  {getRelativeTime(anomaly.timestamp)}
                                </Box>
                              </Tooltip>
                            </Typography>
                          </>
                        }
                      />
                    </ListItem>
                  </Paper>
                );
              })}
            </List>
          )}

          {/* 异常详情对话框 */}
          <Dialog
            open={detailsDialogOpen}
            onClose={() => setDetailsDialogOpen(false)}
            maxWidth="sm"
            fullWidth
          >
            {selectedAnomaly && (
              <>
                <DialogTitle>
                  <Box sx={{ display: 'flex', alignItems: 'center' }}>
                    {getAnomalyIcon(selectedAnomaly.metricType)}
                    <Typography variant="h6" sx={{ ml: 1 }}>
                      {selectedAnomaly.deviceName} 异常详情
                    </Typography>
                  </Box>
                </DialogTitle>
                <DialogContent dividers>
                  <Alert 
                    severity={selectedAnomaly.severity as "error" | "warning" | "info"}
                    sx={{ mb: 2 }}
                  >
                    {selectedAnomaly.description}
                  </Alert>
                  
                  <Grid container spacing={2}>
                    <Grid item xs={6}>
                      <Typography variant="subtitle2">患者</Typography>
                      <Typography variant="body2" gutterBottom>{selectedAnomaly.patientName}</Typography>
                    </Grid>
                    <Grid item xs={6}>
                      <Typography variant="subtitle2">指标</Typography>
                      <Typography variant="body2" gutterBottom>{selectedAnomaly.metricName}</Typography>
                    </Grid>
                    <Grid item xs={6}>
                      <Typography variant="subtitle2">读数</Typography>
                      <Typography variant="body2" gutterBottom>{selectedAnomaly.value}</Typography>
                    </Grid>
                    <Grid item xs={6}>
                      <Typography variant="subtitle2">时间</Typography>
                      <Typography variant="body2" gutterBottom>{formatTimestamp(selectedAnomaly.timestamp)}</Typography>
                    </Grid>
                    <Grid item xs={6}>
                      <Typography variant="subtitle2">严重程度</Typography>
                      <Chip 
                        size="small" 
                        label={
                          selectedAnomaly.severity === 'critical' ? '严重' :
                          selectedAnomaly.severity === 'warning' ? '警告' : '信息'
                        } 
                        color={
                          selectedAnomaly.severity === 'critical' ? 'error' :
                          selectedAnomaly.severity === 'warning' ? 'warning' : 'info'
                        }
                      />
                    </Grid>
                    <Grid item xs={6}>
                      <Typography variant="subtitle2">状态</Typography>
                      {getStatusChip(selectedAnomaly.status)}
                    </Grid>
                  </Grid>
                  
                  <Box sx={{ mt: 2 }}>
                    <Typography variant="subtitle2">处理建议</Typography>
                    <Typography variant="body2" paragraph>
                      {selectedAnomaly.severity === 'critical' 
                        ? '请立即联系患者并咨询医生，可能需要紧急干预。' 
                        : selectedAnomaly.severity === 'warning'
                          ? '请在24小时内联系患者，并考虑调整治疗方案。'
                          : '请在下次随访时关注此指标变化趋势。'
                      }
                    </Typography>
                  </Box>
                </DialogContent>
                <DialogActions>
                  {selectedAnomaly.status === 'new' && (
                    <Button 
                      onClick={() => handleAcknowledge(selectedAnomaly.id)}
                      color="primary"
                    >
                      确认异常
                    </Button>
                  )}
                  {(selectedAnomaly.status === 'new' || selectedAnomaly.status === 'acknowledged') && (
                    <Button 
                      onClick={() => handleResolve(selectedAnomaly.id)}
                      color="success"
                    >
                      标记为已解决
                    </Button>
                  )}
                  <Button 
                    onClick={() => setDetailsDialogOpen(false)}
                    color="inherit"
                  >
                    关闭
                  </Button>
                </DialogActions>
              </>
            )}
          </Dialog>

          {/* 筛选设置对话框 */}
          <Dialog
            open={filtersDialogOpen}
            onClose={() => setFiltersDialogOpen(false)}
            maxWidth="xs"
            fullWidth
          >
            <DialogTitle>筛选设置</DialogTitle>
            <DialogContent>
              <Typography variant="subtitle2" gutterBottom>
                显示状态
              </Typography>
              <Box sx={{ mb: 2 }}>
                <Chip
                  label="新异常"
                  color="error"
                  sx={{ mr: 1, mb: 1 }}
                  variant="filled"
                  onClick={() => {}} // 新异常始终显示
                />
                <Chip
                  label="已确认"
                  color={filters.showAcknowledged ? "warning" : "default"}
                  sx={{ mr: 1, mb: 1 }}
                  variant={filters.showAcknowledged ? "filled" : "outlined"}
                  onClick={() => setFilters({...filters, showAcknowledged: !filters.showAcknowledged})}
                />
                <Chip
                  label="已解决"
                  color={filters.showResolved ? "success" : "default"}
                  sx={{ mr: 1, mb: 1 }}
                  variant={filters.showResolved ? "filled" : "outlined"}
                  onClick={() => setFilters({...filters, showResolved: !filters.showResolved})}
                />
              </Box>
              
              <Typography variant="subtitle2" gutterBottom>
                严重程度
              </Typography>
              <Box sx={{ mb: 2 }}>
                <Chip
                  label="严重"
                  color={filters.severityFilters.includes('critical') ? "error" : "default"}
                  sx={{ mr: 1, mb: 1 }}
                  variant={filters.severityFilters.includes('critical') ? "filled" : "outlined"}
                  onClick={() => {
                    const newFilters = filters.severityFilters.includes('critical')
                      ? filters.severityFilters.filter(s => s !== 'critical')
                      : [...filters.severityFilters, 'critical'];
                    setFilters({...filters, severityFilters: newFilters});
                  }}
                />
                <Chip
                  label="警告"
                  color={filters.severityFilters.includes('warning') ? "warning" : "default"}
                  sx={{ mr: 1, mb: 1 }}
                  variant={filters.severityFilters.includes('warning') ? "filled" : "outlined"}
                  onClick={() => {
                    const newFilters = filters.severityFilters.includes('warning')
                      ? filters.severityFilters.filter(s => s !== 'warning')
                      : [...filters.severityFilters, 'warning'];
                    setFilters({...filters, severityFilters: newFilters});
                  }}
                />
                <Chip
                  label="信息"
                  color={filters.severityFilters.includes('info') ? "info" : "default"}
                  sx={{ mr: 1, mb: 1 }}
                  variant={filters.severityFilters.includes('info') ? "filled" : "outlined"}
                  onClick={() => {
                    const newFilters = filters.severityFilters.includes('info')
                      ? filters.severityFilters.filter(s => s !== 'info')
                      : [...filters.severityFilters, 'info'];
                    setFilters({...filters, severityFilters: newFilters});
                  }}
                />
              </Box>
            </DialogContent>
            <DialogActions>
              <Button 
                onClick={() => setFiltersDialogOpen(false)}
                color="primary"
              >
                确认
              </Button>
            </DialogActions>
          </Dialog>
        </>
      )}
    </Box>
  );
};

export default DeviceAnomalyAlert; 
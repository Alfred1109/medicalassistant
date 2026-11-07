import React, { useState, useEffect, FC } from 'react';
import {
  Box,
  Typography,
  Divider,
  Paper,
  Button,
  Snackbar,
  Alert,
  Stack,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
} from '@mui/material';
import Badge from '@mui/material/Badge';
import RefreshIcon from '@mui/icons-material/Refresh';
import WarningIcon from '@mui/icons-material/Warning';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';

// 导入组件
import HealthDataTimeline from '../../components/HealthManager/HealthDataTimeline';
import { apiService } from '../../services/api';
import api from '../../services/api';

// 健康数据时间线项目类型
interface HealthDataTimelineItem {
  id: string;
  data_type: string;
  title: string;
  description: string;
  value: string | number;
  unit: string;
  timestamp: string;
  metadata?: {
    device?: string;
    location?: string;
    notes?: string;
    tags?: string[];
    alert_status?: string;
    alert_level?: string;
    [key: string]: any;
  };
}

// 健康数据类型（对应后端 HealthDataResponse：data_content 承载具体数值）
interface HealthData {
  id: string;
  patient_id: string;
  data_type: string;
  data_content: {
    value?: string | number | { systolic?: number; diastolic?: number; [key: string]: any };
    unit?: string;
    notes?: string;
    type?: string;
    [key: string]: any;
  };
  source?: string;
  recorded_by?: string;
  recorded_at: string;
  created_at: string;
  updated_at: string;
  metadata?: { [key: string]: any };
  alert_level?: string;
  alert_status?: string;
  alert_message?: string;
  [key: string]: any;
}

// 预警数据类型（对应后端 AlertResponse，GET /health/alerts/alerts）
interface AlertData {
  id: string;
  health_data_id: string;
  patient_id: string;
  data_type: string;
  vital_type?: string;
  value: number | { [key: string]: any };
  unit?: string;
  alert_level: string;
  status: string;
  recorded_at?: string;
  resolved_at?: string;
  resolved_by?: string;
  resolution_notes?: string;
}

// 数据类型映射
const dataTypeLabelMap: Record<string, string> = {
  blood_pressure: '血压测量',
  blood_glucose: '血糖检测',
  heart_rate: '心率监测',
  body_temperature: '体温记录',
  weight: '体重记录',
  height: '身高测量',
  sleep: '睡眠记录',
  step_count: '步数统计',
  blood_oxygen: '血氧监测',
  oxygen_saturation: '血氧监测',
  respiratory_rate: '呼吸频率'
};

// 数据类型默认单位
const getUnitByDataType = (dataType: string): string => {
  const unitMap: Record<string, string> = {
    blood_pressure: 'mmHg',
    blood_glucose: 'mmol/L',
    heart_rate: 'bpm',
    body_temperature: '°C',
    weight: 'kg',
    height: 'cm',
    oxygen_saturation: '%',
    blood_oxygen: '%',
    respiratory_rate: '次/分',
    step_count: '步',
  };
  return unitMap[dataType] || '';
};

// 获取显示值（血压支持 {systolic, diastolic} 结构）
const getDisplayValue = (data: HealthData): string | number => {
  const value = data.data_content?.value;
  if (value && typeof value === 'object') {
    const bp = value as { systolic?: number; diastolic?: number };
    if (bp.systolic != null && bp.diastolic != null) {
      return `${bp.systolic}/${bp.diastolic}`;
    }
    return JSON.stringify(value);
  }
  return value != null ? (value as string | number) : '-';
};

// 转换健康数据到时间线项目
const convertHealthDataToTimelineItems = (healthData: HealthData[]): HealthDataTimelineItem[] => {
  return healthData.map(item => {
    const semanticType = item.data_content?.type || item.data_type;
    const baseTitle = dataTypeLabelMap[semanticType] || dataTypeLabelMap[item.data_type] || `${item.data_type}记录`;

    // 如果有预警信息，添加预警标记
    let title = baseTitle;
    if (item.alert_level === 'warning') {
      title = `⚠️ ${title} (警告)`;
    } else if (item.alert_level === 'critical') {
      title = `🚨 ${title} (严重)`;
    }

    // 描述：预警信息 + 备注
    let description = '';
    if (item.alert_level) {
      const alertMsg = item.alert_level === 'warning' ? '警告: 数值超出正常范围' : '严重: 数值大幅偏离正常范围';
      description += alertMsg;
      if (item.alert_message) {
        description += ` - ${item.alert_message}`;
      }
      description += '\n';
    }
    if (item.data_content?.notes) {
      description += item.data_content.notes;
    }

    return {
      id: item.id,
      data_type: item.data_type,
      title,
      description,
      value: getDisplayValue(item),
      unit: item.data_content?.unit || getUnitByDataType(semanticType),
      timestamp: item.recorded_at || '',
      metadata: {
        notes: item.data_content?.notes,
        source: item.source,
        alert_status: item.alert_status,
        alert_level: item.alert_level
      }
    };
  });
};

// 健康数据时间线页面组件
const HealthDataTimelinePage: React.FC = () => {
  // 状态
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [healthData, setHealthData] = useState<HealthData[]>([]);
  const [alerts, setAlerts] = useState<AlertData[]>([]);
  const [showAlertsOnly, setShowAlertsOnly] = useState<boolean>(false);
  const [detailItem, setDetailItem] = useState<HealthData | null>(null);
  const [snackbar, setSnackbar] = useState({
    open: false,
    message: '',
    severity: 'info' as 'info' | 'warning' | 'error'
  });

  // 患者ID：路由参数优先，其次查询串 ?patientId=，均缺失时给出诚实提示
  const { patientId: routePatientId } = useParams<{ patientId?: string }>();
  const [searchParams] = useSearchParams();
  const patientId = routePatientId || searchParams.get('patientId') || '';
  const navigate = useNavigate();

  // 加载健康数据与预警数据（均为真实接口）
  const loadHealthData = async () => {
    if (!patientId) return;
    try {
      setLoading(true);

      // 获取健康数据：GET /health-records/health-data?patient_id=...
      const response = await apiService.getHealthData(patientId);
      const fetchedData: HealthData[] = response.data;

      // 获取预警数据：GET /health/alerts/alerts?patient_id=...
      // 即使预警接口失败，仍然显示基本健康数据
      let fetchedAlerts: AlertData[] = [];
      try {
        const alertsResponse = await api.get('/health/alerts/alerts', {
          params: { patient_id: patientId }
        });
        fetchedAlerts = Array.isArray(alertsResponse.data) ? alertsResponse.data : [];
      } catch (alertErr) {
        console.error('获取健康预警数据失败:', alertErr);
      }

      setAlerts(fetchedAlerts);

      // 将预警信息按 health_data_id 关联到健康数据
      // （AlertResponse 无 message 字段，预警详情以级别/状态为准，
      // 已处理的预警以 resolution_notes 作为说明）
      const dataWithAlerts = fetchedData.map(item => {
        const relatedAlert = fetchedAlerts.find(alert => alert.health_data_id === item.id);
        if (relatedAlert) {
          return {
            ...item,
            alert_level: relatedAlert.alert_level,
            alert_status: relatedAlert.status,
            alert_message: relatedAlert.status !== 'active' && relatedAlert.resolution_notes
              ? relatedAlert.resolution_notes
              : undefined
          };
        }
        return item;
      });

      setHealthData(dataWithAlerts);
      setError(null);
    } catch (err: any) {
      console.error('加载健康数据失败:', err);
      setError(err.response?.data?.detail || '加载健康数据失败，请稍后重试');
    } finally {
      setLoading(false);
    }
  };

  // 初始化加载数据
  useEffect(() => {
    loadHealthData();
  }, [patientId]);

  // 全量时间线项目
  const allTimelineItems = convertHealthDataToTimelineItems(healthData);

  // "仅显示异常数据" 时前端过滤出带预警的项目
  const timelineData = showAlertsOnly
    ? allTimelineItems.filter(item =>
        item.metadata && (item.metadata.alert_level === 'warning' || item.metadata.alert_level === 'critical')
      )
    : allTimelineItems;

  // 处理时间线项目点击事件：打开该项目真实数据的详情对话框
  const handleTimelineItemClick = (item: HealthDataTimelineItem) => {
    const originalData = healthData.find(data => data.id === item.id);
    if (originalData) {
      setDetailItem(originalData);
    }
  };

  // 处理数据导出：后端暂未提供导出接口，不伪造导出成功
  const handleExport = () => {
    setSnackbar({
      open: true,
      message: '导出功能后端暂未提供',
      severity: 'info'
    });
  };

  // 处理数据分享：后端暂未提供分享接口，不伪造分享链接
  const handleShare = () => {
    setSnackbar({
      open: true,
      message: '分享功能后端暂未提供',
      severity: 'info'
    });
  };

  // 切换仅显示预警数据
  const toggleAlertsOnly = () => {
    setShowAlertsOnly(!showAlertsOnly);
  };

  // 关闭提示消息
  const handleCloseSnackbar = () => {
    setSnackbar({ ...snackbar, open: false });
  };

  // 未指定患者时的诚实提示（后端接口要求必填 patient_id，且无患者列表接口可默认）
  if (!patientId) {
    return (
      <Box>
        <Typography variant="h5" gutterBottom>
          健康数据时间线
        </Typography>
        <Divider sx={{ mb: 3 }} />
        <Alert severity="info">
          请先指定患者（通过患者列表进入，或在地址后附加 ?patientId=患者ID）后查看健康数据时间线。本页面不预设默认患者。
        </Alert>
      </Box>
    );
  }

  return (
    <Box>
      <Typography variant="h5" gutterBottom>
        健康数据时间线
        {alerts.length > 0 && (
          <Badge
            badgeContent={alerts.length}
            color="error"
            sx={{ ml: 2 }}
          >
            <WarningIcon color="error" />
          </Badge>
        )}
      </Typography>
      <Typography variant="body2" color="text.secondary" paragraph>
        查看患者（ID: {patientId}）健康数据的时间线视图，了解健康指标的变化趋势和关键时间点。实时监测异常数据并提供预警通知。
      </Typography>
      <Divider sx={{ mb: 3 }} />

      {/* 操作按钮 */}
      <Box sx={{ mb: 3, display: 'flex', justifyContent: 'space-between' }}>
        <Stack direction="row" spacing={2}>
          <Button
            variant="outlined"
            startIcon={<RefreshIcon />}
            onClick={loadHealthData}
            disabled={loading}
          >
            刷新数据
          </Button>
          <Button
            variant={showAlertsOnly ? "contained" : "outlined"}
            color="error"
            startIcon={<WarningIcon />}
            onClick={toggleAlertsOnly}
            disabled={loading || alerts.length === 0}
          >
            {showAlertsOnly ? "显示全部数据" : "仅显示异常数据"}
          </Button>
        </Stack>
        <Stack direction="row" spacing={2}>
          <Button
            color="primary"
            onClick={() => navigate(`/app/health-manager/health-records/${patientId}`)}
          >
            查看健康档案
          </Button>
        </Stack>
      </Box>

      {error && (
        <Alert severity="error" sx={{ mb: 3 }}>{error}</Alert>
      )}

      {/* 预警提示 */}
      {alerts.length > 0 && !showAlertsOnly && (
        <Alert
          severity="warning"
          sx={{ mb: 3 }}
          action={
            <Button color="inherit" size="small" onClick={toggleAlertsOnly}>
              查看详情
            </Button>
          }
        >
          发现 {alerts.length} 条健康数据异常，请及时查看并处理
        </Alert>
      )}

      {/* 时间线组件（导出/分享为诚实提示，后端暂无对应能力） */}
      <HealthDataTimeline
        data={timelineData}
        loading={loading}
        error={error || undefined}
        title={showAlertsOnly ? "健康数据异常时间线" : "健康数据时间线"}
        maxHeight={600}
        onItemClick={handleTimelineItemClick}
        onExport={handleExport}
        onShare={handleShare}
      />

      {/* 时间线项目详情对话框（展示抓取到的真实字段） */}
      <Dialog open={!!detailItem} onClose={() => setDetailItem(null)} maxWidth="sm" fullWidth>
        <DialogTitle>
          {detailItem
            ? dataTypeLabelMap[detailItem.data_content?.type || detailItem.data_type] ||
              `${detailItem.data_type}记录`
            : '数据详情'}
        </DialogTitle>
        <DialogContent>
          {detailItem && (
            <Paper variant="outlined" sx={{ p: 2 }}>
              <Typography variant="body1" sx={{ mb: 1 }}>
                <strong>数值：</strong>
                {getDisplayValue(detailItem)}
                {detailItem.data_content?.unit ? ` ${detailItem.data_content.unit}` : ''}
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                <strong>数据类型：</strong>{detailItem.data_type}
                {detailItem.data_content?.type ? `（${detailItem.data_content.type}）` : ''}
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                <strong>测量时间：</strong>
                {detailItem.recorded_at ? new Date(detailItem.recorded_at).toLocaleString('zh-CN') : '-'}
              </Typography>
              {detailItem.source && (
                <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                  <strong>来源：</strong>{detailItem.source}
                </Typography>
              )}
              {detailItem.recorded_by && (
                <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                  <strong>记录人ID：</strong>{detailItem.recorded_by}
                </Typography>
              )}
              {detailItem.alert_level && (
                <Typography variant="body2" color="error" sx={{ mb: 1 }}>
                  <strong>预警级别：</strong>{detailItem.alert_level}
                  {detailItem.alert_message ? `（${detailItem.alert_message}）` : ''}
                </Typography>
              )}
              {detailItem.data_content?.notes && (
                <Typography variant="body2" sx={{ mb: 1 }}>
                  <strong>备注：</strong>{detailItem.data_content.notes}
                </Typography>
              )}
            </Paper>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDetailItem(null)}>关闭</Button>
        </DialogActions>
      </Dialog>

      {/* 提示消息（仅用于"功能后端暂未提供"等诚实提示） */}
      <Snackbar
        open={snackbar.open}
        autoHideDuration={5000}
        onClose={handleCloseSnackbar}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        <Alert
          onClose={handleCloseSnackbar}
          severity={snackbar.severity}
          variant="filled"
        >
          {snackbar.message}
        </Alert>
      </Snackbar>
    </Box>
  );
};

export default HealthDataTimelinePage;

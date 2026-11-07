import React, { useState, useEffect, useRef } from 'react';
import {
  Box,
  Card,
  CardContent,
  Typography,
  Grid,
  Paper,
  Chip,
  LinearProgress,
  Divider,
  ToggleButton,
  ToggleButtonGroup,
  Button,
  Alert,
  List,
  ListItem,
  ListItemText,
} from '@mui/material';

import { deviceService, DeviceDataItem } from '../../services/deviceService';

// 组件属性接口
interface DeviceDataDisplayProps {
  deviceId?: string;
  showChart?: boolean;
  height?: number | string;
  timeRange?: 'day' | 'week' | 'month';
  onError?: (error: string) => void;
}

// 时间范围对应的毫秒数
const TIME_RANGE_MS: Record<string, number> = {
  day: 24 * 3600 * 1000,
  week: 7 * 24 * 3600 * 1000,
  month: 30 * 24 * 3600 * 1000,
};

// 将数据值渲染为字符串（后端 value 为任意类型）
const formatValue = (value: any): string => {
  if (value === null || value === undefined) return '-';
  if (typeof value === 'number') return Number.isInteger(value) ? String(value) : value.toFixed(1);
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
};

// 数据类型的中文名称（未匹配时原样展示）
const DATA_TYPE_LABELS: Record<string, string> = {
  heart_rate: '心率',
  heartRate: '心率',
  blood_pressure: '血压',
  bloodPressure: '血压',
  steps: '步数',
  sleep: '睡眠',
  temperature: '体温',
  blood_oxygen: '血氧',
  spo2: '血氧',
  weight: '体重',
};

const getDataTypeLabel = (type: string): string => DATA_TYPE_LABELS[type] || type;

const DeviceDataDisplay: React.FC<DeviceDataDisplayProps> = ({
  deviceId,
  showChart = true,
  height = 'auto',
  timeRange = 'day',
  onError
}) => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [items, setItems] = useState<DeviceDataItem[]>([]);
  const [selectedType, setSelectedType] = useState<string | null>(null);
  const [timeRangeValue, setTimeRangeValue] = useState<string>(timeRange);
  const [reloadTick, setReloadTick] = useState(0);

  // onError 通过 ref 引用，避免父组件内联回调导致重复请求
  const onErrorRef = useRef(onError);
  onErrorRef.current = onError;

  // 真实数据加载：GET /api/devices/{id}/data
  useEffect(() => {
    if (!deviceId) {
      setItems([]);
      setError(null);
      setLoading(false);
      return;
    }

    let cancelled = false;
    const loadData = async () => {
      setLoading(true);
      setError(null);

      try {
        const startDate = new Date(Date.now() - (TIME_RANGE_MS[timeRangeValue] || TIME_RANGE_MS.day));
        const data = await deviceService.getDeviceData(deviceId, {
          startDate: startDate.toISOString(),
          limit: 200,
        });
        if (cancelled) return;
        setItems(data);
        // 默认选中第一个出现的数据类型
        setSelectedType(prev => (prev && data.some(d => d.data_type === prev) ? prev : (data[0]?.data_type ?? null)));
        setLoading(false);
      } catch (err: any) {
        if (cancelled) return;
        const message =
          err?.response?.data?.detail || err?.message || '获取设备数据失败，请稍后再试';
        console.error('Error loading device data:', err);
        setError(message);
        setLoading(false);
        if (onErrorRef.current) onErrorRef.current(message);
      }
    };

    loadData();
    return () => { cancelled = true; };
  }, [deviceId, timeRangeValue, reloadTick]);

  // 处理数据类型切换
  const handleTypeChange = (
    event: React.MouseEvent<HTMLElement>,
    newType: string | null,
  ) => {
    if (newType !== null) {
      setSelectedType(newType);
    }
  };

  // 处理时间范围切换
  const handleTimeRangeChange = (
    event: React.MouseEvent<HTMLElement>,
    newTimeRange: string | null,
  ) => {
    if (newTimeRange !== null) {
      setTimeRangeValue(newTimeRange);
    }
  };

  // 按数据类型分组（保持后端返回顺序）
  const groupByType = (): { [type: string]: DeviceDataItem[] } => {
    const grouped: { [type: string]: DeviceDataItem[] } = {};
    for (const item of items) {
      if (!grouped[item.data_type]) grouped[item.data_type] = [];
      grouped[item.data_type].push(item);
    }
    return grouped;
  };

  const grouped = groupByType();
  const types = Object.keys(grouped);

  // 渲染指定类型的最新值卡片
  const renderTypeCard = (type: string) => {
    const list = grouped[type];
    const latest = list[0]; // 后端按时间倒序返回
    return (
      <Grid item xs={6} sm={3} key={type}>
        <Card
          variant={selectedType === type ? 'elevation' : 'outlined'}
          sx={{
            boxShadow: selectedType === type ? 3 : 0,
            borderColor: selectedType === type ? 'primary.main' : 'divider',
            cursor: 'pointer',
          }}
          onClick={() => setSelectedType(type)}
        >
          <CardContent sx={{ p: 2, '&:last-child': { pb: 2 } }}>
            <Typography variant="subtitle2" color="text.secondary" gutterBottom>
              {getDataTypeLabel(type)}
            </Typography>
            <Typography variant="h4" component="div">
              {latest ? formatValue(latest.value) : '-'}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              {latest ? `${latest.unit || ''} · ${new Date(latest.timestamp).toLocaleString()}` : '-'}
            </Typography>
          </CardContent>
        </Card>
      </Grid>
    );
  };

  // 渲染所选类型的真实数据趋势（横条示意，数据全部来自接口返回值）
  const renderChart = () => {
    if (!selectedType) return null;
    const list = grouped[selectedType] || [];
    const numeric = list
      .map(item => ({ item, num: Number(item.value) }))
      .filter(entry => Number.isFinite(entry.num));
    if (numeric.length === 0) return null;

    const values = numeric.map(entry => entry.num);
    const min = Math.min(...values);
    const max = Math.max(...values);
    const span = max - min || 1;

    return (
      <Box sx={{ mt: 2 }}>
        {numeric.slice(0, 12).map(({ item, num }) => (
          <Box key={item.id} sx={{ display: 'flex', alignItems: 'center', mb: 0.5 }}>
            <Typography variant="caption" color="text.secondary" sx={{ width: 140, flexShrink: 0 }}>
              {new Date(item.timestamp).toLocaleString()}
            </Typography>
            <Box sx={{ flex: 1, bgcolor: 'grey.100', borderRadius: 1, height: 16, mr: 1 }}>
              <Box
                sx={{
                  width: `${30 + ((num - min) / span) * 70}%`,
                  bgcolor: 'primary.main',
                  height: '100%',
                  borderRadius: 1,
                }}
              />
            </Box>
            <Typography variant="caption" sx={{ width: 70, textAlign: 'right' }}>
              {formatValue(item.value)} {item.unit || ''}
            </Typography>
          </Box>
        ))}
      </Box>
    );
  };

  // 渲染原始数据明细列表
  const renderDataList = () => {
    if (!selectedType) return null;
    const list = (grouped[selectedType] || []).slice(0, 20);
    return (
      <List dense>
        {list.map(item => (
          <ListItem key={item.id} divider>
            <ListItemText
              primary={`${formatValue(item.value)} ${item.unit || ''}`}
              secondary={new Date(item.timestamp).toLocaleString()}
            />
          </ListItem>
        ))}
      </List>
    );
  };

  // 未指定设备：诚实提示，不伪造数据
  if (!deviceId) {
    return (
      <Box sx={{ width: '100%', height }}>
        <Alert severity="info">未指定设备，无法加载设备数据。</Alert>
      </Box>
    );
  }

  if (loading) {
    return (
      <Box sx={{ width: '100%', height }}>
        <Typography variant="subtitle1" gutterBottom>加载设备数据中...</Typography>
        <LinearProgress />
      </Box>
    );
  }

  if (error) {
    return (
      <Box sx={{ width: '100%', height }}>
        <Alert
          severity="error"
          action={
            <Button color="inherit" size="small" onClick={() => setReloadTick(t => t + 1)}>
              重试
            </Button>
          }
        >
          {error}
        </Alert>
      </Box>
    );
  }

  // 真实空状态：设备存在但接口未返回任何数据
  if (items.length === 0) {
    return (
      <Box sx={{ width: '100%', height }}>
        <Alert severity="info">该设备暂无数据。设备上报或完成同步后，这里会展示真实测量记录。</Alert>
      </Box>
    );
  }

  return (
    <Box sx={{ width: '100%', height }}>
      <Grid container spacing={3}>
        <Grid item xs={12}>
          <Grid container spacing={2}>
            {types.map(type => renderTypeCard(type))}
          </Grid>
        </Grid>

        <Grid item xs={12}>
          <Paper sx={{ p: 2 }}>
            <Box display="flex" justifyContent="space-between" alignItems="center" mb={2} flexWrap="wrap" gap={1}>
              <Typography variant="h6">
                {getDataTypeLabel(selectedType || '')}数据记录
              </Typography>
              <ToggleButtonGroup
                value={timeRangeValue}
                exclusive
                onChange={handleTimeRangeChange}
                aria-label="时间范围选择"
                size="small"
              >
                <ToggleButton value="day" aria-label="今日">今日</ToggleButton>
                <ToggleButton value="week" aria-label="本周">本周</ToggleButton>
                <ToggleButton value="month" aria-label="本月">本月</ToggleButton>
              </ToggleButtonGroup>
            </Box>

            <Divider sx={{ mb: 2 }} />

            <Box sx={{ mb: 2, display: 'flex', justifyContent: 'center', flexWrap: 'wrap', gap: 1 }}>
              <ToggleButtonGroup
                value={selectedType}
                exclusive
                onChange={handleTypeChange}
                aria-label="数据类型选择"
                size="small"
              >
                {types.map(type => (
                  <ToggleButton key={type} value={type} aria-label={getDataTypeLabel(type)}>
                    <Chip label={getDataTypeLabel(type)} size="small" variant="outlined" />
                  </ToggleButton>
                ))}
              </ToggleButtonGroup>
            </Box>

            {showChart && renderChart()}

            <Box sx={{ mt: 2, display: 'flex', justifyContent: 'space-between' }}>
              <Typography variant="caption" color="text.secondary">
                {timeRangeValue === 'day' ? '过去24小时' :
                 timeRangeValue === 'week' ? '过去7天' : '过去30天'}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                共 {items.length} 条记录
              </Typography>
            </Box>

            <Divider sx={{ my: 2 }} />

            {renderDataList()}
          </Paper>
        </Grid>
      </Grid>
    </Box>
  );
};

export default DeviceDataDisplay;

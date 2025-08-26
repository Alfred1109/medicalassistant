import React, { useState, useEffect } from 'react';
import {
  Box,
  Typography,
  Paper,
  Divider,
  Chip,
  CircularProgress,
  Alert,
  Grid,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  TextField,
  Button,
  IconButton,
  Tooltip,
  Stack,
  Menu,
  ListItemIcon,
  ListItemText
} from '@mui/material';
import FilterListIcon from '@mui/icons-material/FilterList';
import FileDownloadIcon from '@mui/icons-material/FileDownload';
import ShareIcon from '@mui/icons-material/Share';
import LocalPrintshopIcon from '@mui/icons-material/LocalPrintshop';
import GroupWorkIcon from '@mui/icons-material/GroupWork';
import TodayIcon from '@mui/icons-material/Today';
import CalendarViewMonthIcon from '@mui/icons-material/CalendarViewMonth';
import CalendarViewWeekIcon from '@mui/icons-material/CalendarViewWeek';
import Timeline from '@mui/lab/Timeline';
import TimelineItem from '@mui/lab/TimelineItem';
import TimelineSeparator from '@mui/lab/TimelineSeparator';
import TimelineConnector from '@mui/lab/TimelineConnector';
import TimelineContent from '@mui/lab/TimelineContent';
import TimelineDot from '@mui/lab/TimelineDot';
import TimelineOppositeContent from '@mui/lab/TimelineOppositeContent';
import { format, parseISO, subDays, startOfDay, endOfDay, startOfMonth, endOfMonth, startOfWeek, endOfWeek } from 'date-fns';
import { zhCN } from 'date-fns/locale';

// 图标导入
import FavoriteIcon from '@mui/icons-material/Favorite';
import MonitorHeartIcon from '@mui/icons-material/MonitorHeart';
import OpacityIcon from '@mui/icons-material/Opacity';
import ThermostatIcon from '@mui/icons-material/Thermostat';
import ScaleIcon from '@mui/icons-material/Scale';
import HeightIcon from '@mui/icons-material/Height';
import RestaurantIcon from '@mui/icons-material/Restaurant';
import BedtimeIcon from '@mui/icons-material/Bedtime';
import DirectionsRunIcon from '@mui/icons-material/DirectionsRun';
import BloodtypeIcon from '@mui/icons-material/Bloodtype';
import DeviceThermostatIcon from '@mui/icons-material/DeviceThermostat';
import AirIcon from '@mui/icons-material/Air';
import MoreVertIcon from '@mui/icons-material/MoreVert';

// 健康数据类型图标映射
const dataTypeIcons: { [key: string]: React.ReactNode } = {
  blood_pressure: <OpacityIcon />,
  heart_rate: <FavoriteIcon />,
  body_temperature: <ThermostatIcon />,
  weight: <ScaleIcon />,
  height: <HeightIcon />,
  blood_glucose: <BloodtypeIcon />,
  oxygen_saturation: <AirIcon />,
  respiratory_rate: <DeviceThermostatIcon />,
  step_count: <DirectionsRunIcon />,
  sleep: <BedtimeIcon />,
  diet: <RestaurantIcon />,
  default: <MonitorHeartIcon />
};

// 健康数据类型颜色映射
const dataTypeColors: { [key: string]: 'primary' | 'secondary' | 'success' | 'warning' | 'info' | 'error' | 'default' } = {
  blood_pressure: 'primary',
  heart_rate: 'secondary',
  body_temperature: 'warning',
  weight: 'info',
  height: 'info',
  blood_glucose: 'error',
  oxygen_saturation: 'success',
  respiratory_rate: 'primary',
  step_count: 'secondary',
  sleep: 'info',
  diet: 'success',
  default: 'default'
};

// 健康数据类型中文映射
const dataTypeLabels: { [key: string]: string } = {
  blood_pressure: '血压',
  heart_rate: '心率',
  body_temperature: '体温',
  weight: '体重',
  height: '身高',
  blood_glucose: '血糖',
  oxygen_saturation: '血氧',
  respiratory_rate: '呼吸频率',
  step_count: '步数',
  sleep: '睡眠',
  diet: '饮食',
  default: '其他'
};

// 时间范围选项
const timeRangeOptions = [
  { value: 'all', label: '全部' },
  { value: 'today', label: '今天' },
  { value: 'week', label: '本周' },
  { value: 'month', label: '本月' },
  { value: 'last7', label: '最近7天' },
  { value: 'last30', label: '最近30天' },
  { value: 'last90', label: '最近90天' }
];

// 分组选项
const groupByOptions = [
  { value: 'none', label: '不分组' },
  { value: 'type', label: '按类型分组' },
  { value: 'day', label: '按天分组' },
  { value: 'week', label: '按周分组' },
  { value: 'month', label: '按月分组' }
];

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
    [key: string]: any;
  };
  icon?: string;
  color?: string;
}

// 组件属性
interface HealthDataTimelineProps {
  data: HealthDataTimelineItem[];
  loading?: boolean;
  error?: string;
  title?: string;
  maxHeight?: number | string;
  onItemClick?: (item: HealthDataTimelineItem) => void;
  onExport?: (data: HealthDataTimelineItem[], format: 'csv' | 'pdf' | 'excel') => void;
  onShare?: (data: HealthDataTimelineItem[]) => void;
  onDataFilterChange?: (filteredData: HealthDataTimelineItem[]) => void;
}

const HealthDataTimeline: React.FC<HealthDataTimelineProps> = ({
  data,
  loading = false,
  error,
  title = '健康数据时间线',
  maxHeight = 600,
  onItemClick,
  onExport,
  onShare,
  onDataFilterChange
}) => {
  // 状态
  const [timelineData, setTimelineData] = useState<HealthDataTimelineItem[]>([]);
  const [timeRange, setTimeRange] = useState<string>('last30');
  const [selectedTypes, setSelectedTypes] = useState<string[]>([]);
  const [groupBy, setGroupBy] = useState<string>('none');
  const [searchTerm, setSearchTerm] = useState<string>('');
  const [anchorEl, setAnchorEl] = useState<null | HTMLElement>(null);
  const [availableTypes, setAvailableTypes] = useState<string[]>([]);
  
  // 菜单开关状态
  const open = Boolean(anchorEl);
  
  // 打开菜单
  const handleMenuClick = (event: React.MouseEvent<HTMLButtonElement>) => {
    setAnchorEl(event.currentTarget);
  };
  
  // 关闭菜单
  const handleMenuClose = () => {
    setAnchorEl(null);
  };
  
  // 根据数据类型获取图标
  const getIconForDataType = (type: string) => {
    return dataTypeIcons[type] || dataTypeIcons.default;
  };
  
  // 根据数据类型获取颜色
  const getColorForDataType = (type: string) => {
    return dataTypeColors[type] || dataTypeColors.default;
  };
  
  // 格式化日期
  const formatDate = (dateString: string, formatStr: string = 'yyyy年MM月dd日 HH:mm') => {
    try {
      const date = parseISO(dateString);
      return format(date, formatStr, { locale: zhCN });
    } catch (error) {
      return dateString;
    }
  };
  
  // 格式化日期分组标题
  const formatGroupTitle = (date: Date, groupType: string) => {
    switch (groupType) {
      case 'day':
        return format(date, 'yyyy年MM月dd日', { locale: zhCN });
      case 'week':
        return `${format(startOfWeek(date, { locale: zhCN }), 'yyyy年MM月dd日')} - ${format(endOfWeek(date, { locale: zhCN }), 'MM月dd日')}`;
      case 'month':
        return format(date, 'yyyy年MM月', { locale: zhCN });
      default:
        return format(date, 'yyyy年MM月dd日', { locale: zhCN });
    }
  };
  
  // 过滤和处理数据
  const processData = () => {
    if (!data || data.length === 0) {
      setTimelineData([]);
      return;
    }
    
    // 提取所有可用的数据类型
    const types = [...new Set(data.map(item => item.data_type))];
    setAvailableTypes(types);
    
    // 如果没有选择任何类型，默认选择所有类型
    if (selectedTypes.length === 0 && types.length > 0) {
      setSelectedTypes(types);
    }
    
    // 过滤数据
    let filteredData = [...data];
    
    // 按时间范围过滤
    const now = new Date();
    if (timeRange !== 'all') {
      const filterDate = getDateRangeStart(timeRange, now);
      filteredData = filteredData.filter(item => {
        const itemDate = parseISO(item.timestamp);
        return itemDate >= filterDate;
      });
    }
    
    // 按类型过滤
    if (selectedTypes.length > 0) {
      filteredData = filteredData.filter(item => selectedTypes.includes(item.data_type));
    }
    
    // 按搜索词过滤
    if (searchTerm) {
      const lowerSearchTerm = searchTerm.toLowerCase();
      filteredData = filteredData.filter(item => 
        item.title.toLowerCase().includes(lowerSearchTerm) ||
        item.description.toLowerCase().includes(lowerSearchTerm) ||
        (item.metadata?.notes && item.metadata.notes.toLowerCase().includes(lowerSearchTerm))
      );
    }
    
    // 按时间排序
    filteredData.sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());
    
    // 更新数据
    setTimelineData(filteredData);
    
    // 回调通知
    if (onDataFilterChange) {
      onDataFilterChange(filteredData);
    }
  };
  
  // 获取时间范围起始日期
  const getDateRangeStart = (range: string, currentDate: Date) => {
    switch (range) {
      case 'today':
        return startOfDay(currentDate);
      case 'week':
        return startOfWeek(currentDate, { locale: zhCN });
      case 'month':
        return startOfMonth(currentDate);
      case 'last7':
        return subDays(currentDate, 7);
      case 'last30':
        return subDays(currentDate, 30);
      case 'last90':
        return subDays(currentDate, 90);
      default:
        return new Date(0); // 1970年1月1日
    }
  };
  
  // 处理时间范围变更
  const handleTimeRangeChange = (event: React.ChangeEvent<{ value: unknown }>) => {
    const value = event.target.value as string;
    setTimeRange(value);
  };
  
  // 处理分组方式变更
  const handleGroupByChange = (event: React.ChangeEvent<{ value: unknown }>) => {
    const value = event.target.value as string;
    setGroupBy(value);
  };
  
  // 处理搜索词变更
  const handleSearchChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    setSearchTerm(event.target.value);
  };
  
  // 处理数据类型选择
  const handleTypeToggle = (type: string) => {
    setSelectedTypes(prev => {
      if (prev.includes(type)) {
        return prev.filter(t => t !== type);
      } else {
        return [...prev, type];
      }
    });
  };
  
  // 处理导出
  const handleExport = (format: 'csv' | 'pdf' | 'excel') => {
    if (onExport) {
      onExport(timelineData, format);
    }
    handleMenuClose();
  };
  
  // 处理分享
  const handleShare = () => {
    if (onShare) {
      onShare(timelineData);
    }
    handleMenuClose();
  };
  
  // 处理打印
  const handlePrint = () => {
    window.print();
    handleMenuClose();
  };
  
  // 当数据、过滤条件或搜索词变更时重新处理数据
  useEffect(() => {
    processData();
  }, [data, timeRange, selectedTypes, searchTerm]);
  
  // 渲染分组标题
  const renderGroupTitle = (groupTitle: string) => (
    <Box sx={{ display: 'flex', alignItems: 'center', mb: 2, mt: 3 }}>
      <Divider sx={{ flex: 1, mr: 2 }} />
      <Chip 
        label={groupTitle} 
        color="primary" 
        icon={<TodayIcon />}
      />
      <Divider sx={{ flex: 1, ml: 2 }} />
    </Box>
  );
  
  // 渲染按类型分组的时间线
  const renderGroupedByType = () => {
    const groupedData: { [key: string]: HealthDataTimelineItem[] } = {};
    
    timelineData.forEach(item => {
      const type = item.data_type;
      if (!groupedData[type]) {
        groupedData[type] = [];
      }
      groupedData[type].push(item);
    });
    
    return Object.entries(groupedData).map(([type, items]) => (
      <Box key={type} sx={{ mb: 4 }}>
        {renderGroupTitle(dataTypeLabels[type] || type)}
        <Timeline position="right">
          {items.map((item, index) => renderTimelineItem(item, index, items.length))}
        </Timeline>
      </Box>
    ));
  };
  
  // 渲染按日期分组的时间线
  const renderGroupedByDate = (groupType: 'day' | 'week' | 'month') => {
    const groupedData: { [key: string]: HealthDataTimelineItem[] } = {};
    
    timelineData.forEach(item => {
      const date = parseISO(item.timestamp);
      let groupKey: string;
      
      switch (groupType) {
        case 'day':
          groupKey = format(date, 'yyyy-MM-dd');
          break;
        case 'week':
          const weekStart = startOfWeek(date, { locale: zhCN });
          groupKey = format(weekStart, 'yyyy-MM-dd');
          break;
        case 'month':
          groupKey = format(date, 'yyyy-MM');
          break;
        default:
          groupKey = format(date, 'yyyy-MM-dd');
      }
      
      if (!groupedData[groupKey]) {
        groupedData[groupKey] = [];
      }
      groupedData[groupKey].push(item);
    });
    
    return Object.entries(groupedData)
      .sort((a, b) => b[0].localeCompare(a[0])) // 按日期降序
      .map(([dateKey, items]) => {
        const date = parseISO(dateKey.length <= 7 ? `${dateKey}-01` : dateKey);
        return (
          <Box key={dateKey} sx={{ mb: 4 }}>
            {renderGroupTitle(formatGroupTitle(date, groupType))}
            <Timeline position="right">
              {items.map((item, index) => renderTimelineItem(item, index, items.length))}
            </Timeline>
          </Box>
        );
      });
  };
  
  // 渲染时间线项目
  const renderTimelineItem = (item: HealthDataTimelineItem, index: number, totalItems: number) => (
    <TimelineItem key={item.id}>
      <TimelineOppositeContent color="text.secondary">
        {formatDate(item.timestamp)}
      </TimelineOppositeContent>
      <TimelineSeparator>
        <TimelineDot color={getColorForDataType(item.data_type)}>
          {getIconForDataType(item.data_type)}
        </TimelineDot>
        {index < totalItems - 1 && <TimelineConnector />}
      </TimelineSeparator>
      <TimelineContent sx={{ py: '12px', px: 2 }}>
        <Box
          sx={{
            p: 2,
            border: '1px solid',
            borderColor: 'divider',
            borderRadius: 1,
            '&:hover': {
              bgcolor: 'action.hover',
              cursor: onItemClick ? 'pointer' : 'default'
            }
          }}
          onClick={() => onItemClick && onItemClick(item)}
        >
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <Typography variant="subtitle1" component="span">
              {item.title}
            </Typography>
            <Chip
              label={dataTypeLabels[item.data_type] || item.data_type}
              color={getColorForDataType(item.data_type)}
              size="small"
            />
          </Box>
          
          <Typography variant="h6" sx={{ mt: 1, fontWeight: 'bold' }}>
            {item.value} {item.unit}
          </Typography>
          
          {item.description && (
            <Typography variant="body2" sx={{ mt: 1 }}>
              {item.description}
            </Typography>
          )}
          
          {item.metadata && (
            <Box sx={{ mt: 1 }}>
              {item.metadata.device && (
                <Chip
                  label={`设备: ${item.metadata.device}`}
                  size="small"
                  variant="outlined"
                  sx={{ mr: 1, mt: 0.5 }}
                />
              )}
              {item.metadata.location && (
                <Chip
                  label={`位置: ${item.metadata.location}`}
                  size="small"
                  variant="outlined"
                  sx={{ mr: 1, mt: 0.5 }}
                />
              )}
              {item.metadata.notes && (
                <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
                  备注: {item.metadata.notes}
                </Typography>
              )}
            </Box>
          )}
        </Box>
      </TimelineContent>
    </TimelineItem>
  );
  
  // 渲染主体内容
  const renderTimelineContent = () => {
    if (timelineData.length === 0) {
      return (
        <Box display="flex" justifyContent="center" alignItems="center" height={200}>
          <Typography color="text.secondary">
            暂无符合条件的健康数据记录
          </Typography>
        </Box>
      );
    }
    
    switch (groupBy) {
      case 'type':
        return renderGroupedByType();
      case 'day':
        return renderGroupedByDate('day');
      case 'week':
        return renderGroupedByDate('week');
      case 'month':
        return renderGroupedByDate('month');
      default:
        return (
          <Timeline position="right">
            {timelineData.map((item, index) => 
              renderTimelineItem(item, index, timelineData.length)
            )}
          </Timeline>
        );
    }
  };
  
  return (
    <Paper elevation={1}>
      <Box p={3}>
        <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
          <Typography variant="h6">{title}</Typography>
          <Box>
            <IconButton onClick={handleMenuClick} aria-label="更多选项">
              <MoreVertIcon />
            </IconButton>
            <Menu
              anchorEl={anchorEl}
              open={open}
              onClose={handleMenuClose}
            >
              <MenuItem onClick={() => handleExport('csv')}>
                <ListItemIcon>
                  <FileDownloadIcon fontSize="small" />
                </ListItemIcon>
                <ListItemText>导出CSV</ListItemText>
              </MenuItem>
              <MenuItem onClick={() => handleExport('excel')}>
                <ListItemIcon>
                  <FileDownloadIcon fontSize="small" />
                </ListItemIcon>
                <ListItemText>导出Excel</ListItemText>
              </MenuItem>
              <MenuItem onClick={() => handleExport('pdf')}>
                <ListItemIcon>
                  <FileDownloadIcon fontSize="small" />
                </ListItemIcon>
                <ListItemText>导出PDF</ListItemText>
              </MenuItem>
              <MenuItem onClick={handleShare}>
                <ListItemIcon>
                  <ShareIcon fontSize="small" />
                </ListItemIcon>
                <ListItemText>分享</ListItemText>
              </MenuItem>
              <MenuItem onClick={handlePrint}>
                <ListItemIcon>
                  <LocalPrintshopIcon fontSize="small" />
                </ListItemIcon>
                <ListItemText>打印</ListItemText>
              </MenuItem>
            </Menu>
          </Box>
        </Box>
        
        <Divider sx={{ mb: 3 }} />
        
        {/* 过滤器区域 */}
        <Box mb={3}>
          <Grid container spacing={2}>
            <Grid item xs={12} sm={4}>
              <FormControl fullWidth size="small">
                <InputLabel>时间范围</InputLabel>
                <Select
                  value={timeRange}
                  label="时间范围"
                  onChange={handleTimeRangeChange as any}
                >
                  {timeRangeOptions.map(option => (
                    <MenuItem key={option.value} value={option.value}>
                      {option.label}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} sm={4}>
              <FormControl fullWidth size="small">
                <InputLabel>分组方式</InputLabel>
                <Select
                  value={groupBy}
                  label="分组方式"
                  onChange={handleGroupByChange as any}
                  startAdornment={
                    <GroupWorkIcon color="action" sx={{ mr: 1 }} />
                  }
                >
                  {groupByOptions.map(option => (
                    <MenuItem key={option.value} value={option.value}>
                      {option.label}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} sm={4}>
              <TextField
                fullWidth
                size="small"
                label="搜索"
                variant="outlined"
                value={searchTerm}
                onChange={handleSearchChange}
              />
            </Grid>
          </Grid>
        </Box>
        
        {/* 数据类型选择器 */}
        <Box mb={3}>
          <Typography variant="subtitle2" gutterBottom>数据类型:</Typography>
          <Stack direction="row" spacing={1} flexWrap="wrap">
            {availableTypes.map(type => (
              <Chip
                key={type}
                label={dataTypeLabels[type] || type}
                color={selectedTypes.includes(type) ? getColorForDataType(type) : 'default'}
                onClick={() => handleTypeToggle(type)}
                icon={
                  <Box sx={{ display: 'flex', alignItems: 'center' }}>
                    {getIconForDataType(type)}
                  </Box>
                }
                sx={{ m: 0.5 }}
              />
            ))}
          </Stack>
        </Box>
        
        {error && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {error}
          </Alert>
        )}
        
        {/* 时间线内容 */}
        {loading ? (
          <Box display="flex" justifyContent="center" alignItems="center" height={200}>
            <CircularProgress />
          </Box>
        ) : (
          <Box sx={{ maxHeight, overflowY: 'auto' }}>
            {renderTimelineContent()}
          </Box>
        )}
      </Box>
    </Paper>
  );
};

export default HealthDataTimeline; 
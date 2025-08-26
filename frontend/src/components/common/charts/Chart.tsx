import React from 'react';
import { Box, Typography, CircularProgress } from '@mui/material';
import {
  ResponsiveContainer,
  LineChart,
  Line,
  BarChart,
  Bar,
  PieChart,
  Pie,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  Cell
} from 'recharts';
import { ChartType, ChartConfig, CHART_COLORS, getColorForKey, formatChartValue, DataPoint } from './ChartTypes';

// 统一图表组件接口
interface ChartProps extends ChartConfig {
  loading?: boolean;
  error?: string;
  tooltipFormatter?: (value: any, name?: string) => string;
  emptyMessage?: string;
  onClickData?: (data: any) => void;
}

/**
 * 统一图表组件
 * 根据传入的配置渲染不同类型的图表
 */
const Chart: React.FC<ChartProps> = ({
  title,
  type = 'line',
  height = 300,
  data = [],
  loading = false,
  error,
  xKey = 'date',
  yKeys = [],
  colors = {},
  tooltipFormatter,
  stacked = false,
  showLegend = true,
  showTooltip = true,
  showGrid = true,
  emptyMessage = '暂无数据',
  onClickData
}) => {
  // 如果没有指定yKeys，尝试从第一个数据点中提取
  const getYKeys = (): string[] => {
    if (yKeys.length > 0) return yKeys;
    
    if (data.length === 0) return [];
    
    const firstItem = data[0];
    return Object.keys(firstItem).filter(key => 
      key !== xKey && 
      typeof firstItem[key] === 'number'
    );
  };
  
  const actualYKeys = getYKeys();
  
  // 默认tooltip格式化函数
  const defaultTooltipFormatter = (value: any, name?: string) => {
    return [formatChartValue(value), name || ''];
  };
  
  // 处理图表点击事件
  const handleClick = (data: DataPoint) => {
    if (onClickData) {
      onClickData(data);
    }
  };
  
  // 渲染加载中状态
  if (loading) {
    return (
      <Box 
        sx={{ 
          height, 
          display: 'flex', 
          flexDirection: 'column',
          alignItems: 'center', 
          justifyContent: 'center',
        }}
      >
        <CircularProgress size={40} />
        <Typography variant="body2" color="text.secondary" mt={1}>
          数据加载中...
        </Typography>
      </Box>
    );
  }
  
  // 渲染错误状态
  if (error) {
    return (
      <Box 
        sx={{ 
          height, 
          display: 'flex', 
          flexDirection: 'column',
          alignItems: 'center', 
          justifyContent: 'center',
          border: '1px dashed #f44336',
          borderRadius: 1,
          p: 2
        }}
      >
        <Typography variant="subtitle1" color="error" gutterBottom>
          {title || '图表错误'}
        </Typography>
        <Typography variant="body2" color="error" align="center">
          {error}
        </Typography>
      </Box>
    );
  }
  
  // 渲染空数据状态
  if (!data || data.length === 0 || actualYKeys.length === 0) {
    return (
      <Box 
        sx={{ 
          height, 
          display: 'flex', 
          flexDirection: 'column',
          alignItems: 'center', 
          justifyContent: 'center',
          border: '1px dashed grey',
          borderRadius: 1,
          p: 2
        }}
      >
        <Typography variant="subtitle1" gutterBottom>
          {title || '图表'}
        </Typography>
        <Typography variant="body2" color="text.secondary" align="center">
          {emptyMessage}
        </Typography>
      </Box>
    );
  }
  
  // 根据图表类型渲染不同的图表
  const renderChart = () => {
    switch (type) {
      case 'line':
        return (
          <LineChart data={data} onClick={handleClick}>
            {showGrid && <CartesianGrid strokeDasharray="3 3" />}
            <XAxis dataKey={xKey} />
            <YAxis />
            {showTooltip && <Tooltip formatter={tooltipFormatter || defaultTooltipFormatter} />}
            {showLegend && <Legend />}
            {actualYKeys.map((key, index) => (
              <Line 
                key={key}
                type="monotone" 
                dataKey={key} 
                stroke={getColorForKey(key, index, colors)}
                activeDot={{ r: 8 }}
                dot={{ r: 3 }}
              />
            ))}
          </LineChart>
        );
        
      case 'bar':
        return (
          <BarChart data={data} onClick={handleClick}>
            {showGrid && <CartesianGrid strokeDasharray="3 3" />}
            <XAxis dataKey={xKey} />
            <YAxis />
            {showTooltip && <Tooltip formatter={tooltipFormatter || defaultTooltipFormatter} />}
            {showLegend && <Legend />}
            {actualYKeys.map((key, index) => (
              <Bar 
                key={key}
                dataKey={key} 
                fill={getColorForKey(key, index, colors)}
                stackId={stacked ? 'stack' : undefined}
              />
            ))}
          </BarChart>
        );
        
      case 'area':
        return (
          <AreaChart data={data} onClick={handleClick}>
            {showGrid && <CartesianGrid strokeDasharray="3 3" />}
            <XAxis dataKey={xKey} />
            <YAxis />
            {showTooltip && <Tooltip formatter={tooltipFormatter || defaultTooltipFormatter} />}
            {showLegend && <Legend />}
            {actualYKeys.map((key, index) => (
              <Area 
                key={key}
                type="monotone" 
                dataKey={key} 
                fill={getColorForKey(key, index, colors)}
                stroke={getColorForKey(key, index, colors)}
                stackId={stacked ? 'stack' : undefined}
                fillOpacity={0.6}
              />
            ))}
          </AreaChart>
        );
        
      case 'pie':
        // 为饼图特殊处理数据
        const pieData = actualYKeys.map((key, index) => ({
          name: key,
          value: data.reduce((sum, item) => sum + (Number(item[key]) || 0), 0),
          color: getColorForKey(key, index, colors)
        }));
        
        return (
          <PieChart onClick={handleClick}>
            <Pie
              data={pieData}
              dataKey="value"
              nameKey="name"
              cx="50%"
              cy="50%"
              outerRadius={height > 300 ? 120 : 80}
              label={({name, value}: {name: string, value: number}) => `${name}: ${formatChartValue(value)}`}
              labelLine
            >
              {pieData.map((entry, index) => (
                <Cell key={`cell-${index}`} fill={entry.color} />
              ))}
            </Pie>
            {showTooltip && <Tooltip formatter={tooltipFormatter || defaultTooltipFormatter} />}
            {showLegend && <Legend />}
          </PieChart>
        );
        
      default:
        return (
          <LineChart data={data} onClick={handleClick}>
            {showGrid && <CartesianGrid strokeDasharray="3 3" />}
            <XAxis dataKey={xKey} />
            <YAxis />
            {showTooltip && <Tooltip formatter={tooltipFormatter || defaultTooltipFormatter} />}
            {showLegend && <Legend />}
            {actualYKeys.map((key, index) => (
              <Line 
                key={key}
                type="monotone" 
                dataKey={key} 
                stroke={getColorForKey(key, index, colors)}
                activeDot={{ r: 8 }}
              />
            ))}
          </LineChart>
        );
    }
  };
  
  return (
    <Box sx={{ width: '100%', height }}>
      {title && (
        <Typography variant="subtitle1" gutterBottom component="div">
          {title}
        </Typography>
      )}
      <Box sx={{ width: '100%', height: title ? height - 30 : height }}>
        <ResponsiveContainer width="100%" height="100%">
          {renderChart()}
        </ResponsiveContainer>
      </Box>
    </Box>
  );
};

export default Chart; 
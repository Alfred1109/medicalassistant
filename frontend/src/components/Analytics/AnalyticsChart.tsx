import React from 'react';
import { Box, Typography, CircularProgress } from '@mui/material';
import {
  LineChart, Line, BarChart, Bar, PieChart, Pie, 
  AreaChart, Area, ScatterChart, Scatter, 
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, Cell,
  ResponsiveContainer
} from 'recharts';
import { ChartType } from '../../types/dataAnalysis';

// 默认颜色
const COLORS = ['#0088FE', '#00C49F', '#FFBB28', '#FF8042', '#8884d8', '#82ca9d', '#ffc658'];

interface AnalyticsChartProps {
  title?: string;
  data: any[];
  type: ChartType;
  height?: number;
  loading?: boolean;
  xKey?: string;
  yKeys?: string[];
  colors?: Record<string, string>;
  nameKey?: string;
  valueKey?: string;
  tooltipFormatter?: (value: any, name?: string) => string;
}

/**
 * 通用分析图表组件
 * 支持多种图表类型的统一渲染接口
 */
const AnalyticsChart: React.FC<AnalyticsChartProps> = ({
  title,
  data = [],
  type = 'line',
  height = 300,
  loading = false,
  xKey = 'date',
  yKeys = [],
  colors = {},
  nameKey = 'name',
  valueKey = 'value',
  tooltipFormatter
}) => {
  // 如果没有指定yKeys，则尝试从第一个数据点中提取
  const getYKeys = (): string[] => {
    if (yKeys.length > 0) return yKeys;
    
    if (data.length === 0) return [];
    
    // 从第一个数据点中找出所有可能的y值键
    const firstItem = data[0];
    const keys = Object.keys(firstItem).filter(key => 
      key !== xKey && 
      typeof firstItem[key] === 'number'
    );
    
    return keys;
  };
  
  const actualYKeys = getYKeys();
  
  // 默认的tooltip格式化函数
  const defaultTooltipFormatter = (value: any) => {
    if (typeof value === 'number') {
      return value.toFixed(1);
    }
    return value?.toString() || '';
  };
  
  const getColorForKey = (key: string, index: number) => {
    return colors[key] || COLORS[index % COLORS.length];
  };
  
  // 渲染加载状态
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
  
  // 渲染空数据状态
  if (!data || data.length === 0) {
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
          暂无数据
        </Typography>
      </Box>
    );
  }
  
  // 根据图表类型渲染不同的图表
  const renderChart = () => {
    switch (type) {
      case 'line':
        return (
          <ResponsiveContainer width="100%" height={height}>
            <LineChart data={data}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey={xKey} />
              <YAxis />
              <Tooltip formatter={tooltipFormatter || defaultTooltipFormatter} />
              <Legend />
              {actualYKeys.map((key, index) => (
                <Line 
                  key={key}
                  type="monotone" 
                  dataKey={key} 
                  stroke={getColorForKey(key, index)}
                  activeDot={{ r: 8 }}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        );
        
      case 'bar':
        return (
          <ResponsiveContainer width="100%" height={height}>
            <BarChart data={data}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey={xKey} />
              <YAxis />
              <Tooltip formatter={tooltipFormatter || defaultTooltipFormatter} />
              <Legend />
              {actualYKeys.map((key, index) => (
                <Bar 
                  key={key} 
                  dataKey={key} 
                  fill={getColorForKey(key, index)} 
                />
              ))}
            </BarChart>
          </ResponsiveContainer>
        );
        
      case 'area':
        return (
          <ResponsiveContainer width="100%" height={height}>
            <AreaChart data={data}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey={xKey} />
              <YAxis />
              <Tooltip formatter={tooltipFormatter || defaultTooltipFormatter} />
              <Legend />
              {actualYKeys.map((key, index) => (
                <Area 
                  key={key}
                  type="monotone" 
                  dataKey={key} 
                  stroke={getColorForKey(key, index)}
                  fill={getColorForKey(key, index) + '80'} // 添加透明度
                />
              ))}
            </AreaChart>
          </ResponsiveContainer>
        );
        
      case 'pie':
        return (
          <ResponsiveContainer width="100%" height={height}>
            <PieChart>
              <Pie
                data={data}
                cx="50%"
                cy="50%"
                labelLine={true}
                outerRadius={height / 3}
                fill="#8884d8"
                dataKey={valueKey}
                nameKey={nameKey}
                label={({ name, value }) => `${name}: ${value}`}
              >
                {data.map((entry, index) => (
                  <Cell 
                    key={`cell-${index}`} 
                    fill={entry.color || COLORS[index % COLORS.length]} 
                  />
                ))}
              </Pie>
              <Tooltip formatter={tooltipFormatter || defaultTooltipFormatter} />
              <Legend />
            </PieChart>
          </ResponsiveContainer>
        );
        
      case 'scatter':
        return (
          <ResponsiveContainer width="100%" height={height}>
            <ScatterChart>
              <CartesianGrid />
              <XAxis type="number" dataKey={xKey} name={xKey} />
              <YAxis dataKey={actualYKeys[0]} name={actualYKeys[0]} />
              <Tooltip cursor={{ strokeDasharray: '3 3' }} formatter={tooltipFormatter || defaultTooltipFormatter} />
              <Legend />
              {actualYKeys.map((key, index) => (
                <Scatter 
                  key={key} 
                  name={key} 
                  data={data} 
                  fill={getColorForKey(key, index)} 
                />
              ))}
            </ScatterChart>
          </ResponsiveContainer>
        );
        
      default:
        return (
          <Box 
            sx={{ 
              height,
              display: 'flex', 
              alignItems: 'center', 
              justifyContent: 'center',
              border: '1px dashed grey',
              borderRadius: 1,
              p: 2
            }}
          >
            <Typography variant="body2" color="text.secondary">
              不支持的图表类型: {type}
            </Typography>
          </Box>
        );
    }
  };
  
  return (
    <Box>
      {title && (
        <Typography variant="subtitle1" gutterBottom align="center">
          {title}
        </Typography>
      )}
      {renderChart()}
    </Box>
  );
};

export default AnalyticsChart; 
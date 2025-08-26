import React, { useState } from 'react';
import { 
  Box, 
  Typography, 
  CircularProgress, 
  Paper, 
  Divider,
  ToggleButtonGroup,
  ToggleButton,
  FormControlLabel,
  Checkbox,
  Select,
  MenuItem,
  InputLabel,
  FormControl
} from '@mui/material';
import {
  LineChart, Line, 
  XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  ResponsiveContainer, Area
} from 'recharts';
import { PredictionResult, ConfidenceInterval } from '../../types/dataAnalysis';

// 预测方法映射表
const methodLabels = {
  linear: '线性回归',
  arima: 'ARIMA时间序列',
  prophet: 'Prophet分解',
  ensemble: '集成方法'
};

interface PredictionAnalysisChartProps {
  data?: PredictionResult;
  loading?: boolean;
  onMethodChange?: (method: string) => void;
  onConfidenceIntervalChange?: (showConfidenceInterval: boolean) => void;
}

/**
 * 高级预测分析图表组件
 * 支持展示多种预测算法的结果和置信区间
 */
const PredictionAnalysisChart: React.FC<PredictionAnalysisChartProps> = ({
  data,
  loading = false,
  onMethodChange,
  onConfidenceIntervalChange
}) => {
  const [showConfidenceInterval, setShowConfidenceInterval] = useState(true);
  const [selectedMethod, setSelectedMethod] = useState<string>('ensemble');
  const [comparisonMode, setComparisonMode] = useState<boolean>(false);
  
  // 处理方法切换
  const handleMethodChange = (_: React.MouseEvent<HTMLElement>, newMethod: string) => {
    if (newMethod !== null) {
      setSelectedMethod(newMethod);
      if (onMethodChange) {
        onMethodChange(newMethod);
      }
    }
  };
  
  // 处理置信区间显示切换
  const handleConfidenceIntervalChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    setShowConfidenceInterval(event.target.checked);
    if (onConfidenceIntervalChange) {
      onConfidenceIntervalChange(event.target.checked);
    }
  };
  
  // 处理比较模式切换
  const handleComparisonModeChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    setComparisonMode(event.target.checked);
  };
  
  // 渲染加载状态
  if (loading) {
    return (
      <Box 
        sx={{ 
          height: 400, 
          display: 'flex', 
          flexDirection: 'column',
          alignItems: 'center', 
          justifyContent: 'center',
        }}
      >
        <CircularProgress size={40} />
        <Typography variant="body2" color="text.secondary" mt={1}>
          预测分析中...
        </Typography>
      </Box>
    );
  }
  
  // 如果没有数据
  if (!data) {
    return (
      <Box 
        sx={{ 
          height: 400, 
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
          预测分析
        </Typography>
        <Typography variant="body2" color="text.secondary" align="center">
          暂无预测数据
        </Typography>
      </Box>
    );
  }
  
  // 格式化数据用于图表展示
  const chartData = formatDataForChart(data, selectedMethod, comparisonMode);
  
  // 生成所有方法的下拉菜单选项
  const methodOptions = Object.entries(methodLabels).map(([value, label]) => (
    <MenuItem key={value} value={value}>{label}</MenuItem>
  ));
  
  // 获取当前选中方法的预测数据
  const getPredictionData = () => {
    if (comparisonMode && data.all_predictions) {
      return data.all_predictions;
    }
    
    if (selectedMethod === 'ensemble' && data.all_predictions) {
      return data.all_predictions.ensemble;
    }
    
    return data.prediction;
  };
  
  // 获取当前数据的单位
  const getUnit = () => {
    switch (data.data_type) {
      case 'heart_rate':
        return 'bpm';
      case 'blood_pressure':
        return 'mmHg';
      case 'temperature':
        return '°C';
      case 'steps':
        return '步';
      default:
        return '';
    }
  };
  
  // 获取数据类型的显示名称
  const getDataTypeName = () => {
    switch (data.data_type) {
      case 'heart_rate':
        return '心率';
      case 'blood_pressure':
        return '血压';
      case 'temperature':
        return '体温';
      case 'steps':
        return '步数';
      default:
        return data.data_type;
    }
  };
  
  return (
    <Paper sx={{ p: 3 }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
        <Typography variant="h6">
          {getDataTypeName()}预测分析
        </Typography>
        
        <Box sx={{ display: 'flex', alignItems: 'center' }}>
          {data.all_predictions && (
            <FormControlLabel
              control={
                <Checkbox 
                  checked={comparisonMode}
                  onChange={handleComparisonModeChange}
                  color="primary"
                />
              }
              label="比较模式"
              sx={{ mr: 2 }}
            />
          )}
          
          <FormControlLabel
            control={
              <Checkbox 
                checked={showConfidenceInterval}
                onChange={handleConfidenceIntervalChange}
                color="primary"
              />
            }
            label="置信区间"
            sx={{ mr: 2 }}
          />
          
          {!comparisonMode && (
            <FormControl size="small" sx={{ minWidth: 150 }}>
              <InputLabel id="prediction-method-select-label">预测方法</InputLabel>
              <Select
                labelId="prediction-method-select-label"
                value={selectedMethod}
                label="预测方法"
                onChange={(e) => {
                  setSelectedMethod(e.target.value);
                  if (onMethodChange) {
                    onMethodChange(e.target.value);
                  }
                }}
              >
                {methodOptions}
              </Select>
            </FormControl>
          )}
        </Box>
      </Box>
      
      <Divider sx={{ mb: 2 }} />
      
      <Box sx={{ mb: 2 }}>
        <Typography variant="body2" color="text.secondary">
          基于最近{data.days_analyzed}天的数据，预测未来{data.prediction_days}天的趋势。
          使用{comparisonMode ? '多种预测方法对比' : methodLabels[selectedMethod as keyof typeof methodLabels]}。
          数据点：{data.data_points}个。
        </Typography>
      </Box>
      
      <Box sx={{ height: 400, mb: 3 }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="date" />
            <YAxis />
            <Tooltip formatter={(value) => [`${value} ${getUnit()}`, getDataTypeName()]} />
            <Legend />
            
            {/* 历史数据 */}
            <Line
              name="历史数据"
              type="monotone"
              dataKey="history"
              stroke="#8884d8"
              dot={false}
              activeDot={{ r: 8 }}
            />
            
            {/* 预测数据 - 比较模式 */}
            {comparisonMode && data.all_predictions && (
              <>
                <Line
                  name="线性回归"
                  type="monotone"
                  dataKey="linear"
                  stroke="#82ca9d"
                  strokeDasharray="3 3"
                  dot={false}
                />
                <Line
                  name="ARIMA"
                  type="monotone"
                  dataKey="arima"
                  stroke="#ff7300"
                  strokeDasharray="3 3"
                  dot={false}
                />
                <Line
                  name="Prophet"
                  type="monotone"
                  dataKey="prophet"
                  stroke="#0088fe"
                  strokeDasharray="3 3"
                  dot={false}
                />
                <Line
                  name="集成方法"
                  type="monotone"
                  dataKey="ensemble"
                  stroke="#FF8042"
                  strokeDasharray="3 3"
                  dot={false}
                />
              </>
            )}
            
            {/* 预测数据 - 单一模式 */}
            {!comparisonMode && (
              <Line
                name={`${methodLabels[selectedMethod as keyof typeof methodLabels]}预测`}
                type="monotone"
                dataKey="prediction"
                stroke="#82ca9d"
                strokeDasharray="3 3"
                dot={false}
              />
            )}
            
            {/* 置信区间 */}
            {showConfidenceInterval && !comparisonMode && (
              <>
                <Area
                  name="置信区间"
                  type="monotone"
                  dataKey="upperBound"
                  stroke="transparent"
                  fill="#82ca9d"
                  fillOpacity={0.2}
                />
                <Area
                  name="置信区间"
                  type="monotone"
                  dataKey="lowerBound"
                  stroke="transparent"
                  fill="#82ca9d"
                  fillOpacity={0.2}
                />
              </>
            )}
          </LineChart>
        </ResponsiveContainer>
      </Box>
      
      <Box>
        <Typography variant="body2" color="text.secondary">
          <strong>预测结果解读：</strong> {interpretPrediction(data, selectedMethod)}
        </Typography>
      </Box>
    </Paper>
  );
};

/**
 * 格式化数据用于图表展示
 */
function formatDataForChart(
  data: PredictionResult,
  selectedMethod: string,
  comparisonMode: boolean
): any[] {
  const historyData = data.history.aggregated;
  const chartData = [...historyData];
  
  // 获取最后一个历史数据点的日期
  const lastDate = new Date(historyData[historyData.length - 1].date);
  
  if (comparisonMode && data.all_predictions) {
    // 预测数据 - 比较模式
    for (let i = 0; i < data.prediction_days; i++) {
      const nextDate = new Date(lastDate);
      nextDate.setDate(lastDate.getDate() + i + 1);
      const dateStr = nextDate.toISOString().split('T')[0];
      
      const point: any = {
        date: dateStr,
        linear: data.all_predictions.linear?.values[i] || null,
        arima: data.all_predictions.arima?.values[i] || null,
        prophet: data.all_predictions.prophet?.values[i] || null,
        ensemble: data.all_predictions.ensemble?.values[i] || null
      };
      
      chartData.push(point);
    }
  } else {
    // 预测数据 - 单一模式
    const prediction = selectedMethod === 'ensemble' && data.all_predictions 
      ? data.all_predictions.ensemble 
      : data.prediction;
      
    if (prediction) {
      for (let i = 0; i < data.prediction_days; i++) {
        const nextDate = new Date(lastDate);
        nextDate.setDate(lastDate.getDate() + i + 1);
        const dateStr = nextDate.toISOString().split('T')[0];
        
        const point: any = {
          date: dateStr,
          prediction: prediction.values[i]
        };
        
        // 添加置信区间
        if (prediction.confidence_interval) {
          point.upperBound = prediction.confidence_interval[i].upper;
          point.lowerBound = prediction.confidence_interval[i].lower;
        }
        
        chartData.push(point);
      }
    }
  }
  
  // 格式化历史数据部分
  for (let i = 0; i < historyData.length; i++) {
    chartData[i] = {
      ...chartData[i],
      history: historyData[i].value
    };
  }
  
  return chartData;
}

/**
 * 解读预测结果
 */
function interpretPrediction(data: PredictionResult, selectedMethod: string): string {
  const predictionData = selectedMethod === 'ensemble' && data.all_predictions
    ? data.all_predictions.ensemble
    : data.prediction;
    
  if (!predictionData || !predictionData.values || predictionData.values.length === 0) {
    return '无法解读预测结果，预测数据不足。';
  }
  
  const firstValue = predictionData.values[0];
  const lastValue = predictionData.values[predictionData.values.length - 1];
  const change = ((lastValue - firstValue) / firstValue) * 100;
  const trend = change > 1 ? '上升' : change < -1 ? '下降' : '保持稳定';
  
  let interpretation = `根据${methodLabels[selectedMethod as keyof typeof methodLabels]}预测，`;
  interpretation += `未来${data.prediction_days}天内${data.data_type}将${trend}`;
  
  if (change > 1 || change < -1) {
    interpretation += `约${Math.abs(change).toFixed(1)}%。`;
  } else {
    interpretation += `。`;
  }
  
  // 如果有置信区间，添加不确定性描述
  if (predictionData.confidence_interval) {
    const lastConfidence = predictionData.confidence_interval[predictionData.confidence_interval.length - 1];
    const confidenceRange = lastConfidence.upper - lastConfidence.lower;
    const relativeCertainty = confidenceRange / lastValue;
    
    if (relativeCertainty < 0.1) {
      interpretation += ' 预测具有较高确定性。';
    } else if (relativeCertainty < 0.3) {
      interpretation += ' 预测具有中等确定性。';
    } else {
      interpretation += ' 预测具有较大不确定性，建议谨慎解读。';
    }
  }
  
  return interpretation;
}

export default PredictionAnalysisChart; 
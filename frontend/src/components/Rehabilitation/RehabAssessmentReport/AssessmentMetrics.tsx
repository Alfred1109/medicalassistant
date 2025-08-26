import React from 'react';
import { 
  Box, 
  Typography, 
  Paper, 
  Grid,
  LinearProgress,
  Chip
} from '@mui/material';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableContainer from '@mui/material/TableContainer';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import TrendingUpIcon from '@mui/icons-material/TrendingUp';
import TrendingDownIcon from '@mui/icons-material/TrendingDown';
import TrendingFlatIcon from '@mui/icons-material/TrendingFlat';
import { AssessmentMetric } from './index';
import { formatDate, formatPercentage } from './utils';

interface AssessmentMetricsProps {
  metrics: AssessmentMetric[];
  assessmentDate: string;
}

/**
 * 康复评估报告中的评估指标组件，展示各项评估指标及其变化趋势
 */
const AssessmentMetrics: React.FC<AssessmentMetricsProps> = ({
  metrics,
  assessmentDate
}) => {
  // 计算总体改善率
  const calculateOverallImprovement = (): number => {
    if (!metrics || metrics.length === 0) return 0;
    
    const totalImprovement = metrics.reduce((acc, metric) => {
      return acc + metric.improvementPercentage;
    }, 0);
    
    return totalImprovement / metrics.length;
  };
  
  const overallImprovement = calculateOverallImprovement();
  const isPositiveOverall = overallImprovement >= 0;
  
  return (
    <Paper 
      elevation={0} 
      sx={{ 
        p: 3, 
        mb: 3,
        border: '1px solid #eee',
        '@media print': { border: 'none', p: 0, boxShadow: 'none' }
      }}
    >
      <Typography variant="h6" sx={{ mb: 2, fontWeight: 'bold' }}>
        评估指标
      </Typography>
      
      <Box sx={{ mb: 3 }}>
        <Grid container spacing={2} alignItems="center">
          <Grid item xs={12} sm={4}>
            <Typography variant="subtitle1" sx={{ fontWeight: 'bold' }}>
              总体改善情况
            </Typography>
            <Typography variant="body2" color="text.secondary">
              评估日期: {formatDate(assessmentDate)}
            </Typography>
          </Grid>
          <Grid item xs={12} sm={8}>
            <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
              <Box sx={{ flexGrow: 1, mr: 2 }}>
                <LinearProgress 
                  variant="determinate" 
                  value={Math.abs(overallImprovement) * 100}
                  color={isPositiveOverall ? "success" : "error"}
                  sx={{ height: 10, borderRadius: 5 }}
                />
              </Box>
              <Box sx={{ display: 'flex', alignItems: 'center' }}>
                {isPositiveOverall ? (
                  <TrendingUpIcon color="success" />
                ) : (
                  <TrendingDownIcon color="error" />
                )}
                <Typography 
                  variant="h6" 
                  sx={{ 
                    ml: 0.5, 
                    color: isPositiveOverall ? 'success.main' : 'error.main'
                  }}
                >
                  {formatPercentage(Math.abs(overallImprovement), 1)}
                </Typography>
              </Box>
            </Box>
            <Typography variant="body2" color="text.secondary">
              {isPositiveOverall 
                ? '相比初始状态有显著改善' 
                : '相比初始状态有所下降，需调整康复计划'}
            </Typography>
          </Grid>
        </Grid>
      </Box>
      
      {/* 详细指标表格 */}
      <TableContainer>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell sx={{ fontWeight: 'bold' }}>指标名称</TableCell>
              <TableCell align="right" sx={{ fontWeight: 'bold' }}>初始值</TableCell>
              <TableCell align="right" sx={{ fontWeight: 'bold' }}>当前值</TableCell>
              <TableCell align="right" sx={{ fontWeight: 'bold' }}>目标值</TableCell>
              <TableCell align="right" sx={{ fontWeight: 'bold' }}>变化量</TableCell>
              <TableCell align="right" sx={{ fontWeight: 'bold' }}>变化率</TableCell>
              <TableCell align="center" sx={{ fontWeight: 'bold' }}>趋势</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {metrics.map((metric, index) => (
              <TableRow key={index}>
                <TableCell component="th" scope="row">
                  {metric.name}
                </TableCell>
                <TableCell align="right">{`${metric.initialValue} ${metric.unit}`}</TableCell>
                <TableCell align="right">{`${metric.currentValue} ${metric.unit}`}</TableCell>
                <TableCell align="right">{`${metric.targetValue} ${metric.unit}`}</TableCell>
                <TableCell align="right">
                  {`${metric.improvement > 0 ? '+' : ''}${metric.improvement} ${metric.unit}`}
                </TableCell>
                <TableCell align="right">
                  <Chip
                    label={formatPercentage(metric.improvementPercentage, 1)}
                    size="small"
                    color={metric.isPositiveTrend ? "success" : "error"}
                    sx={{ 
                      fontWeight: 'bold',
                      minWidth: '60px'
                    }}
                  />
                </TableCell>
                <TableCell align="center">
                  {metric.trend === 'up' && (
                    <TrendingUpIcon color={metric.isPositiveTrend ? "success" : "error"} />
                  )}
                  {metric.trend === 'down' && (
                    <TrendingDownIcon color={metric.isPositiveTrend ? "success" : "error"} />
                  )}
                  {metric.trend === 'flat' && (
                    <TrendingFlatIcon color="action" />
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
      
      <Typography variant="body2" color="text.secondary" sx={{ mt: 2, fontStyle: 'italic' }}>
        注: 变化率为当前值相对于初始值的百分比变化，趋势的正负取决于指标的性质（如关节活动度上升为积极趋势，而疼痛指数下降为积极趋势）
      </Typography>
    </Paper>
  );
};

export default AssessmentMetrics; 
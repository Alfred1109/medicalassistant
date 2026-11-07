import React, { useState, useEffect } from 'react';
import {
  Box,
  Card,
  CardContent,
  Typography,
  Grid,
  LinearProgress,
  Paper,
  List,
  ListItem,
  ListItemText,
  Alert,
  CircularProgress,
} from '@mui/material';
import { format, differenceInDays, parseISO } from 'date-fns';
import { zhCN } from 'date-fns/locale';
import api from '../../services/api';
import { RehabPlan } from '../../types/rehab';

/**
 * 康复进度评估组件（真实数据版）
 *
 * 数据来源（均为后端真实端点，响应字段以 rehabilitation_router.py 为准）：
 * - GET /rehabilitation/plans/{plan_id}/statistics  进度统计
 * - GET /rehabilitation/plans/{plan_id}/trends      完成趋势（按天）
 *
 * 后端不提供历史对比/模拟指标，凡统计字段为 null（如 range_of_motion、
 * muscle_strength）一律如实展示"暂无数据"，不做任何虚构。
 */

// GET /plans/{plan_id}/statistics 的响应结构（rehabilitation_service.calculate_plan_statistics）
interface PlanStatistics {
  plan_id: string;
  time_range: string;
  total_records: number;
  completed_records: number;
  completion_rate: number | null;
  avg_pain_level: number | null;
  avg_difficulty_rating: number | null;
  range_of_motion: null;
  muscle_strength: null;
  weekly_completion: { week_start: string; total: number; completed: number; completion_rate: number }[];
  per_exercise: {
    exercise_id: string;
    exercise_name: string;
    total: number;
    completed: number;
    completion_rate: number | null;
    avg_pain_level: number | null;
    avg_difficulty_rating: number | null;
  }[];
  unsupported_metrics: string[];
  data_source: string;
  data_notes: string[];
}

// GET /plans/{plan_id}/trends 的响应结构（metric=completion 时 series 每项含完成率）
interface PlanTrends {
  plan_id: string;
  metric: string;
  days: number;
  total_records: number;
  series: { date: string; total: number; completed: number; completion_rate: number }[];
  data_source: string;
  data_notes: string[];
}

interface RehabProgressEvaluationProps {
  plan: RehabPlan;
}

const RehabProgressEvaluation: React.FC<RehabProgressEvaluationProps> = ({ plan }) => {
  const [statistics, setStatistics] = useState<PlanStatistics | null>(null);
  const [trends, setTrends] = useState<PlanTrends | null>(null);
  const [fetchLoading, setFetchLoading] = useState<boolean>(false);
  const [fetchError, setFetchError] = useState<string | null>(null);

  const planId = plan.id || plan._id || '';

  // 拉取真实统计数据与趋势数据
  useEffect(() => {
    if (!planId) return;
    let cancelled = false;

    const fetchData = async () => {
      setFetchLoading(true);
      setFetchError(null);
      try {
        const [statsRes, trendsRes] = await Promise.all([
          api.get<PlanStatistics>(`/rehabilitation/plans/${planId}/statistics`),
          api.get<PlanTrends>(`/rehabilitation/plans/${planId}/trends`, {
            params: { metric: 'completion', days: 30 },
          }),
        ]);
        if (!cancelled) {
          setStatistics(statsRes.data);
          setTrends(trendsRes.data);
        }
      } catch (err: any) {
        if (!cancelled) {
          setFetchError(err?.response?.data?.detail || err?.message || '获取康复进度数据失败');
          setStatistics(null);
          setTrends(null);
        }
      } finally {
        if (!cancelled) {
          setFetchLoading(false);
        }
      }
    };

    fetchData();
    return () => {
      cancelled = true;
    };
  }, [planId]);

  // 计划内剩余天数（基于真实起止日期，无结束日期则如实标注）
  const remainingDays = (() => {
    const endDateStr = plan.endDate || plan.end_date;
    if (!endDateStr) return null;
    try {
      const days = differenceInDays(parseISO(endDateStr), new Date());
      return days >= 0 ? days : 0;
    } catch {
      return null;
    }
  })();

  // 格式化日期
  const formatDate = (dateString?: string): string => {
    if (!dateString) return '';
    try {
      return format(parseISO(dateString), 'yyyy年MM月dd日', { locale: zhCN });
    } catch {
      return dateString;
    }
  };


  return (
    <Box>
      <Card variant="outlined" sx={{ mb: 3 }}>
        <CardContent>
          <Typography variant="h6" component="h2" mb={2}>
            康复进度评估
          </Typography>

          {/* 错误状态 */}
          {fetchError && (
            <Alert severity="error" sx={{ mb: 2 }}>
              {fetchError}
            </Alert>
          )}

          {/* 加载状态 */}
          {fetchLoading && (
            <Box display="flex" justifyContent="center" my={4}>
              <CircularProgress />
            </Box>
          )}

          {/* 数据区 */}
          {!fetchLoading && (
            <>
              {/* 计划基本信息（来自 plan 本身的真实字段） */}
              <Box mb={3}>
                <Grid container spacing={2}>
                  <Grid item xs={12} sm={6} md={3}>
                    <Paper elevation={0} variant="outlined" sx={{ p: 2, height: '100%' }}>
                      <Typography variant="body2" color="textSecondary" gutterBottom>
                        康复开始日期
                      </Typography>
                      <Typography variant="body1" fontWeight="medium">
                        {formatDate(plan.startDate || plan.start_date) || '未设定'}
                      </Typography>
                    </Paper>
                  </Grid>
                  <Grid item xs={12} sm={6} md={3}>
                    <Paper elevation={0} variant="outlined" sx={{ p: 2, height: '100%' }}>
                      <Typography variant="body2" color="textSecondary" gutterBottom>
                        预计结束日期
                      </Typography>
                      <Typography variant="body1" fontWeight="medium">
                        {(plan.endDate || plan.end_date) ? formatDate(plan.endDate || plan.end_date) : '未设定'}
                      </Typography>
                    </Paper>
                  </Grid>
                  <Grid item xs={12} sm={6} md={3}>
                    <Paper elevation={0} variant="outlined" sx={{ p: 2, height: '100%' }}>
                      <Typography variant="body2" color="textSecondary" gutterBottom>
                        剩余天数
                      </Typography>
                      <Typography variant="body1" fontWeight="medium">
                        {remainingDays !== null ? `${remainingDays} 天` : '未设定结束日期'}
                      </Typography>
                    </Paper>
                  </Grid>
                  <Grid item xs={12} sm={6} md={3}>
                    <Paper
                      elevation={0}
                      variant="outlined"
                      sx={{ p: 2, height: '100%', bgcolor: 'primary.light', borderColor: 'primary.main' }}
                    >
                      <Typography variant="body2" color="primary.contrastText" gutterBottom>
                        总体完成度
                      </Typography>
                      <Typography variant="h5" fontWeight="bold" color="primary.contrastText">
                        {statistics?.completion_rate != null ? `${statistics.completion_rate}%` : '暂无数据'}
                      </Typography>
                      {statistics?.completion_rate != null && (
                        <LinearProgress
                          variant="determinate"
                          value={Math.min(100, statistics.completion_rate)}
                          sx={{ height: 8, borderRadius: 4, mt: 1, bgcolor: 'rgba(255,255,255,0.3)' }}
                        />
                      )}
                    </Paper>
                  </Grid>
                </Grid>
              </Box>

              {/* 空状态：后端明确返回无进度记录 */}
              {statistics && statistics.total_records === 0 && (
                <Alert severity="info" sx={{ mb: 2 }}>
                  该计划暂无进度记录。请在计划详情中记录运动完成情况后，此处将展示真实统计数据。
                </Alert>
              )}

              {/* 核心统计指标（来自 /statistics 的真实字段，null 一律展示"暂无数据"） */}
              <Typography variant="subtitle2" gutterBottom>
                核心康复指标
              </Typography>
              <Grid container spacing={2} sx={{ mb: 3 }}>
                {[
                  { name: '进度记录总数', value: statistics ? String(statistics.total_records) : null, unit: '条' },
                  { name: '已完成记录', value: statistics ? String(statistics.completed_records) : null, unit: '条' },
                  {
                    name: '平均疼痛指数',
                    value: statistics?.avg_pain_level != null ? String(Math.round(statistics.avg_pain_level * 10) / 10) : null,
                    unit: '级',
                  },
                  {
                    name: '平均难度评分',
                    value: statistics?.avg_difficulty_rating != null ? String(Math.round(statistics.avg_difficulty_rating * 10) / 10) : null,
                    unit: '分',
                  },
                ].map((metric) => (
                  <Grid item xs={12} sm={6} md={3} key={metric.name}>
                    <Card variant="outlined" sx={{ height: '100%' }}>
                      <CardContent sx={{ p: 2, '&:last-child': { pb: 2 } }}>
                        <Typography variant="body2" color="textSecondary" gutterBottom>
                          {metric.name}
                        </Typography>
                        <Typography variant="h6" component="span" fontWeight="medium">
                          {metric.value != null ? `${metric.value}${metric.unit}` : '暂无数据'}
                        </Typography>
                      </CardContent>
                    </Card>
                  </Grid>
                ))}
              </Grid>

              {/* 每周完成情况（来自 statistics.weekly_completion 的真实分桶数据） */}
              <Typography variant="subtitle2" gutterBottom>
                每周完成情况
              </Typography>
              {statistics && statistics.weekly_completion.length > 0 ? (
                <List dense>
                  {statistics.weekly_completion.map((week) => (
                    <ListItem key={week.week_start} divider>
                      <ListItemText
                        primary={`${formatDate(week.week_start)} 起的一周`}
                        secondary={`完成 ${week.completed}/${week.total} 次`}
                      />
                      <Box sx={{ width: '40%', display: 'flex', alignItems: 'center' }}>
                        <Box sx={{ width: '100%', mr: 1 }}>
                          <LinearProgress variant="determinate" value={Math.min(100, week.completion_rate)} />
                        </Box>
                        <Typography variant="body2">{week.completion_rate}%</Typography>
                      </Box>
                    </ListItem>
                  ))}
                </List>
              ) : (
                <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
                  暂无每周完成数据
                </Typography>
              )}

              {/* 近30天完成趋势（来自 /trends metric=completion 的真实按天数据） */}
              <Typography variant="subtitle2" gutterBottom>
                近30天完成趋势
              </Typography>
              {trends && trends.series.length > 0 ? (
                <List dense>
                  {trends.series.map((point) => (
                    <ListItem key={point.date} divider>
                      <ListItemText
                        primary={point.date}
                        secondary={`完成 ${point.completed}/${point.total} 次`}
                      />
                      <Box sx={{ width: '40%', display: 'flex', alignItems: 'center' }}>
                        <Box sx={{ width: '100%', mr: 1 }}>
                          <LinearProgress variant="determinate" value={Math.min(100, point.completion_rate)} />
                        </Box>
                        <Typography variant="body2">{point.completion_rate}%</Typography>
                      </Box>
                    </ListItem>
                  ))}
                </List>
              ) : (
                <Typography variant="body2" color="text.secondary">
                  暂无趋势数据
                </Typography>
              )}

              {/* 后端数据说明（如实透出，例如"计划内暂无进度记录"） */}
              {statistics && statistics.data_notes.length > 0 && (
                <Box mt={2}>
                  {statistics.data_notes.map((note, index) => (
                    <Typography key={index} variant="caption" color="text.secondary" display="block">
                      数据说明：{note}
                    </Typography>
                  ))}
                </Box>
              )}
            </>
          )}
        </CardContent>
      </Card>
    </Box>
  );
};

export default RehabProgressEvaluation;

import React, { useState } from 'react';
import { formatAppDate } from '../../utils/dateTime';
import { timelineMeasurement } from '../../utils/healthTimeline';
import { useSelector } from 'react-redux';
import {
  Box,
  Typography,
  Paper,
  Tabs,
  Tab,
  Divider,
  List,
  ListItem,
  ListItemText,
  Chip,
  CircularProgress,
  Button,
} from '@mui/material';
import type { RootState } from '../../store';
import { apiService } from '../../services/api';
import apiClient from '../../services/apiClient';
import type { FollowUpRecord } from '../../types/followup';
import { getFollowUpStatusBadge, getFollowUpSummaryRows, getFollowUpTypeLabel } from '../../constants/followup';

// GET /api/health-records 返回的 HealthRecordResponse 关键字段
// （见 backend/app/schemas/health_record.py，content 为字符串，tags / attachments 为数组）
interface HealthRecordItem {
  id: string;
  patient_id?: string;
  record_type?: string;
  title: string;
  content?: string;
  created_by?: string;
  tags?: string[];
  created_at?: string;
  updated_at?: string;
}

// GET /api/health-records/timeline/{patient_id} 返回的 HealthTimelineItem 字段
interface HealthTimelineItem {
  id: string;
  item_type?: string;
  title: string;
  description?: string | null;
  timestamp?: string | null;
  data?: { source?: { view?: string; orphan?: boolean; ambiguous?: boolean }; metadata?: { source?: string; quality_flags?: unknown; values?: Record<string, unknown> } };
}

// 患者端随访只读呈现（T73）：状态与小结均为后端 FollowUpRecordResponse 投影
const formatFollowUpDate = (value?: string | null) => formatDateTime(value) ?? '时间未知';

// 时间显示：无效或缺失时间返回 null，避免渲染出 NaN/Invalid Date
const formatDateTime = (value?: string | null) => {
  if (!value) return null;
  return formatAppDate(value, 'minute', { invalid: '' }) || null;
};

// 面板内通用的加载中提示
const PanelLoading = () => (
  <Box display="flex" justifyContent="center" alignItems="center" py={4}>
    <CircularProgress size={24} sx={{ mr: 1 }} />
    <Typography variant="body2" color="text.secondary">
      加载中...
    </Typography>
  </Box>
);

// 面板内通用的错误提示
const PanelError = ({ text }: { text: string }) => (
  <Box textAlign="center" py={4}>
    <Typography variant="body2" color="error">
      {text}
    </Typography>
  </Box>
);

// 面板内通用的空数据提示
const PanelEmpty = ({ text }: { text: string }) => (
  <Box textAlign="center" py={4}>
    <Typography variant="body2" color="text.secondary">
      {text}
    </Typography>
  </Box>
);

const HealthRecords: React.FC = () => {
  const [tabValue, setTabValue] = useState(0);
  const currentUser = useSelector((state: RootState) => state.auth.user);

  // 真实数据状态：健康档案列表、医疗时间线与随访安排（T73 患者端只读）
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [records, setRecords] = useState<HealthRecordItem[]>([]);
  const [timeline, setTimeline] = useState<HealthTimelineItem[]>([]);
  const [timelineView, setTimelineView] = useState<'current' | 'history'>('current');
  const [timelinePage, setTimelinePage] = useState(0);
  const [followUps, setFollowUps] = useState<FollowUpRecord[]>([]);

  const patientId = currentUser?.id;

  // 从真实后端拉取健康档案与时间线；患者本人 ID 取自认证 store
  React.useEffect(() => {
    if (!patientId) {
      // 未登录 / 用户信息未就绪时不发请求，如实提示
      setRecords([]);
      setTimeline([]);
      setFollowUps([]);
      setError(false);
      setLoading(false);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError(false);

    const loadData = async () => {
      let targetPatientId: string;
      try {
        const context = await apiClient.get<{ patient_id: string }>('/health-records/patient-context');
        if (cancelled) return;
        if (!context || typeof context.patient_id !== 'string' || !context.patient_id) throw new Error('invalid patient context');
        targetPatientId = context.patient_id;
      } catch {
        if (!cancelled) { setRecords([]); setTimeline([]); setFollowUps([]); setError(true); setLoading(false); }
        return;
      }
      const [recordsRes, timelineRes, followUpsRes] = await Promise.allSettled([
        apiService.getHealthRecords(targetPatientId),
        apiClient.get<HealthTimelineItem[]>(`/health-records/timeline/${encodeURIComponent(targetPatientId)}`, {
          params: { view: timelineView, skip: timelinePage * 50, limit: 50 },
        }),
        apiService.getFollowUps(targetPatientId),
      ]);

      if (cancelled) return;

      if (recordsRes.status === 'fulfilled' && Array.isArray(recordsRes.value?.data)) {
        setRecords(recordsRes.value.data);
      } else {
        setRecords([]);
        setError(true);
      }

      if (timelineRes.status === 'fulfilled' && Array.isArray(timelineRes.value)) {
        setTimeline(timelineRes.value);
      } else {
        setTimeline([]);
        setError(true);
      }

      if (followUpsRes.status === 'fulfilled' && Array.isArray(followUpsRes.value?.data)) {
        setFollowUps(followUpsRes.value.data);
      } else {
        setFollowUps([]);
        setError(true);
      }

      setLoading(false);
    };

    loadData();

    return () => {
      cancelled = true;
    };
  }, [patientId, timelineView, timelinePage]);

  const handleTabChange = (event: React.SyntheticEvent, newValue: number) => {
    setTabValue(newValue);
  };

  return (
    <Box>
      <Typography variant="h5" gutterBottom>
        健康档案
      </Typography>

      {!patientId ? (
        // 用户信息未就绪时统一提示，不渲染任何假数据
        <Paper sx={{ mt: 2 }}>
          <PanelEmpty text="未登录或用户信息加载中，暂时无法获取健康档案" />
        </Paper>
      ) : (
        <Paper sx={{ width: '100%', mt: 2 }}>
          <Tabs
            value={tabValue}
            onChange={handleTabChange}
            indicatorColor="primary"
            textColor="primary"
            variant="fullWidth"
          >
            <Tab label="健康档案" />
            <Tab label="健康时间线" />
            <Tab label="随访安排" />
          </Tabs>

          <Box sx={{ p: 3 }}>
            {tabValue === 1 && <Box sx={{ mb: 2 }}>
              <Button disabled={loading || timelineView === 'current'} onClick={() => { setTimelineView('current'); setTimelinePage(0); }}>当前事实</Button>
              <Button disabled={loading || timelineView === 'history'} onClick={() => { setTimelineView('history'); setTimelinePage(0); }}>只读历史快照</Button>
              <Typography variant="body2" color="text.secondary">{timelineView === 'history'
                ? '历史快照保留当时记录，可能与当前事实不同；包含已删除来源的原快照。'
                : '实时读取健康数据、随访与评估；无法核实来源的历史条目单独标识。健康记录按最近更新时间排列，原始时间保留在来源数据中。'}</Typography>
              <Button disabled={loading || timelinePage === 0} onClick={() => setTimelinePage(page => page - 1)}>上一页</Button>
              <Typography component="span" variant="body2">第 {timelinePage + 1} 页</Typography>
              <Button disabled={loading || timeline.length < 50} onClick={() => setTimelinePage(page => page + 1)}>下一页</Button>
            </Box>}
            {loading ? (
              <PanelLoading />
            ) : error ? (
              <PanelError text="健康档案数据加载失败，请稍后重试" />
            ) : tabValue === 2 ? (
              // 随访安排（只读，T73）：状态徽章区分系统自动/手工来源，含随访小结
              followUps.length === 0 ? (
                <PanelEmpty text="暂无随访安排" />
              ) : (
                <List>
                  {followUps.map((item, index) => {
                    const summaryRows = getFollowUpSummaryRows(item.followup_summary);
                    return (
                      <React.Fragment key={item.id ?? `followup-${index}`}>
                        <ListItem alignItems="flex-start" sx={{ px: 0 }}>
                          <ListItemText
                            primary={
                              <Box display="flex" justifyContent="space-between" alignItems="center" flexWrap="wrap">
                                <Box display="flex" alignItems="center">
                                  <Typography variant="subtitle1">{getFollowUpTypeLabel(item.follow_up_type)}</Typography>
                                  <Chip
                                    label={getFollowUpStatusBadge(item).label}
                                    size="small"
                                    color={getFollowUpStatusBadge(item).color}
                                    sx={{ ml: 1 }}
                                  />
                                </Box>
                                <Typography variant="body2" color="text.secondary">
                                  计划：{formatFollowUpDate(item.scheduled_date)}
                                  {item.actual_date ? ` · 完成：${formatFollowUpDate(item.actual_date)}` : ''}
                                </Typography>
                              </Box>
                            }
                            secondary={
                              <>
                                {item.description && (
                                  <Typography variant="body2" component="span" color="text.primary" sx={{ display: 'block', mt: 0.5, whiteSpace: 'pre-wrap' }}>
                                    {item.description}
                                  </Typography>
                                )}
                                {summaryRows.length > 0 && (
                                  <Box mt={1}>
                                    <Typography variant="caption" color="text.secondary">随访小结</Typography>
                                    {summaryRows.map(row => (
                                      <Typography key={row.label} variant="body2" component="span" color="text.primary" sx={{ display: 'block', whiteSpace: 'pre-wrap' }}>
                                        {row.label}：{row.value}
                                      </Typography>
                                    ))}
                                  </Box>
                                )}
                              </>
                            }
                          />
                        </ListItem>
                        {index < followUps.length - 1 && <Divider variant="inset" component="li" />}
                      </React.Fragment>
                    );
                  })}
                </List>
              )
            ) : tabValue === 0 ? (
              // 健康档案列表（真实数据）
              records.length === 0 ? (
                <PanelEmpty text="暂无健康档案记录" />
              ) : (
                <List>
                  {records.map((record, index) => (
                    <React.Fragment key={record.id ?? `record-${index}`}>
                      <ListItem alignItems="flex-start" sx={{ px: 0 }}>
                        <ListItemText
                          primary={
                            <Box display="flex" justifyContent="space-between" alignItems="center" flexWrap="wrap">
                              <Box display="flex" alignItems="center">
                                <Typography variant="subtitle1">{record.title}</Typography>
                                {record.record_type && (
                                  <Chip
                                    label={record.record_type}
                                    size="small"
                                    color="primary"
                                    variant="outlined"
                                    sx={{ ml: 1 }}
                                  />
                                )}
                              </Box>
                              <Typography variant="body2" color="text.secondary">
                                {formatDateTime(record.created_at) ?? '时间未知'}
                              </Typography>
                            </Box>
                          }
                          secondary={
                            <>
                              {record.content && (
                                <Typography
                                  variant="body2"
                                  component="span"
                                  color="text.primary"
                                  sx={{ display: 'block', mt: 0.5, whiteSpace: 'pre-wrap' }}
                                >
                                  {record.content}
                                </Typography>
                              )}
                              {(record.tags ?? []).length > 0 && (
                                <Box mt={1}>
                                  {record.tags!.map((tag, tagIndex) => (
                                    <Chip key={tagIndex} label={tag} size="small" sx={{ mr: 0.5, mb: 0.5 }} />
                                  ))}
                                </Box>
                              )}
                            </>
                          }
                        />
                      </ListItem>
                      {index < records.length - 1 && <Divider variant="inset" component="li" />}
                    </React.Fragment>
                  ))}
                </List>
              )
            ) : (
              // 健康时间线（真实数据）
              timeline.length === 0 ? (
                <PanelEmpty text="暂无健康时间线数据" />
              ) : (
                <List>
                  {timeline.map((item, index) => (
                    <React.Fragment key={item.id ?? `timeline-${index}`}>
                      <ListItem alignItems="flex-start" sx={{ px: 0 }}>
                        <ListItemText
                          primary={
                            <Box display="flex" justifyContent="space-between" alignItems="center" flexWrap="wrap">
                              <Box display="flex" alignItems="center">
                                <Typography variant="subtitle1">{item.title}</Typography>
                                {item.item_type && (
                                  <Chip
                                    label={item.item_type}
                                    size="small"
                                    color="secondary"
                                    variant="outlined"
                                    sx={{ ml: 1 }}
                                  />
                                )}
                              </Box>
                              <Typography variant="body2" color="text.secondary">
                                {formatDateTime(item.timestamp) ?? '时间未知'}
                              </Typography>
                            </Box>
                          }
                          secondary={
                            <>
                              <Typography variant="body2" component="span" color="text.primary">
                                {item.data?.source?.view === 'history' ? `${item.data.source.ambiguous ? '来源关联有歧义的历史快照' : item.data.source.orphan ? '孤儿历史快照' : '历史快照'}：` : ''}{timelineMeasurement(item.data?.metadata?.values) ?? item.description}
                              </Typography>
                              {item.data?.metadata?.source && <Typography variant="caption" component="span" display="block">来源：{item.data.metadata.source}</Typography>}
                              {Array.isArray(item.data?.metadata?.quality_flags) && item.data.metadata.quality_flags.length > 0 && <Typography variant="body2" component="span" display="block" color="warning.main">读数质量待核实：{item.data.metadata.quality_flags.map(String).join('、')}</Typography>}
                              {item.data?.metadata?.quality_flags != null && !Array.isArray(item.data.metadata.quality_flags) && <Typography variant="body2" component="span" display="block" color="warning.main">读数质量标志格式异常，请核实原始记录。</Typography>}
                            </>
                          }
                        />
                      </ListItem>
                      {index < timeline.length - 1 && <Divider variant="inset" component="li" />}
                    </React.Fragment>
                  ))}
                </List>
              )
            )}
          </Box>
        </Paper>
      )}
    </Box>
  );
};

export default HealthRecords;

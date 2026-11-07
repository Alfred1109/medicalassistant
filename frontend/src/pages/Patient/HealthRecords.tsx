import React, { useState } from 'react';
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
} from '@mui/material';
import type { RootState } from '../../store';
import { apiService } from '../../services/api';
import apiClient from '../../services/apiClient';

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
  occurred_at?: string;
}

// 时间显示：无效或缺失时间返回 null，避免渲染出 NaN/Invalid Date
const formatDateTime = (value?: string | null) => {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return `${date.getFullYear()}-${(date.getMonth() + 1).toString().padStart(2, '0')}-${date.getDate().toString().padStart(2, '0')} ${date.getHours().toString().padStart(2, '0')}:${date.getMinutes().toString().padStart(2, '0')}`;
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

  // 真实数据状态：健康档案列表与医疗时间线
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [records, setRecords] = useState<HealthRecordItem[]>([]);
  const [timeline, setTimeline] = useState<HealthTimelineItem[]>([]);

  const patientId = currentUser?.id;

  // 从真实后端拉取健康档案与时间线；患者本人 ID 取自认证 store
  React.useEffect(() => {
    if (!patientId) {
      // 未登录 / 用户信息未就绪时不发请求，如实提示
      setRecords([]);
      setTimeline([]);
      setError(false);
      setLoading(false);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError(false);

    const loadData = async () => {
      const [recordsRes, timelineRes] = await Promise.allSettled([
        apiService.getHealthRecords(patientId),
        apiClient.get<HealthTimelineItem[]>(`/health-records/timeline/${patientId}`),
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

      setLoading(false);
    };

    loadData();

    return () => {
      cancelled = true;
    };
  }, [patientId]);

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
          </Tabs>

          <Box sx={{ p: 3 }}>
            {loading ? (
              <PanelLoading />
            ) : error ? (
              <PanelError text="健康档案数据加载失败，请稍后重试" />
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
                                {formatDateTime(item.occurred_at) ?? '时间未知'}
                              </Typography>
                            </Box>
                          }
                          secondary={
                            item.description ? (
                              <Typography variant="body2" component="span" color="text.primary">
                                {item.description}
                              </Typography>
                            ) : undefined
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

import React from 'react';
import { Alert, Box, Button, CircularProgress, Paper, Stack, Typography } from '@mui/material';
import AssignmentTurnedInOutlinedIcon from '@mui/icons-material/AssignmentTurnedInOutlined';
import FactCheckOutlinedIcon from '@mui/icons-material/FactCheckOutlined';
import { Link } from 'react-router-dom';
import { useAsyncResource } from '../../hooks/useAsyncResource';
import { useSelector } from 'react-redux';
import type { RootState } from '../../store';
import dashboardService from '../../services/dashboardService';
import { formatAppDate } from '../../utils/dateTime';

const sourceMessage: Record<string, string> = {
  questionnaires_unavailable: '问卷任务暂时无法读取。',
  questionnaires_incomplete: '问卷任务较多，本次未能完整读取。',
  consents_unavailable: '知情同意文档暂时无法读取。',
};

function PatientTodos() {
  const load = React.useCallback(async (signal: AbortSignal) => {
    const data = await dashboardService.getTodoCenter(signal);
    if (!Array.isArray(data?.items) || !Array.isArray(data?.source_errors)) {
      throw new Error('待办列表格式无效');
    }
    return data;
  }, []);
  const { data, loading, error, reload } = useAsyncResource(load);

  return <Paper sx={{ p: { xs: 2, md: 3 }, maxWidth: 900, mx: 'auto' }}>
    <Stack spacing={2}>
      <Box>
        <Typography variant="h5" component="h1">待办中心</Typography>
        <Typography color="text.secondary" variant="body2" sx={{ mt: 0.5 }}>
          这里汇总当前需要你处理的问卷和知情同意文档。状态以各业务记录为准。
        </Typography>
      </Box>
      {loading && <Box role="status"><CircularProgress size={24} aria-label="正在加载待办事项" /></Box>}
      {!!error && <Alert severity="error" action={<Button onClick={reload}>重试</Button>}>待办事项加载失败，请稍后重试。</Alert>}
      {data?.source_errors.length ? <Alert severity="warning">
        {data.source_errors.map(code => sourceMessage[code] || '部分待办来源暂时不可用。').join(' ')} 当前列表可能不完整。
      </Alert> : null}
      {data?.items.length === 0 && data.source_errors.length === 0 && <Alert severity="info">目前没有待处理事项。</Alert>}
      {data?.items.map(item => {
        const Icon = item.type === 'questionnaire' ? AssignmentTurnedInOutlinedIcon : FactCheckOutlinedIcon;
        return <Box key={item.id} sx={{ border: 1, borderColor: 'divider', borderRadius: 1, p: 2 }}>
          <Stack direction="row" spacing={1.5} alignItems="flex-start">
            <Icon color="primary" />
            <Box sx={{ flex: 1, minWidth: 0 }}>
              <Typography fontWeight={600}>{item.title}</Typography>
              <Typography variant="body2" color="text.secondary">{item.description}</Typography>
              {item.created_at && <Typography variant="caption" color="text.secondary">
                创建时间：{formatAppDate(item.created_at, 'minute', { invalid: '时间无效' })}
              </Typography>}
            </Box>
            <Button component={Link} to={item.href} size="small" aria-label={`处理：${item.title}`}>去处理</Button>
          </Stack>
        </Box>;
      })}
    </Stack>
  </Paper>;
}

export default function TodoCenter() {
  const actor = useSelector((state: RootState) => state.auth.user);
  return actor ? <PatientTodos key={actor.id} /> : null;
}

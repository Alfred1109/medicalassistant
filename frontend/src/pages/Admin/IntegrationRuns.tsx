import React, { useCallback, useEffect, useState } from 'react';
import { Alert, Box, Button, Table, TableBody, TableCell, TableHead, TableRow, Typography } from '@mui/material';
import httpClient from '../../services/httpClient';

interface Run {
  id: string;
  kind: string;
  project_id: number;
  status: string;
  created?: number | null;
  existing?: number | null;
  error_code?: string | null;
  message?: string;
}

export default function IntegrationRuns() {
  const [runs, setRuns] = useState<Run[]>([]);
  const [summary, setSummary] = useState<Array<{ project_id: number; attempts: number; last_success: Run | null; last_failure: Run | null }>>([]);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    const [runsResult, summaryResult] = await Promise.all([
      httpClient.get('/integrations/forms/catalog/runs'),
      httpClient.get('/integrations/forms/catalog/runs/summary'),
    ]);
    setRuns(runsResult.data.runs || []);
    setSummary(summaryResult.data.projects || []);
  }, []);

  useEffect(() => { load().catch(() => setError('同步记录没有加载出来。')); }, [load]);

  return <Box>
    <Typography variant="h5" gutterBottom>同步记录</Typography>
    <Alert severity="info" sx={{ mb: 2 }}>这里只记录已经执行过的项目人员导入。失败的导入可以再执行一次；成功记录不能拿来重放。</Alert>
    {summary.map(item => <Typography key={item.project_id}>项目 {item.project_id}：共 {item.attempts} 次，最近成功 {item.last_success ? '有' : '无'}，最近失败 {item.last_failure?.error_code || '无'}</Typography>)}
    {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
    <Table size="small">
      <TableHead><TableRow>
        <TableCell>项目</TableCell><TableCell>状态</TableCell><TableCell>新增</TableCell><TableCell>已存在</TableCell><TableCell>错误</TableCell><TableCell></TableCell>
      </TableRow></TableHead>
      <TableBody>
        {runs.map(run => <TableRow key={run.id}>
          <TableCell>{run.project_id}</TableCell>
          <TableCell>{run.status === 'succeeded' ? '成功' : '失败'}</TableCell>
          <TableCell>{run.created ?? '—'}</TableCell>
          <TableCell>{run.existing ?? '—'}</TableCell>
          <TableCell>{run.error_code || run.message || '—'}</TableCell>
          <TableCell>{run.status === 'failed' && <Button size="small" onClick={async () => {
            setError('');
            try { await httpClient.post(`/integrations/forms/catalog/runs/${run.id}/retry`); await load(); }
            catch { setError('这次重试没有完成。来源目录可能仍不可用。'); }
          }}>重试</Button>}</TableCell>
        </TableRow>)}
        {runs.length === 0 && <TableRow><TableCell colSpan={6}>还没有导入记录。</TableCell></TableRow>}
      </TableBody>
    </Table>
  </Box>;
}

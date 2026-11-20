import { useCallback } from 'react';
import { Alert, Box, Button, CircularProgress, Stack, Typography } from '@mui/material';
import { useSelector } from 'react-redux';
import { Link } from 'react-router-dom';
import { useAsyncResource } from '../../hooks/useAsyncResource';
import httpClient from '../../services/httpClient';
import type { RootState } from '../../store';

interface ConsentRow { id: string; title: string; status: string }
const labels: Record<string, string> = { signed: '已签署', declined: '已拒绝', pending: '待签署' };

function DocumentList({ role }: { role: 'doctor' | 'patient' }) {
  const load = useCallback(async (signal: AbortSignal) => {
    const { data } = await httpClient.get<{ documents: ConsentRow[] }>('/consent/documents', { signal });
    if (!Array.isArray(data?.documents)) throw new Error('invalid document list');
    return data.documents;
  }, []);
  const { data, loading, error, reload } = useAsyncResource(load);
  return <Stack spacing={2}>
    <Typography variant="h5" component="h1">知情同意文档</Typography>
    {role === 'doctor' && <Box><Button component={Link} to="/app/doctor/informed-consent">发起知情同意</Button></Box>}
    {loading && <CircularProgress size={24} aria-label="正在加载文档" />}
    {!!error && <Alert severity="error" action={<Button onClick={reload}>重试</Button>}>无法读取知情同意文档。</Alert>}
    {data?.length === 0 && <Typography color="text.secondary">暂无知情同意文档。</Typography>}
    {data?.map(row => <Box key={row.id}>
      <Button component={Link} to={`/app/${role}/documents/${encodeURIComponent(row.id)}`}>
        {row.title}（{labels[row.status] || row.status}）
      </Button>
    </Box>)}
  </Stack>;
}

export default function ConsentDocumentList() {
  const actor = useSelector((state: RootState) => state.auth.user);
  if (actor?.role === 'doctor' || actor?.role === 'patient') {
    return <DocumentList key={`${actor.role}:${actor.id}`} role={actor.role} />;
  }
  return <Alert severity="info">当前角色没有知情同意文档的读取权限。</Alert>;
}

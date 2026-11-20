import { useCallback, useState } from 'react';
import { Alert, Box, Button, CircularProgress, Stack, TextField, Typography } from '@mui/material';
import { useSelector } from 'react-redux';
import { Link, useParams } from 'react-router-dom';
import { useAsyncResource } from '../../hooks/useAsyncResource';
import httpClient from '../../services/httpClient';
import type { RootState } from '../../store';

interface ConsentDocument {
  id: string;
  title: string;
  body: string;
  status: string;
  signed_name: string;
}
const labels: Record<string, string> = { signed: '已签署', declined: '已拒绝', pending: '待签署' };

function DocumentView({ id, role }: { id: string; role: 'doctor' | 'patient' }) {
  const [name, setName] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [submitted, setSubmitted] = useState<ConsentDocument | null>(null);
  const path = `/consent/documents/${encodeURIComponent(id)}`;
  const load = useCallback(async (signal: AbortSignal) => {
    const { data } = await httpClient.get<ConsentDocument>(path, { signal });
    if (data?.id !== id || typeof data.body !== 'string') throw new Error('invalid document payload');
    return data;
  }, [id, path]);
  const document = useAsyncResource(load, Boolean(id));
  const row = submitted ?? document.data;

  const respond = async (accepted: boolean) => {
    if (busy || role !== 'patient' || row?.status !== 'pending' || (accepted && !name.trim())) return;
    setBusy(true);
    setError('');
    try {
      const { data } = await httpClient.post<ConsentDocument>(`${path}/signature`, { signed_name: name.trim(), accepted });
      if (data?.id !== id || data.status !== (accepted ? 'signed' : 'declined')) {
        throw new Error('unconfirmed consent response');
      }
      setSubmitted(data);
    } catch {
      setError('回应结果未能确认。已重新读取文档，请核对状态后再操作。');
      document.reload();
    } finally {
      setBusy(false);
    }
  };

  const downloadText = async () => {
    setError('');
    try {
      const { data } = await httpClient.get<Blob>(`${path}/text`, { responseType: 'blob' });
      const url = URL.createObjectURL(data);
      try {
        const anchor = window.document.createElement('a');
        anchor.href = url;
        anchor.download = `${row?.title || '知情同意'}.txt`;
        anchor.click();
      } finally { setTimeout(() => URL.revokeObjectURL(url), 0); }
    } catch { setError('未能下载文本，请重试。'); }
  };

  return <Stack spacing={2}>
    <Box><Button component={Link} to={`/app/${role}/documents`}>返回文档列表</Button></Box>
    <Typography variant="h5" component="h1">{row?.title || '知情同意'}</Typography>
    {document.loading && <CircularProgress size={24} aria-label="正在读取文档" />}
    {!!document.error && <Alert severity="error" action={<Button onClick={document.reload}>重试</Button>}>无法读取该文档。</Alert>}
    {error && <Alert severity="error">{error}</Alert>}
    {row && <>
      <Typography sx={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{row.body}</Typography>
      <Typography>状态：{labels[row.status] ?? row.status}{row.signed_name ? ` · ${row.signed_name}` : ''}</Typography>
      {role === 'patient' && row.status === 'pending' && <>
        <TextField size="small" label="签署姓名" value={name} disabled={busy}
          onChange={event => setName(event.target.value)} sx={{ maxWidth: 360 }} />
        <Stack direction="row" spacing={2}>
          <Button variant="contained" disabled={busy || !name.trim()} onClick={() => void respond(true)}>签署</Button>
          <Button color="warning" disabled={busy} onClick={() => void respond(false)}>拒绝</Button>
        </Stack>
      </>}
      <Box><Button onClick={() => void downloadText()}>下载文本</Button></Box>
    </>}
  </Stack>;
}

export default function ConsentDocumentView() {
  const { documentId = '' } = useParams();
  const actor = useSelector((state: RootState) => state.auth.user);
  if (actor?.role === 'doctor' || actor?.role === 'patient') {
    return <DocumentView key={`${actor.role}:${actor.id}:${documentId}`} role={actor.role} id={documentId} />;
  }
  return <Alert severity="info">当前角色没有知情同意文档的读取权限。</Alert>;
}

import React, { useEffect, useState } from 'react';
import { Alert, Box, Button, TextField, Typography } from '@mui/material';
import { useParams } from 'react-router-dom';
import httpClient from '../../services/httpClient';

const ConsentDocumentView: React.FC = () => {
  const { documentId = '' } = useParams();
  const [title, setTitle] = useState('');
  const [body, setBody] = useState('');
  const [status, setStatus] = useState('');
  const [signedName, setSignedName] = useState('');
  const [error, setError] = useState('');

  const load = () => httpClient.get(`/consent/documents/${documentId}`).then(({ data }) => {
    setTitle(data.title); setBody(data.body); setStatus(data.status); setSignedName(data.signed_name || '');
  }).catch(() => setError('这份知情同意没有打开。'));

  useEffect(() => { if (documentId) load(); }, [documentId]);

  return <Box>
    <Typography variant="h5" gutterBottom>{title || '知情同意'}</Typography>
    {error && <Alert severity="error">{error}</Alert>}
    <Typography sx={{ whiteSpace: 'pre-wrap', my: 2 }}>{body}</Typography>
    <Typography>状态：{status === 'signed' ? '已签署' : status === 'declined' ? '已拒绝' : '待签署'}</Typography>
    {status === 'pending' && <>
      <TextField size="small" label="签署姓名" value={signedName} onChange={event => setSignedName(event.target.value)} sx={{ my: 2 }} />
      <Box>
        <Button variant="contained" onClick={async () => { await httpClient.post(`/consent/documents/${documentId}/signature`, { signed_name: signedName, accepted: true }); await load(); }}>签署</Button>
        <Button color="warning" onClick={async () => { await httpClient.post(`/consent/documents/${documentId}/signature`, { signed_name: signedName, accepted: false }); await load(); }}>拒绝</Button>
      </Box>
    </>}
    <Button sx={{ mt: 2 }} onClick={async () => {
      const { data } = await httpClient.get(`/consent/documents/${documentId}/text`, { responseType: 'blob' });
      window.open(URL.createObjectURL(data), '_blank');
    }}>查看文本</Button>
  </Box>;
};

export default ConsentDocumentView;

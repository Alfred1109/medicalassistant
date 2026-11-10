import React, { useEffect, useState } from 'react';
import { Alert, Box, Button, Typography } from '@mui/material';
import { Link } from 'react-router-dom';
import httpClient from '../../services/httpClient';

interface ConsentRow { id: string; title: string; status: string }

const ConsentDocumentList: React.FC = () => {
  const [rows, setRows] = useState<ConsentRow[]>([]);
  const [error, setError] = useState('');
  useEffect(() => {
    httpClient.get('/consent/documents').then(({ data }) => setRows(data.documents || [])).catch(() => setError('知情同意没有加载出来。'));
  }, []);
  return <Box>
    <Typography variant="h5" gutterBottom>知情同意文档</Typography>
    {error && <Alert severity="error">{error}</Alert>}
    {rows.length === 0 && !error && <Typography color="text.secondary">还没有发给你的知情同意。</Typography>}
    {rows.map(row => <Box key={row.id} sx={{ my: 1 }}>
      <Button component={Link} to={`/app/patient/documents/${row.id}`}>{row.title}（{row.status === 'signed' ? '已签署' : row.status === 'declined' ? '已拒绝' : '待签署'}）</Button>
    </Box>)}
  </Box>;
};

export default ConsentDocumentList;

import React, { useEffect, useState } from 'react';
import { Alert, Box, Typography } from '@mui/material';
import httpClient from '../../services/httpClient';

const ConsentTemplateList: React.FC = () => {
  const [rows, setRows] = useState<Array<{ id: string; title: string }>>([]);
  const [error, setError] = useState('');
  useEffect(() => {
    httpClient.get('/consent/templates').then(({ data }) => setRows(data.templates || [])).catch(() => setError('模板没有加载出来。'));
  }, []);
  return <Box>
    <Typography variant="h5" gutterBottom>知情同意模板</Typography>
    <Alert severity="info" sx={{ my: 2 }}>这里只显示已经保存的模板。模板由医生或管理员编写，页面不会预置法律文本。</Alert>
    {error && <Alert severity="error">{error}</Alert>}
    {rows.length === 0 && !error && <Typography color="text.secondary">还没有模板。</Typography>}
    {rows.map(row => <Typography key={row.id}>{row.title}</Typography>)}
  </Box>;
};

export default ConsentTemplateList;

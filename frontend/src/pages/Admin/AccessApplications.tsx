import React, { useCallback, useEffect, useState } from 'react';
import { Alert, Box, Button, Paper, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, TextField, Typography } from '@mui/material';
import httpClient from '../../services/httpClient';

interface AccessApplication {
  id: string;
  requested_role: string;
  note: string;
  status: string;
  local_user_id?: string | null;
  reason?: string | null;
}

const ROLE_LABEL: Record<string, string> = {
  patient: '患者',
  doctor: '医生',
  health_manager: '健管师',
};

const AccessApplications: React.FC = () => {
  const [rows, setRows] = useState<AccessApplication[]>([]);
  const [error, setError] = useState('');
  const [localUserId, setLocalUserId] = useState<Record<string, string>>({});
  const [evidence, setEvidence] = useState<Record<string, string>>({});
  const [reason, setReason] = useState<Record<string, string>>({});

  const load = useCallback(async () => {
    const { data } = await httpClient.get('/auth/access-applications', { params: { status: 'pending' } });
    setRows(data.applications || []);
  }, []);

  useEffect(() => {
    load().catch(() => setError('暂时无法读取接入申请。'));
  }, [load]);

  const decide = async (row: AccessApplication, approved: boolean) => {
    setError('');
    try {
      await httpClient.post(`/auth/access-applications/${row.id}/decision`, {
        approved,
        local_user_id: approved ? (localUserId[row.id] || '').trim() : '',
        evidence_reference: approved ? (evidence[row.id] || '').trim() : '',
        reason: approved ? '' : (reason[row.id] || '').trim(),
      });
      await load();
    } catch {
      setError(approved
        ? '未能通过。请确认本地人员已经存在，角色与申请一致，并且填写了核实依据。'
        : '未能拒绝。请填写拒绝原因。');
    }
  };

  return <Box>
    <Typography variant="h5" gutterBottom>接入申请</Typography>
    <Alert severity="info" sx={{ mb: 2 }}>
      申请人已经用问卷系统账号完成登录。通过后，这个登录会关联到一名已有本地人员，角色以该人员当前角色为准。未指定角色的导入人员需要先在「患者与问卷来源」里指定角色。
    </Alert>
    {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
    <TableContainer component={Paper}>
      <Table size="small">
        <TableHead>
          <TableRow>
            <TableCell>申请角色</TableCell>
            <TableCell>说明</TableCell>
            <TableCell>本地人员编号</TableCell>
            <TableCell>核实依据或拒绝原因</TableCell>
            <TableCell>处理</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {rows.map(row => <TableRow key={row.id}>
            <TableCell>{ROLE_LABEL[row.requested_role] || row.requested_role}</TableCell>
            <TableCell>{row.note || '—'}</TableCell>
            <TableCell>
              <TextField size="small" value={localUserId[row.id] || ''} placeholder="从项目人员表复制"
                onChange={event => setLocalUserId(current => ({ ...current, [row.id]: event.target.value }))} />
            </TableCell>
            <TableCell>
              <TextField size="small" sx={{ mr: 1 }} value={evidence[row.id] || ''} placeholder="通过时的核实依据"
                onChange={event => setEvidence(current => ({ ...current, [row.id]: event.target.value }))} />
              <TextField size="small" value={reason[row.id] || ''} placeholder="拒绝原因"
                onChange={event => setReason(current => ({ ...current, [row.id]: event.target.value }))} />
            </TableCell>
            <TableCell>
              <Button size="small" variant="contained" onClick={() => decide(row, true)}>通过</Button>
              <Button size="small" color="warning" onClick={() => decide(row, false)}>拒绝</Button>
            </TableCell>
          </TableRow>)}
          {rows.length === 0 && <TableRow><TableCell colSpan={5}>目前没有待审核的接入申请。</TableCell></TableRow>}
        </TableBody>
      </Table>
    </TableContainer>
  </Box>;
};

export default AccessApplications;

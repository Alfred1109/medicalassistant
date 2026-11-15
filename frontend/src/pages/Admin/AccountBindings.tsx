import React, { useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Chip,
  Divider,
  Grid,
  Paper,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import {
  AccountBinding,
  AccountBindingCreatePayload,
  AccountBindingDisablePayload,
  accountBindingErrorCopy,
  patientAccountBindingService,
} from '../../services/patientAccountBindings';

// T77 显式账号绑定管理（admin-only）。
// 消费后端 T64 端点（POST /api/patients/account-bindings 与
// POST /api/patients/account-bindings/{patient_id}/disable）。
// 探查结论：后端只有创建/停用两个写端点，没有列表/查询端点——链接状态
// 只能在操作后由响应回显；因此本页不做“按患者/账号查询”的检索面板，
// 如实告知能力边界，避免硬造假查询。
// 与「患者与问卷来源」（/app/admin/patient-links，113.44 外部问卷关联）
// 语义不同：本页管理的是临床患者 ↔ 登录账号的显式绑定。

const dateText = (value?: string | null) => {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString('zh-CN', { hour12: false });
};

const STATUS_COLOR = (status?: string): 'success' | 'default' =>
  status === 'verified' ? 'success' : 'default';

function BindingResultCard({ result, title }: { result: AccountBinding | null; title: string }) {
  if (!result) return null;
  return (
    <Paper variant="outlined" sx={{ p: 2 }}>
      <Typography variant="subtitle2" gutterBottom>
        {title}结果（后端响应回显）
      </Typography>
      <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }}>
        <Chip size="small" color={STATUS_COLOR(result.status)} label={result.status || '未知状态'} />
        <Typography variant="caption" color="text.secondary">origin：{result.source}</Typography>
      </Stack>
      <Typography variant="body2">患者：{result.patient_id}</Typography>
      <Typography variant="body2">账号：{result.account_id}</Typography>
      <Typography variant="body2">审核人：{result.reviewer || '—'} · 凭证：{result.evidence_reference || '—'}</Typography>
      <Typography variant="body2">绑定时间：{dateText(result.bound_at)} · 停用时间：{dateText(result.disabled_at)}</Typography>
    </Paper>
  );
}

const AccountBindings: React.FC = () => {
  // 创建绑定表单
  const [createPatientId, setCreatePatientId] = useState('');
  const [createAccountId, setCreateAccountId] = useState('');
  const [createReviewer, setCreateReviewer] = useState('');
  const [createEvidence, setCreateEvidence] = useState('');
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState('');
  const [createResult, setCreateResult] = useState<AccountBinding | null>(null);

  // 停用绑定表单
  const [disablePatientId, setDisablePatientId] = useState('');
  const [disableReviewer, setDisableReviewer] = useState('');
  const [disableEvidence, setDisableEvidence] = useState('');
  const [disabling, setDisabling] = useState(false);
  const [disableError, setDisableError] = useState('');
  const [disableResult, setDisableResult] = useState<AccountBinding | null>(null);

  const submitCreate = async () => {
    if (!createPatientId.trim() || !createAccountId.trim() || !createReviewer.trim() || !createEvidence.trim()) {
      setCreateError('患者 ID、账号 ID、审核人与凭证引用均为必填（后端审计要求）。');
      return;
    }
    const payload: AccountBindingCreatePayload = {
      patient_id: createPatientId.trim(),
      account_id: createAccountId.trim(),
      reviewer: createReviewer.trim(),
      evidence_reference: createEvidence.trim(),
    };
    setCreating(true); setCreateError(''); setCreateResult(null);
    try {
      const result = await patientAccountBindingService.createBinding(payload);
      setCreateResult(result);
    } catch (failure) {
      setCreateError(accountBindingErrorCopy(failure));
    } finally {
      setCreating(false);
    }
  };

  const submitDisable = async () => {
    if (!disablePatientId.trim() || !disableReviewer.trim() || !disableEvidence.trim()) {
      setDisableError('患者 ID、审核人与凭证引用均为必填（后端审计要求）。');
      return;
    }
    const payload: AccountBindingDisablePayload = {
      reviewer: disableReviewer.trim(),
      evidence_reference: disableEvidence.trim(),
    };
    setDisabling(true); setDisableError(''); setDisableResult(null);
    try {
      const result = await patientAccountBindingService.disableBinding(disablePatientId.trim(), payload);
      setDisableResult(result);
    } catch (failure) {
      setDisableError(accountBindingErrorCopy(failure));
    } finally {
      setDisabling(false);
    }
  };

  return (
    <Box>
      <Typography variant="h5" component="h1" gutterBottom>账号绑定管理</Typography>
      <Typography color="text.secondary" sx={{ mb: 2 }}>
        为「无账号临床患者」人工核实后绑定登录账号；患者以该账号登录后即可使用自助通路。
      </Typography>
      <Alert severity="info" sx={{ mb: 2 }}>
        后端当前仅提供创建与停用两个 admin-only 端点，没有绑定关系查询端点——操作结果由响应回显，请在执行前核对患者与账号 ID。
        绑定互斥：患者或账号已有任意来源的链接（含已停用）时创建会返回 409，系统不做隐式替换；停用为终态，重新绑定需重新人工核实对账。
        本页与「患者与问卷来源」不同：那里管理的是问卷平台的外部关联，这里管理的是临床患者与本系统登录账号的显式绑定。
      </Alert>

      <Grid container spacing={3}>
        <Grid item xs={12} md={6}>
          <Paper variant="outlined" sx={{ p: { xs: 2, md: 3 }, height: '100%' }}>
            <Typography variant="h6" gutterBottom>创建绑定</Typography>
            <Stack spacing={2}>
              <TextField
                label="患者 ID（clinical patient）" required value={createPatientId}
                onChange={(event) => setCreatePatientId(event.target.value)}
              />
              <TextField
                label="登录账号 ID（24 位）" required value={createAccountId}
                inputProps={{ maxLength: 24 }}
                helperText="账号侧 ObjectId，长度固定 24 位"
                onChange={(event) => setCreateAccountId(event.target.value)}
              />
              <TextField
                label="审核人（人工核实人）" required value={createReviewer}
                inputProps={{ maxLength: 200 }}
                onChange={(event) => setCreateReviewer(event.target.value)}
              />
              <TextField
                label="凭证引用（对账材料编号等）" required value={createEvidence}
                inputProps={{ maxLength: 1024 }}
                onChange={(event) => setCreateEvidence(event.target.value)}
              />
              {createError && <Alert severity="error">{createError}</Alert>}
              <Box>
                <Button variant="contained" disabled={creating} onClick={submitCreate}>
                  {creating ? '提交中…' : '创建绑定'}
                </Button>
              </Box>
              <Divider />
              <BindingResultCard result={createResult} title="创建" />
            </Stack>
          </Paper>
        </Grid>

        <Grid item xs={12} md={6}>
          <Paper variant="outlined" sx={{ p: { xs: 2, md: 3 }, height: '100%' }}>
            <Typography variant="h6" gutterBottom>停用绑定</Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
              按患者停用其显式账号链接（verified → disabled）；不删除历史，也不可复活。
            </Typography>
            <Stack spacing={2}>
              <TextField
                label="患者 ID" required value={disablePatientId}
                onChange={(event) => setDisablePatientId(event.target.value)}
              />
              <TextField
                label="审核人（停用操作人）" required value={disableReviewer}
                inputProps={{ maxLength: 200 }}
                onChange={(event) => setDisableReviewer(event.target.value)}
              />
              <TextField
                label="凭证引用（停用依据）" required value={disableEvidence}
                inputProps={{ maxLength: 1024 }}
                onChange={(event) => setDisableEvidence(event.target.value)}
              />
              {disableError && <Alert severity="error">{disableError}</Alert>}
              <Box>
                <Button color="error" variant="contained" disabled={disabling} onClick={submitDisable}>
                  {disabling ? '提交中…' : '停用绑定'}
                </Button>
              </Box>
              <Divider />
              <BindingResultCard result={disableResult} title="停用" />
            </Stack>
          </Paper>
        </Grid>
      </Grid>
    </Box>
  );
};

export default AccountBindings;

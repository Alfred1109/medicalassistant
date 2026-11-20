import React from 'react';
import {
  Alert, Box, Button, Chip, CircularProgress, Dialog, DialogActions, DialogContent, DialogTitle,
  IconButton, InputAdornment, MenuItem, Paper, Stack, Table, TableBody, TableCell, TableContainer,
  TableHead, TableRow, TextField, Typography,
} from '@mui/material';
import SearchIcon from '@mui/icons-material/Search';
import VisibilityIcon from '@mui/icons-material/Visibility';
import DownloadIcon from '@mui/icons-material/Download';
import AddIcon from '@mui/icons-material/Add';
import api from '../../services/api';

interface PatientOption { id: string; name: string }
interface ConsentTemplate { id: string; title: string; body: string }
interface ConsentDocument {
  id: string; patient_id: string; patient_name: string; title: string; body?: string;
  status: 'pending' | 'signed' | 'declined'; signed_name: string; signed_at?: string | null;
}
const statusLabels: Record<ConsentDocument['status'], string> = {
  pending: '待患者回应', signed: '已同意', declined: '已拒绝',
};
function errorMessage(error: any, fallback: string): string {
  const detail = error?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  const messages: Record<string, string> = {
    PATIENT_NOT_ASSIGNED: '该患者当前不在你的管理范围内，请刷新患者列表。',
    PATIENT_NOT_FOUND: '患者档案不存在或当前不可用。',
    INVALID_TEMPLATE: '请填写标题和正文，正文不能超过 20000 个字符。',
    TEMPLATE_NOT_FOUND: '所选模板已不可用，请刷新后重新选择。',
  };
  return messages[detail?.code] || fallback;
}

const InformedConsent: React.FC = () => {
  const [documents, setDocuments] = React.useState<ConsentDocument[]>([]);
  const [templates, setTemplates] = React.useState<ConsentTemplate[]>([]);
  const [patients, setPatients] = React.useState<PatientOption[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [saving, setSaving] = React.useState(false);
  const [error, setError] = React.useState('');
  const [notice, setNotice] = React.useState('');
  const [search, setSearch] = React.useState('');
  const [templateTitle, setTemplateTitle] = React.useState('');
  const [templateBody, setTemplateBody] = React.useState('');
  const [selectedTemplate, setSelectedTemplate] = React.useState('');
  const [selectedPatient, setSelectedPatient] = React.useState('');
  const [selectedDocument, setSelectedDocument] = React.useState<ConsentDocument | null>(null);
  const [documentLoading, setDocumentLoading] = React.useState(false);

  const load = React.useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [documentResponse, templateResponse, patientResponse] = await Promise.all([
        api.get('/doctors/informed-consents'), api.get('/consent/templates'), api.get('/doctors/patients'),
      ]);
      if (!Array.isArray(documentResponse.data) || !Array.isArray(templateResponse.data?.templates) ||
          !Array.isArray(patientResponse.data)) throw new Error('知情同意接口返回的数据格式异常，请刷新重试。');
      setDocuments(documentResponse.data);
      setTemplates(templateResponse.data.templates);
      setPatients(patientResponse.data.filter((row: any) =>
        typeof row?.id === 'string' && typeof row?.name === 'string'));
    } catch (failure) {
      setError(errorMessage(failure, '加载知情同意、模板或授权患者失败。'));
    } finally { setLoading(false); }
  }, []);
  React.useEffect(() => { void load(); }, [load]);

  const filtered = documents.filter((document) => {
    const keyword = search.trim().toLocaleLowerCase();
    return !keyword || [document.patient_name, document.patient_id, document.title, statusLabels[document.status]]
      .some((value) => value?.toLocaleLowerCase().includes(keyword));
  });

  const createTemplate = async () => {
    setSaving(true); setError(''); setNotice('');
    try {
      const { data } = await api.post('/consent/templates', { title: templateTitle.trim(), body: templateBody.trim() });
      if (!data?.id) throw new Error('模板保存结果未确认，请刷新检查。');
      setTemplateTitle(''); setTemplateBody('');
      await load(); setSelectedTemplate(data.id); setNotice('同意书模板已保存。');
    } catch (failure) { setError(errorMessage(failure, '保存模板失败，请检查内容后重试。')); }
    finally { setSaving(false); }
  };

  const issueDocument = async () => {
    setSaving(true); setError(''); setNotice('');
    try {
      const { data } = await api.post('/consent/documents', { template_id: selectedTemplate, patient_id: selectedPatient });
      if (!data?.id) throw new Error('发出结果未确认，请刷新检查列表。');
      setSelectedPatient(''); await load(); setNotice('知情同意已发给患者。');
    } catch (failure) { setError(errorMessage(failure, '发出知情同意失败，请检查患者和模板后重试。')); }
    finally { setSaving(false); }
  };

  const openDocument = async (document: ConsentDocument) => {
    setDocumentLoading(true); setError('');
    try {
      const { data } = await api.get(`/consent/documents/${encodeURIComponent(document.id)}`);
      if (data?.id !== document.id || typeof data.body !== 'string') throw new Error('invalid document');
      setSelectedDocument({ ...document, ...data });
    } catch (failure) { setError(errorMessage(failure, '无法读取这份知情同意。')); }
    finally { setDocumentLoading(false); }
  };

  const downloadDocument = async (document: ConsentDocument) => {
    setError('');
    try {
      const { data } = await api.get(`/consent/documents/${encodeURIComponent(document.id)}/text`, { responseType: 'blob' });
      const url = URL.createObjectURL(data);
      const anchor = window.document.createElement('a');
      anchor.href = url; anchor.download = `${document.title}.txt`; anchor.click(); URL.revokeObjectURL(url);
    } catch (failure) { setError(errorMessage(failure, '下载知情同意失败。')); }
  };

  const patientNames = new Map(patients.map((patient) => [patient.id, patient.name]));
  return <Box>
    <Typography variant="h5" component="h1" gutterBottom>知情同意书管理</Typography>
    <Typography color="text.secondary" sx={{ mb: 3 }}>
      使用医护编写的模板发起知情同意。患者可在网页或小程序查看正文并回应。
    </Typography>
    {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
    {notice && <Alert severity="success" sx={{ mb: 2 }}>{notice}</Alert>}
    <Stack spacing={2} sx={{ mb: 3 }}>
      <Paper variant="outlined" sx={{ p: 2 }}><Stack spacing={1.5}>
        <Typography variant="h6">新建模板</Typography>
        <TextField label="模板标题" value={templateTitle} disabled={saving} inputProps={{ maxLength: 120 }}
          onChange={(event) => setTemplateTitle(event.target.value)} />
        <TextField label="同意书正文" value={templateBody} disabled={saving} multiline minRows={5}
          inputProps={{ maxLength: 20000 }} onChange={(event) => setTemplateBody(event.target.value)} />
        <Box><Button startIcon={<AddIcon />} variant="outlined" disabled={saving || !templateTitle.trim() || !templateBody.trim()}
          onClick={() => void createTemplate()}>保存模板</Button></Box>
      </Stack></Paper>
      <Paper variant="outlined" sx={{ p: 2 }}><Stack spacing={1.5}>
        <Typography variant="h6">发给患者</Typography>
        {loading ? <CircularProgress size={22} /> : <>
          <TextField select label="选择模板" value={selectedTemplate} onChange={(event) => setSelectedTemplate(event.target.value)}>
            {templates.map((template) => <MenuItem key={template.id} value={template.id}>{template.title}</MenuItem>)}
          </TextField>
          <TextField select label="选择已授权患者" value={selectedPatient} onChange={(event) => setSelectedPatient(event.target.value)}>
            {patients.map((patient) => <MenuItem key={patient.id} value={patient.id}>{patient.name}</MenuItem>)}
          </TextField>
          <Box><Button variant="contained" disabled={saving || !selectedTemplate || !selectedPatient}
            onClick={() => void issueDocument()}>发出知情同意</Button></Box>
          {!templates.length && <Typography color="text.secondary">先创建一份模板。</Typography>}
          {!patients.length && <Typography color="text.secondary">当前没有已分配给你的患者。</Typography>}
        </>}
      </Stack></Paper>
    </Stack>
    <Stack direction="row" spacing={1} sx={{ mb: 2 }}>
      <TextField placeholder="搜索患者、同意书或状态" size="small" value={search} onChange={(event) => setSearch(event.target.value)}
        InputProps={{ startAdornment: <InputAdornment position="start"><SearchIcon /></InputAdornment> }} />
      <Button variant="outlined" disabled={loading} onClick={() => void load()}>刷新</Button>
    </Stack>
    <TableContainer component={Paper} variant="outlined"><Table>
      <TableHead><TableRow>
        <TableCell>患者</TableCell><TableCell>患者编号</TableCell><TableCell>同意书</TableCell>
        <TableCell>签署/回应时间</TableCell><TableCell>状态</TableCell><TableCell>签署姓名</TableCell><TableCell align="right">操作</TableCell>
      </TableRow></TableHead>
      <TableBody>
        {loading ? <TableRow><TableCell colSpan={7} align="center"><CircularProgress size={22} /></TableCell></TableRow>
          : filtered.length === 0 ? <TableRow><TableCell colSpan={7} align="center">
            {search ? '没有匹配的知情同意。' : '暂无知情同意记录。'}
          </TableCell></TableRow>
          : filtered.map((document) => <TableRow key={document.id}>
            <TableCell>{document.patient_name || patientNames.get(document.patient_id) || '患者'}</TableCell>
            <TableCell>{document.patient_id}</TableCell><TableCell>{document.title}</TableCell>
            <TableCell>{document.signed_at ? new Date(document.signed_at).toLocaleString() : '—'}</TableCell>
            <TableCell><Chip size="small" label={statusLabels[document.status] || '状态未知'}
              color={document.status === 'signed' ? 'success' : document.status === 'declined' ? 'error' : 'warning'} /></TableCell>
            <TableCell>{document.signed_name || '—'}</TableCell><TableCell align="right">
              <IconButton aria-label="查看同意书" disabled={documentLoading} onClick={() => void openDocument(document)}><VisibilityIcon /></IconButton>
              <IconButton aria-label="下载同意书" onClick={() => void downloadDocument(document)}><DownloadIcon /></IconButton>
            </TableCell>
          </TableRow>)}
      </TableBody>
    </Table></TableContainer>
    <Dialog open={!!selectedDocument} onClose={() => setSelectedDocument(null)} maxWidth="md" fullWidth>
      <DialogTitle>{selectedDocument?.title || '知情同意'}</DialogTitle>
      <DialogContent dividers>
        {documentLoading ? <CircularProgress /> : selectedDocument && <Stack spacing={2}>
          <Typography color="text.secondary">患者：{selectedDocument.patient_name ||
            patientNames.get(selectedDocument.patient_id) || selectedDocument.patient_id}
            {' · '}{statusLabels[selectedDocument.status] || '状态未知'}</Typography>
          <Typography sx={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{selectedDocument.body}</Typography>
          {selectedDocument.signed_name && <Typography>签署姓名：{selectedDocument.signed_name}</Typography>}
        </Stack>}
      </DialogContent>
      <DialogActions><Button onClick={() => setSelectedDocument(null)}>关闭</Button></DialogActions>
    </Dialog>
  </Box>;
};
export default InformedConsent;

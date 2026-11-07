import React, { useEffect, useState } from 'react';
import { Alert, Box, Button, Card, CardContent, CircularProgress, Divider, Grid, IconButton,
  List, ListItem, ListItemText, Paper, TextField, Typography } from '@mui/material';
import { AdapterDateFns } from '@mui/x-date-pickers/AdapterDateFns';
import { LocalizationProvider } from '@mui/x-date-pickers/LocalizationProvider';
import { DatePicker } from '@mui/x-date-pickers/DatePicker';
import AddIcon from '@mui/icons-material/Add';
import DeleteIcon from '@mui/icons-material/Delete';
import EditIcon from '@mui/icons-material/Edit';
import { apiService } from '../../services/api';

interface DailyRecord {
  id: string;
  date: string;
  pain_level?: number;
  mood?: string;
  sleep?: string;
  exercise_completed?: boolean;
  note?: string;
}
interface RecordForm {
  date: Date | null;
  painLevel: string;
  mood: string;
  sleep: string;
  exerciseCompleted: boolean;
  note: string;
}
const freshForm = (): RecordForm => ({ date: new Date(), painLevel: '0', mood: '', sleep: '', exerciseCompleted: false, note: '' });
const validDate = (date: Date | null): date is Date => date !== null && Number.isFinite(date.getTime());
const dayKey = (date: Date) => `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
// Calendar dates stay local; legacy timestamps retain their original local display behavior.
const recordDate = (value: string): Date | null => {
  const parsed = /^\d{4}-\d{2}-\d{2}$/.test(value) ? new Date(`${value}T00:00:00`) : new Date(value);
  return validDate(parsed) ? parsed : null;
};
const parseRecord = (value: unknown): DailyRecord => {
  if (typeof value !== 'object' || value === null) throw new Error('记录响应格式无效');
  const row = value as Record<string, unknown>;
  const id = row.id ?? row._id;
  if (typeof id !== 'string' || !id || typeof row.date !== 'string') throw new Error('记录缺少真实ID或日期');
  for (const field of ['mood', 'sleep', 'note']) {
    if (row[field] != null && typeof row[field] !== 'string') throw new Error('记录文本格式无效');
  }
  if (row.pain_level != null && (typeof row.pain_level !== 'number' || !Number.isFinite(row.pain_level))) throw new Error('疼痛数据格式无效');
  if (row.exercise_completed != null && typeof row.exercise_completed !== 'boolean') throw new Error('训练数据格式无效');
  return { id, date: row.date, pain_level: (row.pain_level ?? undefined) as number | undefined,
    mood: (row.mood ?? undefined) as string | undefined, sleep: (row.sleep ?? undefined) as string | undefined,
    exercise_completed: (row.exercise_completed ?? undefined) as boolean | undefined, note: (row.note ?? undefined) as string | undefined };
};

const DailyRecords: React.FC = () => {
  const [selectedDate, setSelectedDate] = useState<Date | null>(new Date());
  const [records, setRecords] = useState<DailyRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [loaded, setLoaded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState<RecordForm>(freshForm);
  const [isAdding, setIsAdding] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);

  const fetchRecords = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await apiService.patient.getDailyRecords();
      const data: unknown = response.data;
      if (!Array.isArray(data)) throw new Error('记录响应格式无效');
      setRecords(data.map(parseRecord));
      setLoaded(true);
    } catch {
      setLoaded(false);
      setError('获取日常记录失败，请重试；当前无法确认记录情况。');
    } finally { setLoading(false); }
  };
  useEffect(() => { void fetchRecords(); }, []);

  const openForm = (record?: DailyRecord) => {
    setEditingId(record?.id ?? null);
    setForm(record ? { date: recordDate(record.date), painLevel: record.pain_level?.toString() ?? '',
      mood: record.mood ?? '', sleep: record.sleep ?? '', exerciseCompleted: record.exercise_completed ?? false,
      note: record.note ?? '' } : freshForm());
    setIsAdding(true);
    setError(null);
  };
  const pain = Number(form.painLevel);
  const formValid = validDate(form.date) && form.painLevel.trim() !== '' && Number.isInteger(pain) && pain >= 0 && pain <= 10
    && !!form.mood.trim() && !!form.sleep.trim() && !!form.note.trim();
  const handleSaveRecord = async () => {
    if (!formValid || !validDate(form.date) || busy) return;
    setBusy(true);
    setError(null);
    try {
      const data = { date: dayKey(form.date), pain_level: pain, mood: form.mood, sleep: form.sleep,
        exercise_completed: form.exerciseCompleted, note: form.note };
      const response = editingId
        ? await apiService.patient.updateDailyRecord(editingId, data)
        : await apiService.patient.createDailyRecord(data);
      const saved = parseRecord(response.data);
      if (editingId && saved.id !== editingId) throw new Error('响应ID不匹配');
      setRecords(previous => [...previous.filter(record => record.id !== saved.id), saved]
        .sort((left, right) => right.date.localeCompare(left.date)));
      setSelectedDate(form.date);
      setIsAdding(false);
      setEditingId(null);
      setForm(freshForm());
    } catch { setError('保存记录失败，尚未确认保存成功，请保留内容并重试。'); }
    finally { setBusy(false); }
  };
  const handleDeleteRecord = async (id: string) => {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const response = await apiService.patient.deleteDailyRecord(id);
      if (response.status !== 204) throw new Error('删除未确认');
      setRecords(previous => previous.filter(record => record.id !== id));
      if (editingId === id) { setIsAdding(false); setEditingId(null); }
    } catch { setError('删除记录失败，尚未确认删除成功，请重试。'); }
    finally { setBusy(false); }
  };
  const filterValid = selectedDate === null || validDate(selectedDate);
  const filteredRecords = filterValid ? records.filter(record => {
    if (selectedDate === null) return true;
    const date = recordDate(record.date);
    return date !== null && dayKey(date) === dayKey(selectedDate);
  }) : [];
  const today = new Date();
  const monthDays = new Set(records.flatMap(record => {
    const date = recordDate(record.date);
    return date && date.getFullYear() === today.getFullYear() && date.getMonth() === today.getMonth() ? [dayKey(date)] : [];
  }));
  const recordedDays = new Set(records.flatMap(record => {
    const date = recordDate(record.date);
    return date ? [dayKey(date)] : [];
  }));
  const streakDate = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  if (!recordedDays.has(dayKey(streakDate))) streakDate.setDate(streakDate.getDate() - 1);
  let streak = 0;
  while (recordedDays.has(dayKey(streakDate))) {
    streak += 1;
    streakDate.setDate(streakDate.getDate() - 1);
  }
  const trainingDays = new Set(records.flatMap(record => {
    const date = recordDate(record.date);
    return date && record.exercise_completed === true ? [dayKey(date)] : [];
  }));

  return <LocalizationProvider dateAdapter={AdapterDateFns}>
    <Box>
      <Typography variant="h5" component="h1" gutterBottom>日常康复记录</Typography>
      {error && <Alert severity="error" sx={{ mb: 3 }}>{error}</Alert>}
      <Grid container spacing={3}>
        <Grid item xs={12} md={8}>
          <Paper sx={{ p: 3, mb: 3 }}>
            <Box display="flex" alignItems="center" gap={2} mb={2} flexWrap="wrap">
              <Typography variant="h6">我的记录</Typography>
              <DatePicker<Date> label="选择日期" value={selectedDate} onChange={setSelectedDate}
                slotProps={{ textField: { error: !filterValid, helperText: !filterValid ? '日期无效' : undefined } }} />
              <Button onClick={() => setSelectedDate(null)}>全部记录</Button>
              <Button variant="contained" startIcon={<AddIcon />} onClick={() => openForm()} disabled={busy || !loaded}>添加记录</Button>
              <Button onClick={() => void fetchRecords()} disabled={busy || loading}>刷新记录</Button>
            </Box>
            {loading ? <Box display="flex" alignItems="center" gap={2}><CircularProgress /><Typography>加载日常记录...</Typography></Box>
              : !loaded ? <Typography>记录未加载，请刷新重试。</Typography>
              : !filterValid ? <Typography>请选择有效日期。</Typography>
              : filteredRecords.length === 0 ? <Typography>{selectedDate ? '该日期没有记录' : '暂无日常记录'}</Typography>
              : <List>{filteredRecords.map(record => <React.Fragment key={record.id}>
                <ListItem secondaryAction={<Box>
                  <IconButton aria-label="编辑记录" onClick={() => openForm(record)} disabled={busy}><EditIcon /></IconButton>
                  <IconButton aria-label="删除记录" onClick={() => void handleDeleteRecord(record.id)} disabled={busy}><DeleteIcon /></IconButton>
                </Box>}>
                  <ListItemText secondaryTypographyProps={{ component: 'div' }}
                    primary={`${recordDate(record.date)?.toLocaleDateString() ?? `日期无效（${record.date}）`} 记录`}
                    secondary={<Box>
                      <Typography component="span" variant="body2">疼痛程度: {record.pain_level === undefined ? '未记录' : `${record.pain_level}/10`} | 心情: {record.mood ?? '未记录'} | 睡眠: {record.sleep ?? '未记录'} | 完成训练: {record.exercise_completed === undefined ? '未记录' : record.exercise_completed ? '是' : '否'}</Typography>
                      <Typography component="p" variant="body2" sx={{ mt: 1 }}>{record.note ?? '未记录备注'}</Typography>
                    </Box>} />
                </ListItem><Divider />
              </React.Fragment>)}</List>}
          </Paper>
        </Grid>
        <Grid item xs={12} md={4}><Card><CardContent>
          <Typography variant="h6" gutterBottom>记录情况</Typography>
          <Typography variant="body2">本月已记录: {loaded ? `${monthDays.size} 天` : '未加载'}</Typography>
          <Typography variant="body2">连续记录（截至今天或昨天）: {loaded ? `${streak} 天` : '未加载'}</Typography>
          <Typography variant="body2">记录总数: {loaded ? `${records.length} 条` : '未加载'}</Typography>
          <Typography variant="body2">完成训练天数: {loaded ? `${trainingDays.size} 天` : '未加载'}</Typography>
        </CardContent></Card></Grid>
      </Grid>
      {isAdding && <Paper sx={{ p: 3, mb: 3 }}>
        <Typography variant="h6" gutterBottom>{editingId ? '编辑记录' : '添加新记录'}</Typography>
        <Grid container spacing={3}>
          <Grid item xs={12} md={6}><DatePicker<Date> label="日期" value={form.date}
            onChange={date => setForm(previous => ({ ...previous, date }))} disabled={busy}
            slotProps={{ textField: { fullWidth: true, required: true, error: !validDate(form.date) } }} /></Grid>
          <Grid item xs={12} md={6}><TextField label="疼痛程度 (0-10)" type="number" fullWidth required
            inputProps={{ min: 0, max: 10, step: 1 }} value={form.painLevel} disabled={busy}
            onChange={event => setForm({ ...form, painLevel: event.target.value })} /></Grid>
          <Grid item xs={12} md={6}><TextField label="心情" fullWidth required value={form.mood} disabled={busy}
            onChange={event => setForm({ ...form, mood: event.target.value })} /></Grid>
          <Grid item xs={12} md={6}><TextField label="睡眠时间" fullWidth required value={form.sleep} disabled={busy}
            onChange={event => setForm({ ...form, sleep: event.target.value })} /></Grid>
          <Grid item xs={12}><TextField label="是否完成训练" select fullWidth value={String(form.exerciseCompleted)}
            disabled={busy} SelectProps={{ native: true }} onChange={event => setForm({ ...form, exerciseCompleted: event.target.value === 'true' })}>
            <option value="true">是</option><option value="false">否</option>
          </TextField></Grid>
          <Grid item xs={12}><TextField label="备注" multiline rows={4} fullWidth required value={form.note} disabled={busy}
            onChange={event => setForm({ ...form, note: event.target.value })} /></Grid>
          <Grid item xs={12}><Box display="flex" justifyContent="flex-end" gap={2}>
            <Button variant="outlined" disabled={busy} onClick={() => setIsAdding(false)}>取消</Button>
            <Button variant="contained" disabled={!formValid || busy} onClick={() => void handleSaveRecord()}>{busy ? '处理中...' : '保存记录'}</Button>
          </Box></Grid>
        </Grid>
      </Paper>}
    </Box>
  </LocalizationProvider>;
};
export default DailyRecords;

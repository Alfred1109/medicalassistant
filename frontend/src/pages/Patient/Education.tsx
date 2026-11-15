import React from 'react';
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Divider,
  Paper,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import MenuBookIcon from '@mui/icons-material/MenuBook';
import { useSelector } from 'react-redux';
import type { RootState } from '../../store';
import { patientClinical } from '../../services/patientClinical';
import type { PatientEducationMaterial } from '../../services/patientClinical';

// 宣教材料阅读状态只有后端两种取值（assigned / read）；未知取值如实回显原文。
export function educationStatusLabel(status: string | undefined): string {
  return status === 'read' ? '已读' : status === 'assigned' ? '未读' : (status || '未读');
}

// 后端 FEEDBACK_TOO_LONG 上限 1000（clinical/workspace.py acknowledge_material）。
export function validEducationFeedback(feedback: string): boolean {
  return feedback.trim().length <= 1000;
}

const Education: React.FC = () => {
  const user = useSelector((state: RootState) => state.auth.user);
  const [materials, setMaterials] = React.useState<PatientEducationMaterial[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [openId, setOpenId] = React.useState<string | null>(null);
  const [feedback, setFeedback] = React.useState('');
  const [submitting, setSubmitting] = React.useState(false);
  const [submitError, setSubmitError] = React.useState<string | null>(null);

  const load = React.useCallback(async (signal?: AbortSignal) => {
    setLoading(true);
    setError(null);
    try {
      const { data } = await patientClinical.education(signal);
      setMaterials(Array.isArray(data?.materials) ? data.materials : []);
    } catch (err: any) {
      if (!signal?.aborted) {
        setMaterials([]);
        setError(err?.response?.data?.detail?.message || err?.response?.data?.detail || err?.message || '宣教材料加载失败');
      }
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    if (!user?.id) return;
    const controller = new AbortController();
    load(controller.signal);
    return () => controller.abort();
  }, [user?.id, load]);

  const submitFeedback = async (material: PatientEducationMaterial) => {
    setSubmitError(null);
    if (!validEducationFeedback(feedback)) {
      setSubmitError('阅读反馈不能超过 1000 字。');
      return;
    }
    setSubmitting(true);
    try {
      await patientClinical.acknowledgeEducation(material.assignment_id, feedback.trim());
      setFeedback('');
      await load();
    } catch (err: any) {
      setSubmitError(err?.response?.data?.detail?.message || err?.response?.data?.detail || err?.message || '阅读反馈提交失败');
    } finally {
      setSubmitting(false);
    }
  };

  const unread = materials.filter(item => item.status !== 'read').length;

  return (
    <Paper sx={{ p: { xs: 2, md: 3 }, maxWidth: 850, mx: 'auto' }}>
      <Stack spacing={2}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <MenuBookIcon color="primary" />
          <Typography variant="h5" component="h1">我的宣教材料</Typography>
          {unread > 0 && <Chip label={`未读 ${unread}`} color="warning" size="small" />}
        </Box>
        <Typography variant="body2" color="text.secondary">
          以下材料由负责的医护人员分配。阅读后可提交阅读反馈；如有医护指导，会显示在材料下方。
        </Typography>
        {loading && <Box role="status"><CircularProgress size={24} aria-label="正在加载宣教材料" /></Box>}
        {error && <Alert severity="error">{error}</Alert>}
        {!loading && !error && materials.length === 0 && (
          <Alert severity="info">目前没有分配给你的宣教材料。</Alert>
        )}
        {materials.map(item => {
          const open = openId === item.assignment_id;
          return (
            <Box key={item.assignment_id} sx={{ border: 1, borderColor: 'divider', borderRadius: 1, p: 2 }}>
              <Stack direction="row" spacing={1} alignItems="center" sx={{ flexWrap: 'wrap' }}>
                <Chip size="small" color={item.status === 'read' ? 'success' : 'warning'}
                      label={educationStatusLabel(item.status)} />
                <Typography sx={{ flexGrow: 1, fontWeight: 500 }}>{item.title}</Typography>
                <Button size="small" onClick={() => { setOpenId(open ? null : item.assignment_id); setFeedback(''); setSubmitError(null); }}>
                  {open ? '收起' : '查看材料'}
                </Button>
              </Stack>
              {open && (
                <Stack spacing={1} sx={{ mt: 1 }}>
                  <Divider />
                  <Typography sx={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{item.body}</Typography>
                  {item.guidance && (
                    <Alert severity="info">
                      <Typography variant="body2">医护指导：{item.guidance}</Typography>
                    </Alert>
                  )}
                  {item.status === 'read' ? (
                    item.feedback && (
                      <Typography variant="body2" color="text.secondary">我的阅读反馈：{item.feedback}</Typography>
                    )
                  ) : (
                    <>
                      <TextField
                        label="阅读反馈（可选）"
                        multiline
                        minRows={2}
                        maxRows={4}
                        value={feedback}
                        onChange={event => { setFeedback(event.target.value); setSubmitError(null); }}
                        error={!validEducationFeedback(feedback)}
                        helperText={!validEducationFeedback(feedback) ? '反馈不能超过 1000 字' : '提交后材料标记为已读'}
                        fullWidth
                      />
                      {submitError && <Alert severity="error">{submitError}</Alert>}
                      <Box>
                        <Button variant="contained" disabled={submitting || !validEducationFeedback(feedback)}
                                onClick={() => submitFeedback(item)}>
                          {submitting ? '提交中…' : '提交阅读反馈'}
                        </Button>
                      </Box>
                    </>
                  )}
                </Stack>
              )}
            </Box>
          );
        })}
      </Stack>
    </Paper>
  );
};

export default Education;

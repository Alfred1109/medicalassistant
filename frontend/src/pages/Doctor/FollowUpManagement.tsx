import React, { useState, useEffect } from 'react';
import { useSelector } from 'react-redux';
import {
  Box,
  Typography,
  Divider,
  Snackbar,
  Alert,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  TextField,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  FormHelperText,
  Stack,
  CircularProgress
} from '@mui/material';
import type { SelectChangeEvent } from '@mui/material';
import { LocalizationProvider, DateTimePicker } from '@mui/x-date-pickers';
import { AdapterDateFns } from '@mui/x-date-pickers/AdapterDateFns';
import { zhCN } from 'date-fns/locale';
import { format } from 'date-fns';
import type { RootState } from '../../store';
import { apiService } from '../../services/api';
import type { Patient } from '../../types/patient.types';

// 导入组件
import FollowUpList from '../../components/HealthManager/FollowUpList';
import FollowUpReviewDialog from '../../components/HealthManager/FollowUpReviewDialog';
import FollowUpManualEntryDialog from '../../components/HealthManager/FollowUpManualEntryDialog';
import FollowUpReEvaluateDialog from '../../components/HealthManager/FollowUpReEvaluateDialog';
import FollowUpDetailsDialog from '../../components/HealthManager/FollowUpDetailsDialog';

import type { FollowUpFilters, FollowUpRecord } from '../../types/followup';
import { followUpTypes, getFollowUpStatusInfo, manualEntryText } from '../../constants/followup';
import { canReEvaluateFollowUp, canReviewFollowUp } from '../../utils/followupReview';
import { useFollowUpWorkbench } from '../../hooks/useFollowUpWorkbench';

// 从 axios 错误中提取可读信息
const getApiErrorMessage = (err: unknown, fallback: string): string => {
  const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  if (typeof detail === 'string' && detail) {
    return detail;
  }
  return fallback;
};

const ALL_PATIENTS = 'all';

const FollowUpManagement: React.FC = () => {
  const currentUser = useSelector((state: RootState) => state.auth.user);
  // A different account receives a fresh workspace, including all dialogs and
  // patient choices; no prior identity's content is rendered during effects.
  return <FollowUpWorkspace key={currentUser ? `${currentUser.id}:${currentUser.role}` : 'anonymous'} currentUser={currentUser} />;
};

const FollowUpWorkspace: React.FC<{ currentUser: RootState['auth']['user'] }> = ({ currentUser }) => {

  // 患者列表状态
  const [patients, setPatients] = useState<Patient[]>([]);
  const [patientsLoading, setPatientsLoading] = useState(true);
  const [patientsError, setPatientsError] = useState<string | null>(null);
  const [selectedPatientId, setSelectedPatientId] = useState<string>(ALL_PATIENTS);

  // 随访列表状态
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(10);
  const [filters, setFilters] = useState<FollowUpFilters>({});
  const today = format(new Date(), 'yyyy-MM-dd');
  const hasFilters = Object.values(filters).some(value => Boolean(value));
  const identity = currentUser ? `${currentUser.id}:${currentUser.role}` : '';
  const { records: followUps, total, loading, error, reload: loadFollowUps } = useFollowUpWorkbench(
    identity, selectedPatientId, filters, page, pageSize, setPage);
  const applyFilters = (next: FollowUpFilters) => { setPage(0); setFilters(next); };
  const changePageSize = (size: number) => { setPage(0); setPageSize(size); };

  // 对话框状态
  const [createOpen, setCreateOpen] = useState(false);
  const [reviewId, setReviewId] = useState<string | null>(null);
  const [detailsId, setDetailsId] = useState<string | null>(null);
  const [reEvaluateId, setReEvaluateId] = useState<string | null>(null);
  const [manualEntryId, setManualEntryId] = useState<string | null>(null);
  const [editTarget, setEditTarget] = useState<FollowUpRecord | null>(null);
  const [cancelTarget, setCancelTarget] = useState<FollowUpRecord | null>(null);
  const [rescheduleTarget, setRescheduleTarget] = useState<FollowUpRecord | null>(null);

  // 新建随访表单
  const [createForm, setCreateForm] = useState<{
    patient_id: string;
    follow_up_type: string;
    scheduled_date: Date;
    description: string;
  }>({
    patient_id: '',
    follow_up_type: 'phone',
    scheduled_date: new Date(),
    description: ''
  });
  const [createError, setCreateError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // 编辑随访表单
  const [editForm, setEditForm] = useState<{
    follow_up_type: string;
    scheduled_date: Date;
    description: string;
  }>({
    follow_up_type: 'phone',
    scheduled_date: new Date(),
    description: ''
  });

  // 取消 / 重新安排表单
  const [cancelReason, setCancelReason] = useState('');
  const [rescheduleForm, setRescheduleForm] = useState<{ new_date: Date; reason: string }>({
    new_date: new Date(),
    reason: ''
  });

  const [snackbar, setSnackbar] = useState({
    open: false,
    message: '',
    severity: 'success' as 'success' | 'error' | 'info' | 'warning'
  });

  const showSnackbar = (message: string, severity: 'success' | 'error' | 'info' | 'warning') => {
    setSnackbar({ open: true, message, severity });
  };

  // 加载医生的患者列表（真实接口 GET /doctors/patients）
  useEffect(() => {
    let cancelled = false;
    setPatients([]);
    setPatientsError(null);
    setSelectedPatientId(ALL_PATIENTS);
    setPage(0);
    setFilters({});
    setCreateOpen(false); setReviewId(null); setDetailsId(null); setReEvaluateId(null);
    setManualEntryId(null); setEditTarget(null); setCancelTarget(null); setRescheduleTarget(null);
    const loadPatients = async () => {
      try {
        setPatientsLoading(true);
        if (!identity) return;
        const response = await (currentUser?.role === 'health_manager' ? apiService.healthManager.getPatients() : apiService.doctor.getPatients());
        if (cancelled) return;
        const list = Array.isArray(response.data) ? response.data : [];
        setPatients(list);
        setPatientsError(null);
      } catch (err) {
        if (cancelled) return;
        setPatientsError(getApiErrorMessage(err, '加载患者列表失败'));
      } finally {
        if (!cancelled) {
          setPatientsLoading(false);
        }
      }
    };
    loadPatients();
    return () => {
      cancelled = true;
    };
  }, [identity]);

  // -------- 新建随访 --------
  const handleAddFollowUp = () => {
    setCreateForm({
      patient_id: selectedPatientId !== ALL_PATIENTS
        ? selectedPatientId
        : (patients[0]?.id ?? ''),
      follow_up_type: 'phone',
      scheduled_date: new Date(),
      description: ''
    });
    setCreateError(null);
    setCreateOpen(true);
  };

  const handleCreateSubmit = async () => {
    if (!createForm.patient_id) {
      setCreateError('请选择患者');
      return;
    }
    if (!createForm.description.trim()) {
      setCreateError('请填写随访说明');
      return;
    }
    try {
      setSubmitting(true);
      await apiService.createFollowUp({
        patient_id: createForm.patient_id,
        follow_up_type: createForm.follow_up_type,
        scheduled_date: createForm.scheduled_date.toISOString(),
        description: createForm.description.trim(),
        provider_id: currentUser?.id,
        created_by: currentUser?.id
      });
      setCreateOpen(false);
      showSnackbar('随访创建成功', 'success');
      await loadFollowUps();
    } catch (err) {
      showSnackbar(getApiErrorMessage(err, '创建随访失败'), 'error');
    } finally {
      setSubmitting(false);
    }
  };

  // -------- 编辑随访（PUT /health-records/followups/{id}） --------
  const handleEditFollowUp = (id: string) => {
    const record = followUps.find(item => item.id === id);
    if (!record) return;
    setEditForm({
      follow_up_type: record.follow_up_type,
      scheduled_date: record.scheduled_date ? new Date(record.scheduled_date) : new Date(),
      description: record.description || ''
    });
    setEditTarget(record);
  };

  const handleEditSubmit = async () => {
    if (!editTarget) return;
    try {
      setSubmitting(true);
      await apiService.updateFollowUp(editTarget.id, {
        follow_up_type: editForm.follow_up_type,
        scheduled_date: editForm.scheduled_date.toISOString(),
        description: editForm.description.trim()
      });
      setEditTarget(null);
      showSnackbar('随访更新成功', 'success');
      await loadFollowUps();
    } catch (err) {
      showSnackbar(getApiErrorMessage(err, '更新随访失败'), 'error');
    } finally {
      setSubmitting(false);
    }
  };

  // -------- 提交手工录入（POST /health-records/followups/{id}/complete） --------
  const handleCompleteFollowUp = (id: string) => setManualEntryId(id);

  // -------- 取消随访（POST /health-records/followups/{id}/cancel） --------
  const handleCancelFollowUp = (id: string) => {
    const record = followUps.find(item => item.id === id);
    setCancelReason('');
    setCancelTarget(record ?? null);
  };

  const handleCancelSubmit = async () => {
    if (!cancelTarget) return;
    if (!cancelReason.trim()) {
      showSnackbar('请填写取消原因', 'warning');
      return;
    }
    try {
      setSubmitting(true);
      await apiService.cancelFollowUp(cancelTarget.id, {
        cancel_reason: cancelReason.trim()
      });
      setCancelTarget(null);
      showSnackbar('随访已取消', 'success');
      await loadFollowUps();
    } catch (err) {
      showSnackbar(getApiErrorMessage(err, '操作失败'), 'error');
    } finally {
      setSubmitting(false);
    }
  };

  // -------- 重新安排随访（POST /health-records/followups/{id}/reschedule） --------
  const handleRescheduleFollowUp = (id: string) => {
    const record = followUps.find(item => item.id === id);
    setRescheduleForm({ new_date: new Date(), reason: '' });
    setRescheduleTarget(record ?? null);
  };

  const handleRescheduleSubmit = async () => {
    if (!rescheduleTarget) return;
    if (!rescheduleForm.reason.trim()) {
      showSnackbar('请填写重新安排的原因', 'warning');
      return;
    }
    try {
      setSubmitting(true);
      await apiService.rescheduleFollowUp(rescheduleTarget.id, {
        new_date: rescheduleForm.new_date.toISOString(),
        reason: rescheduleForm.reason.trim()
      });
      setRescheduleTarget(null);
      showSnackbar('随访已重新安排', 'success');
      await loadFollowUps();
    } catch (err) {
      showSnackbar(getApiErrorMessage(err, '操作失败'), 'error');
    } finally {
      setSubmitting(false);
    }
  };

  // -------- 删除随访：后端暂无 DELETE /health-records/followups/{id} --------
  const handleDeleteFollowUp = () => {
    showSnackbar('后端暂未提供随访删除接口，该功能待随访领域收敛后开放', 'info');
  };

  // 关闭提示消息
  const handleCloseSnackbar = () => {
    setSnackbar(prev => ({ ...prev, open: false }));
  };

  const handlePatientChange = (event: SelectChangeEvent<string>) => {
    setPage(0);
    setSelectedPatientId(event.target.value);
  };

  const handleCreateFormChange = (field: 'patient_id' | 'follow_up_type' | 'description', value: string) => {
    setCreateForm(prev => ({ ...prev, [field]: value }));
    if (createError) {
      setCreateError(null);
    }
  };

  const renderPatientOption = (patient: Patient) =>
    `${patient.name || '未命名患者'}${patient.diagnosis ? `（${patient.diagnosis}）` : ''}`;

  return (
    <Box>
      <Typography variant="h5" gutterBottom>
        随访管理
      </Typography>
      <Typography variant="body2" color="text.secondary" paragraph>
        查看并管理患者的随访计划。手工录入后进入待审阅，责任医护审阅通过后完成随访；
        删除功能待随访领域收敛后开放。
      </Typography>
      <Divider sx={{ mb: 2 }} />

      {/* 患者选项只用于筛选和创建；列表由工作台接口统一授权并分页。 */}
      <Stack direction="row" spacing={2} alignItems="center" sx={{ mb: 2 }}>
        <FormControl size="small" sx={{ minWidth: 280 }}>
          <InputLabel id="doctor-followup-patient-label">患者范围</InputLabel>
          <Select
            labelId="doctor-followup-patient-label"
            value={selectedPatientId}
            label="患者范围"
            onChange={handlePatientChange}
            disabled={patientsLoading || patients.length === 0}
          >
            <MenuItem value={ALL_PATIENTS}>全部患者</MenuItem>
            {patients.map(patient => (
              <MenuItem key={patient.id} value={patient.id}>
                {renderPatientOption(patient)}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
        {patientsLoading && <CircularProgress size={20} />}
      </Stack>

      {patientsError && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {patientsError}
        </Alert>
      )}

      <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" sx={{ mb: 2 }}>
        <Button variant={!hasFilters ? 'contained' : 'outlined'} onClick={() => applyFilters({})}>全部随访</Button>
        <Button variant={filters.status === 'in_review' ? 'contained' : 'outlined'} onClick={() => applyFilters({ status: 'in_review' })}>待医护审阅</Button>
        <Button variant={!filters.status && filters.start_date === today && filters.end_date === today ? 'contained' : 'outlined'} onClick={() => { const day = format(new Date(), 'yyyy-MM-dd'); applyFilters({ start_date: day, end_date: day }); }}>今日安排</Button>
      </Stack>

      <FollowUpList
        records={followUps}
        loading={loading}
        error={error || undefined}
        totalCount={total}
        page={page}
        pageSize={pageSize}
        onPageChange={setPage}
        onPageSizeChange={changePageSize}
        onAdd={handleAddFollowUp}
        onEdit={handleEditFollowUp}
        onView={setDetailsId}
        onReEvaluate={setReEvaluateId}
        canReEvaluate={record => canReEvaluateFollowUp(record, currentUser)}
        onComplete={handleCompleteFollowUp}
        onReview={setReviewId}
        canReview={record => canReviewFollowUp(record, currentUser)}
        onCancel={handleCancelFollowUp}
        onReschedule={handleRescheduleFollowUp}
        onDelete={handleDeleteFollowUp}
        onFilterChange={applyFilters}
        onRefresh={loadFollowUps}
        currentFilters={filters}
      />

      <FollowUpDetailsDialog
        followUpId={detailsId}
        actor={currentUser ? { id: currentUser.id, role: currentUser.role } : null}
        onClose={() => setDetailsId(null)}
        onOpen={setDetailsId}
        onReEvaluate={id => { setDetailsId(null); setReEvaluateId(id); }}
      />
      <FollowUpReEvaluateDialog
        followUpId={reEvaluateId}
        actor={currentUser ? { id: currentUser.id, role: currentUser.role } : null}
        onClose={() => setReEvaluateId(null)}
        onCreated={async record => { setReEvaluateId(null); setDetailsId(record.id); showSnackbar('复评节点已创建', 'success'); await loadFollowUps(); }}
      />

      <FollowUpManualEntryDialog
        followUpId={manualEntryId}
        onClose={() => setManualEntryId(null)}
        onSaved={async () => { setManualEntryId(null); showSnackbar(manualEntryText.success, 'success'); await loadFollowUps(); }}
      />

      <FollowUpReviewDialog
        followUpId={reviewId}
        actor={currentUser ? { id: currentUser.id, role: currentUser.role } : null}
        onClose={() => setReviewId(null)}
        onReviewed={async () => { setReviewId(null); showSnackbar('审阅结果已保存', 'success'); await loadFollowUps(); }}
      />

      {/* 新建随访对话框：对齐后端 FollowUpRecordCreate（第二代）必填字段 */}
      <Dialog
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        fullWidth
        maxWidth="sm"
      >
        <DialogTitle>新建随访</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <FormControl fullWidth required error={!!createError && !createForm.patient_id}>
              <InputLabel id="create-followup-patient-label">患者</InputLabel>
              <Select
                labelId="create-followup-patient-label"
                value={createForm.patient_id}
                label="患者"
                onChange={(e) => handleCreateFormChange('patient_id', e.target.value)}
                disabled={submitting || patients.length === 0}
              >
                {patients.map(patient => (
                  <MenuItem key={patient.id} value={patient.id}>
                    {renderPatientOption(patient)}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>

            <FormControl fullWidth required>
              <InputLabel id="create-followup-type-label">随访类型</InputLabel>
              <Select
                labelId="create-followup-type-label"
                value={createForm.follow_up_type}
                label="随访类型"
                onChange={(e) => handleCreateFormChange('follow_up_type', e.target.value)}
                disabled={submitting}
              >
                {followUpTypes.map(type => (
                  <MenuItem key={type.value} value={type.value}>{type.label}</MenuItem>
                ))}
              </Select>
            </FormControl>

            <LocalizationProvider dateAdapter={AdapterDateFns} adapterLocale={zhCN}>
              <DateTimePicker
                label="计划日期"
                value={createForm.scheduled_date}
                onChange={(date) => {
                  if (date) {
                    setCreateForm(prev => ({ ...prev, scheduled_date: date }));
                  }
                }}
                disabled={submitting}
                slotProps={{ textField: { fullWidth: true } }}
              />
            </LocalizationProvider>

            <TextField
              fullWidth
              required
              multiline
              rows={3}
              label="随访说明"
              value={createForm.description}
              onChange={(e) => handleCreateFormChange('description', e.target.value)}
              disabled={submitting}
            />

            {createError && <FormHelperText error>{createError}</FormHelperText>}
            {!currentUser?.id && (
              <FormHelperText error>
                未获取到当前医生身份，创建时后端将以登录用户作为随访负责人
              </FormHelperText>
            )}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCreateOpen(false)} disabled={submitting}>取消</Button>
          <Button
            onClick={handleCreateSubmit}
            variant="contained"
            disabled={submitting || patients.length === 0}
          >
            {submitting ? <CircularProgress size={22} /> : '创建'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* 编辑随访对话框 */}
      <Dialog
        open={!!editTarget}
        onClose={() => setEditTarget(null)}
        fullWidth
        maxWidth="sm"
      >
        <DialogTitle>编辑随访</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <FormControl fullWidth required>
              <InputLabel id="edit-followup-type-label">随访类型</InputLabel>
              <Select
                labelId="edit-followup-type-label"
                value={editForm.follow_up_type}
                label="随访类型"
                onChange={(e) => setEditForm(prev => ({ ...prev, follow_up_type: e.target.value }))}
                disabled={submitting}
              >
                {followUpTypes.map(type => (
                  <MenuItem key={type.value} value={type.value}>{type.label}</MenuItem>
                ))}
              </Select>
            </FormControl>

            <TextField
              label="状态"
              value={getFollowUpStatusInfo(editTarget?.status ?? '').label}
              InputProps={{ readOnly: true }}
              helperText="状态由对应的随访业务操作更新"
            />

            <LocalizationProvider dateAdapter={AdapterDateFns} adapterLocale={zhCN}>
              <DateTimePicker
                label="计划日期"
                value={editForm.scheduled_date}
                onChange={(date) => {
                  if (date) {
                    setEditForm(prev => ({ ...prev, scheduled_date: date }));
                  }
                }}
                disabled={submitting}
                slotProps={{ textField: { fullWidth: true } }}
              />
            </LocalizationProvider>

            <TextField
              fullWidth
              required
              multiline
              rows={3}
              label="随访说明"
              value={editForm.description}
              onChange={(e) => setEditForm(prev => ({ ...prev, description: e.target.value }))}
              disabled={submitting}
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setEditTarget(null)} disabled={submitting}>取消</Button>
          <Button onClick={handleEditSubmit} variant="contained" disabled={submitting}>
            {submitting ? <CircularProgress size={22} /> : '保存'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* 取消随访对话框：后端要求 cancel_reason 必填 */}
      <Dialog
        open={!!cancelTarget}
        onClose={() => setCancelTarget(null)}
        fullWidth
        maxWidth="xs"
      >
        <DialogTitle>取消随访</DialogTitle>
        <DialogContent>
          <TextField
            autoFocus
            fullWidth
            required
            multiline
            rows={2}
            label="取消原因"
            value={cancelReason}
            onChange={(e) => setCancelReason(e.target.value)}
            disabled={submitting}
            sx={{ mt: 1 }}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCancelTarget(null)} disabled={submitting}>返回</Button>
          <Button onClick={handleCancelSubmit} color="error" disabled={submitting}>
            {submitting ? <CircularProgress size={22} /> : '确认取消随访'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* 重新安排随访对话框：对应后端 RescheduleFollowUpRequest */}
      <Dialog
        open={!!rescheduleTarget}
        onClose={() => setRescheduleTarget(null)}
        fullWidth
        maxWidth="xs"
      >
        <DialogTitle>重新安排随访</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <LocalizationProvider dateAdapter={AdapterDateFns} adapterLocale={zhCN}>
              <DateTimePicker
                label="新的计划日期"
                value={rescheduleForm.new_date}
                onChange={(date) => {
                  if (date) {
                    setRescheduleForm(prev => ({ ...prev, new_date: date }));
                  }
                }}
                disabled={submitting}
                slotProps={{ textField: { fullWidth: true } }}
              />
            </LocalizationProvider>
            <TextField
              fullWidth
              required
              multiline
              rows={2}
              label="原因"
              value={rescheduleForm.reason}
              onChange={(e) => setRescheduleForm(prev => ({ ...prev, reason: e.target.value }))}
              disabled={submitting}
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setRescheduleTarget(null)} disabled={submitting}>取消</Button>
          <Button onClick={handleRescheduleSubmit} variant="contained" disabled={submitting}>
            {submitting ? <CircularProgress size={22} /> : '确认'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* 提示消息 */}
      <Snackbar
        open={snackbar.open}
        autoHideDuration={5000}
        onClose={handleCloseSnackbar}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        <Alert
          onClose={handleCloseSnackbar}
          severity={snackbar.severity}
          variant="filled"
        >
          {snackbar.message}
        </Alert>
      </Snackbar>
    </Box>
  );
};

export default FollowUpManagement;

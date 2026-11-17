const { request, getSession } = require('../../../services/api');
const { patientSelfSnapshotDigest } = require('../../../utils/reviewEvidence');

const roleLabels = { doctor: '医生', health_manager: '健康管理师' };
const followupTypes = [
  { value: 'phone', label: '电话随访' }, { value: 'online', label: '线上随访' },
  { value: 'onsite', label: '门诊随访' }, { value: 'home_visit', label: '家庭访视' },
  { value: 'remote_monitoring', label: '远程监测' }, { value: 'group', label: '小组随访' },
  { value: 'other', label: '其他' },
];
const statusLabels = {
  scheduled: '待随访', awaiting_fill: '待填写', in_review: '待审阅', completed: '已完成',
  overdue: '逾期', lost: '已失访', canceled: '已取消', cancelled: '已取消', missed: '未到访', rescheduled: '已改期',
};
const apiPath = (path) => path;
const valueText = (value, fallback = '未记录') => value === undefined || value === null || value === '' ? fallback : String(value);
const errorText = (error, fallback) => error && error.message ? error.message : fallback;
const lineText = (value) => {
  if (value === null || value === undefined || value === '') return '';
  if (typeof value !== 'object') return String(value);
  return Object.entries(value).map(([key, item]) => `${key}：${typeof item === 'object' && item !== null ? JSON.stringify(item) : valueText(item, '')}`).filter(Boolean).join('；');
};
const historyRows = (values) => (Array.isArray(values) ? values : []).map((item) => ({ display: lineText(item) }));

Page({
  data: {
    roleLabel: '', actorId: '', patients: [], visiblePatients: [], patientKeyword: '', patientSkip: 0, patientHasMore: false, selectedPatientId: '', selectedPatientName: '',
    patientLoading: false, detailLoading: false, busy: false, error: '', message: '',
    healthRecord: null, followups: [], hasMore: false, skip: 0, limit: 50,
    viewMode: 'patients', overviewLoading: false, overviewItems: [], overviewSkip: 0, overviewHasMore: false, chooseForSchedule: false,
    typeOptions: followupTypes, typeIndex: 0, createOpen: false, scheduledDate: '', scheduledTime: '09:00',
    description: '', completionTarget: null, completionResult: '', completionNotes: '', completionAnswers: [],
    reviewTarget: null, reviewComment: '', reviewLoading: false, reviewEvidenceRows: [], reviewEvidenceError: '', reevaluateTarget: null, reevaluateDate: '', reevaluateReason: '',
  },
  onLoad() {
    this._patientsGeneration = 0;
    this._patientGeneration = 0;
    this._overviewGeneration = 0;
    this._reviewGeneration = 0;
    const requestedView = this.options && this.options.view;
    const viewMode = ['workbench', 'followups'].includes(requestedView) ? requestedView : 'patients';
    this.setData({ viewMode });
    this.syncIdentity();
  },
  onPullDownRefresh() { this.refresh().finally(() => wx.stopPullDownRefresh()); },
  onShow() {
    if (!this.identityFrom(getSession()) || this.identityFrom(getSession()).key !== this._identityKey) { this.syncIdentity(); return; }
    if (this.data.selectedPatientId && !this.data.detailLoading && !this.data.busy) this.loadPatientDetail(false);
    else if (['workbench', 'followups'].includes(this.data.viewMode) && !this.data.overviewLoading && !this.data.busy) this.loadFollowupOverview(true);
  },
  identityFrom(session) {
    const user = session && session.user;
    if (!session || !session.identityConfirmed || !user || !['doctor', 'health_manager'].includes(session.role)) return null;
    const actorId = String(user.id || user.actor_id || '');
    const sessionId = String(session.sessionId || '');
    return actorId ? { actorId, role: session.role, sessionId, key: `${session.role}:${actorId}:${sessionId}` } : null;
  },
  isCurrentIdentity(identityKey = this._identityKey) {
    const identity = this.identityFrom(getSession());
    return !!identity && identity.key === identityKey && this._identityKey === identityKey;
  },
  reconcileIdentity(identityKey = this._identityKey) {
    if (this.isCurrentIdentity(identityKey)) return true;
    this.syncIdentity();
    return false;
  },
  clearSensitiveState(message) {
    this._patientsGeneration += 1;
    this._patientGeneration += 1;
    this._overviewGeneration += 1;
    this._reviewGeneration += 1;
    this._identityKey = '';
    this.setData({
      actorId: '', sessionRole: '', roleLabel: '', patients: [], visiblePatients: [], patientKeyword: '', patientSkip: 0, patientHasMore: false, selectedPatientId: '', selectedPatientName: '',
      healthRecord: null, followups: [], overviewItems: [], skip: 0, overviewSkip: 0, hasMore: false, overviewHasMore: false,
      patientLoading: false, detailLoading: false, overviewLoading: false, busy: false,
      createOpen: false, completionTarget: null, reviewTarget: null, reviewLoading: false, reviewEvidenceRows: [], reviewEvidenceError: '', reevaluateTarget: null,
      completionAnswers: [], completionResult: '', completionNotes: '', reviewComment: '', description: '',
      chooseForSchedule: false, error: message || '登录已失效，请重新登录后查看患者信息。', message: '',
    });
  },
  syncIdentity() {
    const identity = this.identityFrom(getSession());
    if (!identity) { this.clearSensitiveState('请先使用已确认的医生或健康管理师账号登录。'); return false; }
    if (identity.key !== this._identityKey) {
      this.clearSensitiveState('账号已切换，已清除上一账号的患者资料。');
      this._identityKey = identity.key;
      this.setData({ roleLabel: roleLabels[identity.role], actorId: identity.actorId, sessionRole: identity.role, error: '' });
      this.loadPatients(true);
      if (['workbench', 'followups'].includes(this.data.viewMode)) this.loadFollowupOverview(true);
    }
    return true;
  },
  async refresh() {
    if (['workbench', 'followups'].includes(this.data.viewMode) && !this.data.selectedPatientId) await this.loadFollowupOverview(true);
    else if (this.data.selectedPatientId) await this.loadPatientDetail(true);
    else if (this.data.viewMode === 'patients') await this.loadPatients(true);
    else await this.loadFollowupOverview(true);
  },
  async loadPatients(reset = false) {
    if (this.data.patientLoading) return;
    if (!this.reconcileIdentity()) return;
    const generation = ++this._patientsGeneration;
    const identityKey = this._identityKey;
    const skip = reset ? 0 : this.data.patientSkip;
    this.setData({ patientLoading: true, error: '' });
    try {
      const route = this.data.sessionRole === 'doctor' ? '/doctors/patients' : '/health-managers/patients';
      const rows = await request(apiPath(`${route}?skip=${skip}&limit=100`));
      if (generation !== this._patientsGeneration || !this.reconcileIdentity(identityKey)) return;
      if (!Array.isArray(rows)) throw new Error('患者目录响应格式异常。');
      const patients = rows.map((row) => ({
        id: String(row.id || row._id || row.patient_id || ''),
        name: valueText(row.name, '未命名患者'),
        diagnosis: valueText(row.diagnosis || row.primary_diagnosis, ''),
      })).filter((row) => row.id);
      const all = reset ? patients : this.data.patients.concat(patients.filter((row) => !this.data.patients.some((item) => item.id === row.id)));
      this.setData({ patients: all, visiblePatients: this.filterPatientRows(all, this.data.patientKeyword), patientSkip: skip + rows.length, patientHasMore: rows.length === 100 });
    } catch (error) {
      if (generation === this._patientsGeneration && this.reconcileIdentity(identityKey)) {
        if (error.statusCode === 401) this.clearSensitiveState('登录已失效，请重新登录后查看患者信息。');
        else this.setData({ error: errorText(error, '患者目录加载失败。') });
      }
    } finally { if (generation === this._patientsGeneration && this.isCurrentIdentity(identityKey)) this.setData({ patientLoading: false }); }
  },
  filterPatientRows(rows, keyword) {
    const query = String(keyword || '').trim().toLocaleLowerCase();
    return query ? rows.filter((row) => `${row.name} ${row.diagnosis}`.toLocaleLowerCase().includes(query)) : rows;
  },
  onPatientSearch(event) {
    const patientKeyword = event.detail.value || '';
    this.setData({ patientKeyword, visiblePatients: this.filterPatientRows(this.data.patients, patientKeyword) });
  },
  async loadMorePatients() { await this.loadPatients(false); },
  async selectPatient(event) {
    const identityKey = this._identityKey;
    const patientId = String(event.currentTarget.dataset.id || '');
    if (!patientId || patientId === this.data.selectedPatientId) return;
    const patient = this.data.patients.find((item) => item.id === patientId);
    if (this.data.chooseForSchedule) {
      const confirmed = await new Promise((resolve) => wx.showModal({
        title: '确认随访对象', content: `将为${patient ? patient.name : '该患者'}安排随访。`,
        confirmText: '继续安排', cancelText: '重新选择', success: (result) => resolve(!!result.confirm), fail: () => resolve(false),
      }));
      if (!confirmed || !this.reconcileIdentity(identityKey)) return;
      this.setData({ selectedPatientId: patientId, selectedPatientName: patient ? patient.name : '患者', chooseForSchedule: false, viewMode: 'patients' });
      this.openCreate();
      return;
    }
    const confirmed = await new Promise((resolve) => wx.showModal({
      title: '确认患者', content: `即将打开${patient ? patient.name : '该患者'}的健康档案与随访记录。`,
      confirmText: '继续查看', cancelText: '返回目录', success: (result) => resolve(!!result.confirm), fail: () => resolve(false),
    }));
    if (!confirmed || !this.reconcileIdentity(identityKey)) return;
    this._patientGeneration += 1;
    this.setData({ selectedPatientId: patientId, selectedPatientName: patient ? patient.name : '患者', skip: 0, followups: [], healthRecord: null, detailLoading: false, error: '', message: '' });
    await this.loadPatientDetail(true);
  },
  async loadFollowupOverview(reset = false) {
    if (this.data.overviewLoading) return;
    if (!this.reconcileIdentity()) return;
    const generation = ++this._overviewGeneration;
    const identityKey = this._identityKey;
    const skip = reset ? 0 : this.data.overviewSkip;
    this.setData({ overviewLoading: true, error: '' });
    try {
      const statuses = this.data.viewMode === 'workbench' ? '&status=scheduled&status=awaiting_fill&status=in_review&status=overdue' : '';
      const page = await request(apiPath(`/health-records/followup-workbench?skip=${skip}&limit=50${statuses}`));
      if (generation !== this._overviewGeneration || !this.reconcileIdentity(identityKey)) return;
      if (!page || !Array.isArray(page.items)) throw new Error('随访列表响应格式异常。');
      const rows = page.items.map((item) => ({ ...this.formatFollowup(item), patientName: valueText(item.patient_name, '患者'), patientId: String(item.patient_id || '') }));
      this.setData({
        overviewItems: reset ? rows : this.data.overviewItems.concat(rows),
        overviewSkip: skip + rows.length,
        overviewHasMore: skip + rows.length < Number(page.total || 0),
      });
    } catch (error) {
      if (generation === this._overviewGeneration && this.reconcileIdentity(identityKey)) {
        if (error.statusCode === 401) this.clearSensitiveState('登录已失效，请重新登录后查看患者信息。');
        else this.setData({ error: errorText(error, '随访工作台加载失败。') });
      }
    }
    finally { if (generation === this._overviewGeneration && this.isCurrentIdentity(identityKey)) this.setData({ overviewLoading: false }); }
  },
  async refreshFollowups() { if (['workbench', 'followups'].includes(this.data.viewMode)) await this.loadFollowupOverview(true); else await this.refresh(); },
  async loadMoreOverview() { await this.loadFollowupOverview(false); },
  async viewPatientFromFollowup(event) {
    const identityKey = this._identityKey;
    const patientId = String(event.currentTarget.dataset.patientId || '');
    if (!patientId) return;
    const patient = this.data.patients.find((item) => item.id === patientId);
    const name = patient ? patient.name : String(event.currentTarget.dataset.patientName || '患者');
    const confirmed = await new Promise((resolve) => wx.showModal({
      title: '确认患者', content: `即将打开${name}的健康档案与随访记录。`,
      confirmText: '继续查看', cancelText: '返回工作台', success: (result) => resolve(!!result.confirm), fail: () => resolve(false),
    }));
    if (!confirmed || !this.reconcileIdentity(identityKey)) return;
    this._patientGeneration += 1;
    this.setData({ selectedPatientId: patientId, selectedPatientName: name, skip: 0, followups: [], healthRecord: null, detailLoading: false, viewMode: 'patients', error: '', message: '' });
    await this.loadPatientDetail(true);
  },
  choosePatientForNewFollowup() { this.setData({ selectedPatientId: '', viewMode: 'patients', chooseForSchedule: true }); },
  openTasks() { wx.navigateTo({ url: '/pages/clinical/tasks/index' }); },
  async loadPatientDetail(reset) {
    const patientId = this.data.selectedPatientId;
    if (!patientId || this.data.detailLoading) return;
    if (!this.reconcileIdentity()) return;
    const generation = ++this._patientGeneration;
    const identityKey = this._identityKey;
    const skip = reset ? 0 : this.data.skip;
    this.setData({ detailLoading: true, error: '' });
    const rolePrefix = this.data.sessionRole === 'doctor' ? '/doctors' : '/health-managers';
    const followupQuery = `patient_id=${encodeURIComponent(patientId)}&skip=${skip}&limit=${this.data.limit}`;
    try {
      const [healthRecord, followupPage] = await Promise.all([
        request(apiPath(`${rolePrefix}/health-records/${encodeURIComponent(patientId)}`)),
        request(apiPath(`/health-records/followup-workbench?${followupQuery}`)),
      ]);
      if (generation !== this._patientGeneration || !this.reconcileIdentity(identityKey) || patientId !== this.data.selectedPatientId) return;
      if (!followupPage || !Array.isArray(followupPage.items)) throw new Error('随访列表响应格式异常。');
      healthRecord.allergies = Array.isArray(healthRecord.allergies) ? healthRecord.allergies : [];
      healthRecord.allergiesLabel = healthRecord.allergies.map(lineText).filter(Boolean).join('、');
      healthRecord.medicalHistoryRows = historyRows(healthRecord.medicalHistory);
      healthRecord.rehabHistoryRows = historyRows(healthRecord.rehabHistory);
      healthRecord.medicationRows = historyRows(healthRecord.medications);
      healthRecord.vitalRows = (Array.isArray(healthRecord.vitalSigns) ? healthRecord.vitalSigns : []).map((item) => ({ display: [item.recorded_at, lineText(item.data_content || item.data || item)].filter(Boolean).join('　') }));
      const formatted = followupPage.items.map((item) => this.formatFollowup(item));
      this.setData({
      healthRecord,
        followups: reset ? formatted : this.data.followups.concat(formatted),
        skip: skip + formatted.length,
        hasMore: skip + formatted.length < Number(followupPage.total || 0),
      });
    } catch (error) {
      if (generation === this._patientGeneration && this.reconcileIdentity(identityKey) && patientId === this.data.selectedPatientId) {
        if (error.statusCode === 401) this.clearSensitiveState('登录已失效，请重新登录后查看患者信息。');
        else this.setData({ error: errorText(error, '患者信息加载失败。') });
      }
    } finally { if (generation === this._patientGeneration && this.isCurrentIdentity(identityKey)) this.setData({ detailLoading: false }); }
  },
  formatFollowup(item) {
    const date = item.scheduled_date ? new Date(item.scheduled_date) : null;
    const dateLabel = date && !Number.isNaN(date.getTime()) ? date.toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' }) : '时间未记录';
    const type = followupTypes.find((option) => option.value === item.follow_up_type);
    const evidenceSource = item.current_evidence && item.current_evidence.source;
    const manualEvidence = !item.effective_response && (evidenceSource === 'manual_entry' || (item.completion_data && item.completion_data.source === 'manual_entry'));
    const canReview = item.status === 'in_review' && [item.provider_id, item.created_by].map(String).includes(this.data.actorId);
    const canApprove = canReview && manualEvidence;
    const canReevaluate = ['completed', 'canceled', 'missed', 'overdue'].includes(item.status) && !item.next_visit_id && !item.next_follow_up_id;
    return {
      ...item,
      statusLabel: statusLabels[item.status] || valueText(item.status),
      typeLabel: type ? type.label : valueText(item.follow_up_type), dateLabel,
      canComplete: ['scheduled', 'awaiting_fill', 'overdue'].includes(item.status),
      canReview, canApprove, canReevaluate,
      evidenceLabel: evidenceSource === 'external_form' ? '外部表单答卷' : evidenceSource === 'manual_entry' ? '手工录入' : evidenceSource === 'ambiguous' ? '来源冲突' : '尚无有效证据',
      descriptionLabel: valueText(item.description, '未填写随访说明'),
      resultLabel: valueText(item.follow_up_result || item.completion_data && item.completion_data.result, ''),
      questions: Array.isArray(item.questions) ? item.questions : [],
    };
  },
  async loadMore() { await this.loadPatientDetail(false); },
  backToPatients() {
    this._patientGeneration += 1;
    this.setData({ selectedPatientId: '', selectedPatientName: '', healthRecord: null, followups: [], skip: 0, hasMore: false, detailLoading: false, error: '', message: '' });
  },
  openCreate() {
    const now = new Date();
    const date = new Date(now.getTime() - now.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
    this.setData({ createOpen: true, typeIndex: 0, scheduledDate: date, scheduledTime: '09:00', description: '' });
  },
  closeCreate() { this.setData({ createOpen: false }); },
  onTypeChange(event) { this.setData({ typeIndex: Number(event.detail.value) || 0 }); },
  onScheduledDate(event) { this.setData({ scheduledDate: event.detail.value }); },
  onScheduledTime(event) { this.setData({ scheduledTime: event.detail.value }); },
  onDescriptionInput(event) { this.setData({ description: event.detail.value }); },
  async createFollowup() {
    if (this.data.busy || !this.data.selectedPatientId) return;
    if (!this.reconcileIdentity()) return;
    const identityKey = this._identityKey;
    const session = getSession();
    const actor = session && session.user;
    const scheduledDate = this.data.scheduledDate && this.data.scheduledTime ? new Date(`${this.data.scheduledDate}T${this.data.scheduledTime}:00`).toISOString() : '';
    const description = String(this.data.description || '').trim();
    if (!scheduledDate || !description) return this.setData({ error: '请填写计划时间和随访说明。' });
    this.setData({ busy: true, error: '', message: '' });
    try {
      await request(apiPath('/health-records/followups'), { method: 'POST', data: {
        patient_id: this.data.selectedPatientId,
        follow_up_type: this.data.typeOptions[this.data.typeIndex].value,
        scheduled_date: scheduledDate,
        provider_id: String(actor.id || actor.actor_id),
        description,
        questions: [],
      }, header: { 'content-type': 'application/json' } });
      if (!this.reconcileIdentity(identityKey)) return;
      this.setData({ createOpen: false, message: '随访计划已保存。' });
      await this.loadPatientDetail(true);
    } catch (error) {
      if (!this.reconcileIdentity(identityKey)) return;
      if (error.statusCode === 401) this.clearSensitiveState('登录已失效，请重新登录后查看患者信息。');
      else this.setData({ error: errorText(error, '随访计划未保存。') });
    }
    finally { if (this.isCurrentIdentity(identityKey)) this.setData({ busy: false }); }
  },
  openCompletion(event) {
    const item = [...this.data.followups, ...this.data.overviewItems].find((row) => row.id === event.currentTarget.dataset.id);
    if (!item) return;
    const answers = item.questions.map((question) => ({ question_id: question.question_id, answer_value: '', answer_text: '' }));
    this.setData({ completionTarget: item, completionResult: '', completionNotes: '', completionAnswers: answers });
  },
  closeCompletion() { this.setData({ completionTarget: null }); },
  onCompletionResult(event) { this.setData({ completionResult: event.detail.value }); },
  onCompletionNotes(event) { this.setData({ completionNotes: event.detail.value }); },
  onAnswerInput(event) {
    const index = Number(event.currentTarget.dataset.index);
    if (!Number.isInteger(index) || !this.data.completionAnswers[index]) return;
    this.setData({ [`completionAnswers[${index}].answer_value`]: event.detail.value, [`completionAnswers[${index}].answer_text`]: event.detail.value });
  },
  async submitCompletion() {
    const item = this.data.completionTarget;
    if (!item || this.data.busy) return;
    if (!this.reconcileIdentity()) return;
    const identityKey = this._identityKey;
    const result = String(this.data.completionResult || '').trim();
    if (!result) return this.setData({ error: '请填写随访结果。' });
    const missing = item.questions.some((question, index) => question.required && !String(this.data.completionAnswers[index].answer_value || '').trim());
    if (missing) return this.setData({ error: '请完成所有必填问题。' });
    this.setData({ busy: true, error: '', message: '' });
    try {
      await request(apiPath(`/health-records/followups/${encodeURIComponent(item.id)}/complete`), { method: 'POST', data: {
        expected_version: Number(item.mutation_version || 0),
        actual_date: new Date().toISOString(),
        answers: this.data.completionAnswers.map((answer) => ({ ...answer, answered_at: new Date().toISOString() })),
        follow_up_result: result,
        notes: String(this.data.completionNotes || '').trim() || undefined,
      }, header: { 'content-type': 'application/json' } });
      if (!this.reconcileIdentity(identityKey)) return;
      this.setData({ completionTarget: null, message: '随访结果已提交，当前状态为待医护审阅。' });
      await this.refreshFollowups();
    } catch (error) {
      if (!this.reconcileIdentity(identityKey)) return;
      if (error.statusCode === 401) this.clearSensitiveState('登录已失效，请重新登录后查看患者信息。');
      else this.setData({ error: errorText(error, '随访结果未提交，请刷新核对当前版本。') });
    }
    finally { if (this.isCurrentIdentity(identityKey)) this.setData({ busy: false }); }
  },
  async openReview(event) {
    const item = [...this.data.followups, ...this.data.overviewItems].find((row) => row.id === event.currentTarget.dataset.id);
    if (!item || !item.canReview || !this.reconcileIdentity()) return;
    const identityKey = this._identityKey, generation = ++this._reviewGeneration;
    this.setData({ reviewTarget: null, reviewComment: '', reviewEvidenceRows: [], reviewEvidenceError: '', reviewLoading: true, error: '' });
    let reviewed = null;
    try {
      const record = await request(`/health-records/followups/${encodeURIComponent(item.id)}`);
      if (generation !== this._reviewGeneration || !this.isCurrentIdentity(identityKey)) return;
      reviewed = this.formatFollowup(record);
      if (!reviewed.canReview || !Number.isInteger(reviewed.mutation_version)) throw new Error('随访状态或责任人已变化，请刷新后重新审阅。');
      let evidenceRows = [];
      if (reviewed.current_evidence && reviewed.current_evidence.source === 'external_form') {
        const ref = reviewed.effective_response;
        if (!ref || !ref.task_id || !ref.response_id) throw new Error('缺少可核实的答卷引用，不能批准。');
        let task, selfTask = false;
        try { task = await request(`/integrations/forms/fill-tasks/${encodeURIComponent(ref.task_id)}`); }
        catch (error) {
          if (error.statusCode !== 404) throw error;
          selfTask = true;
          task = await request(`/integrations/forms/patient-self/tasks/${encodeURIComponent(ref.task_id)}`);
        }
        if (generation !== this._reviewGeneration || !this.isCurrentIdentity(identityKey)) return;
        const confirmation = task && (task.confirmation || task.verifiedEvidence);
        const self = confirmation && confirmation.fill_mode === 'patient_self';
        const version = confirmation && confirmation.questionnaire_version_ref;
        const validSelf = !selfTask || (self && task.session && task.session.status === 'submitted' && task.session.sessionId
          && confirmation.session_uuid === task.session.sessionId && confirmation.is_voided === false && confirmation.user_id === null
          && version && task.remoteRefs && version.form_id === task.remoteRefs.questionnaire_id
          && Number.isInteger(version.form_id) && Number.isInteger(version.family_id) && Number.isInteger(version.version) && version.version > 0
          && /^[a-f0-9]{64}$/i.test(version.definition_sha256 || '') && /^[a-f0-9]{64}$/i.test(confirmation.snapshot_sha256 || '')
          && !!confirmation.verified_at && (!reviewed.visit_code || !confirmation.visit_code || reviewed.visit_code === confirmation.visit_code)
          && patientSelfSnapshotDigest(confirmation) === confirmation.snapshot_sha256.toLowerCase());
        const verified = task && String(task.id) === String(ref.task_id) && String(task.patientId) === String(reviewed.patient_id)
          && String(task.followupVisitId) === String(reviewed.id) && task.status === 'confirmed' && confirmation
          && String(confirmation.response_id) === String(ref.response_id)
          && ['submitted', 'restored'].includes(confirmation.remote_status) && !task.remoteQueryError
          && !['revoked', 'cancelled', 'expired', 'invalidated'].includes(task.remoteStatus || '')
          && Array.isArray(confirmation.answers) && confirmation.answers.length > 0
          && confirmation.answers.every(answer => answer && Number.isInteger(answer.question_id)
            && (answer.answer_text === null || typeof answer.answer_text === 'string')) && validSelf;
        if (!verified) throw new Error('无法核实本次答卷的回答快照，请先在完整工作台检查。');
        evidenceRows = confirmation.answers.map(answer => ({ question: `问题 ${valueText(answer.question_id, '未标识')}`,
          answer: lineText(answer.answer_text) || '未提供' }));
        if (confirmation.fill_mode === 'patient_self') reviewed.evidenceLabel = '患者本人填写的问卷';
        reviewed.canApprove = true;
      }
      this.setData({ reviewTarget: reviewed, reviewEvidenceRows: evidenceRows });
    } catch (error) {
      if (generation === this._reviewGeneration && this.isCurrentIdentity(identityKey)) {
        const message = errorText(error, '读取审阅证据失败，请重试。');
        if (reviewed && reviewed.canReview && Number.isInteger(reviewed.mutation_version)) {
          reviewed.canApprove = false;
          this.setData({ reviewTarget: reviewed, reviewEvidenceRows: [], reviewEvidenceError: message });
        } else this.setData({ error: message });
      }
    } finally { if (generation === this._reviewGeneration && this.isCurrentIdentity(identityKey)) this.setData({ reviewLoading: false }); }
  },
  closeReview() { this._reviewGeneration += 1; this.setData({ reviewTarget: null, reviewEvidenceRows: [], reviewEvidenceError: '', reviewLoading: false }); },
  onReviewComment(event) { this.setData({ reviewComment: event.detail.value }); },
  async submitReview(event) {
    const item = this.data.reviewTarget;
    const decision = event.currentTarget.dataset.decision;
    if (!item || !['approved', 'returned'].includes(decision) || this.data.busy) return;
    if (!this.reconcileIdentity()) return;
    const identityKey = this._identityKey;
    const comment = String(this.data.reviewComment || '').trim();
    if (decision === 'approved' && !item.canApprove) return this.setData({ error: '此条记录的证据类型需要在完整工作台核验；小程序不提供直接批准。' });
    if (decision === 'returned' && !comment) return this.setData({ error: '退回前请填写原因。' });
    this.setData({ busy: true, error: '', message: '' });
    try {
      await request(apiPath(`/health-records/followups/${encodeURIComponent(item.id)}/review`), { method: 'POST', data: {
        expected_version: Number(item.mutation_version), decision,
        ...(item.current_evidence && item.current_evidence.source === 'external_form' && item.effective_response ? { evidence: item.effective_response } : {}),
        ...(comment ? { comment } : {}),
      }, header: { 'content-type': 'application/json' } });
      if (!this.reconcileIdentity(identityKey)) return;
      this.setData({ reviewTarget: null, message: decision === 'approved' ? '随访审阅已通过。' : '随访已退回待重新填写。' });
      await this.refreshFollowups();
    } catch (error) {
      if (!this.reconcileIdentity(identityKey)) return;
      if (error.statusCode === 401) this.clearSensitiveState('登录已失效，请重新登录后查看患者信息。');
      else this.setData({ error: errorText(error, '审阅未保存，请刷新记录后重试。') });
    }
    finally { if (this.isCurrentIdentity(identityKey)) this.setData({ busy: false }); }
  },
  openReevaluate(event) {
    const item = [...this.data.followups, ...this.data.overviewItems].find((row) => row.id === event.currentTarget.dataset.id);
    if (!item || !item.canReevaluate) return;
    const now = new Date();
    const date = new Date(now.getTime() - now.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
    this.setData({ reevaluateTarget: item, reevaluateDate: date, reevaluateReason: '' });
  },
  closeReevaluate() { this.setData({ reevaluateTarget: null }); },
  onReevaluateDate(event) { this.setData({ reevaluateDate: event.detail.value }); },
  onReevaluateReason(event) { this.setData({ reevaluateReason: event.detail.value }); },
  async submitReevaluate() {
    const item = this.data.reevaluateTarget;
    if (!item || this.data.busy) return;
    if (!this.reconcileIdentity()) return;
    const identityKey = this._identityKey;
    if (!this.data.reevaluateDate) return this.setData({ error: '请选择复评计划日期。' });
    this.setData({ busy: true, error: '', message: '' });
    try {
      const date = new Date(`${this.data.reevaluateDate}T09:00:00`).toISOString();
      await request(apiPath(`/health-records/followups/${encodeURIComponent(item.id)}/re-evaluate`), { method: 'POST', data: {
        scheduled_date: date,
        ...(this.data.reevaluateReason.trim() ? { reason: this.data.reevaluateReason.trim() } : {}),
      }, header: { 'content-type': 'application/json' } });
      if (!this.reconcileIdentity(identityKey)) return;
      this.setData({ reevaluateTarget: null, message: '复评节点已建立，并关联到原随访。' });
      await this.refreshFollowups();
    } catch (error) {
      if (!this.reconcileIdentity(identityKey)) return;
      if (error.statusCode === 401) this.clearSensitiveState('登录已失效，请重新登录后查看患者信息。');
      else this.setData({ error: errorText(error, '复评未建立，请刷新节点状态后重试。') });
    }
    finally { if (this.isCurrentIdentity(identityKey)) this.setData({ busy: false }); }
  },
});

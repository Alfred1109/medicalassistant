const { request, getSession } = require('../../../services/api');
const { apiBaseUrl } = require('../../../config');

const labels = { assigned: '待患者填写', active: '患者填写中', revoking: '正在取消', revoke_failed: '取消未完成，请重试', revoked: '已取消', session_created: '会话已创建', waiting_fill: '等待填写', submitted: '已提交待核验', confirmed: '已核实待审阅', cancelled: '已取消', failed: '失败' };
const purposeLabels = { initial_assessment: '初评', followup: '随访', reassessment: '复评' };
const endpoint = (path) => path;

Page({
  data: {
    actorId: '', role: '', roleLabel: '', taskMode: 'staff', tasks: [], loading: false, saving: false, error: '', message: '',
    total: 0, skip: 0, limit: 50, hasMore: false, createOpen: false, candidateLoading: false,
    candidates: [], referenceOptions: [], formOptions: [], candidateTotal: 0, candidateSkip: 0, candidateLimit: 50, candidateHasMore: false,
    patientIndex: -1, referenceIndex: -1, formIndex: -1, followups: [], followupOptions: [{ id: '', description: '不关联随访' }],
    followupIndex: 0, followupLoading: false, followupError: '', followupSkip: 0, followupTotal: 0, followupHasMore: false, webviewUrl: '',
  },
  onLoad() {
    this._generation = 0;
    this._candidateGeneration = 0;
    this._followupGeneration = 0;
    this._followupPatientId = '';
    this._followupRetryReset = true;
    this._identityKey = '';
    this.syncIdentity();
  },
  onShow() {
    if (!this.syncIdentity()) return;
    if (!this.data.webviewUrl && !this.data.loading && !this.data.saving) this.loadTasks(true);
  },
  isCurrent(identityKey) {
    const session = getSession(), user = session && session.user;
    return !!(session && session.identityConfirmed && user && identityKey === this._identityKey &&
      identityKey === `${session.role}:${String(user.id || user.actor_id || '')}:${String(session.sessionId || '')}`);
  },
  selectMode(event) {
    const mode = event.currentTarget.dataset.mode;
    if (!['staff', 'patient'].includes(mode) || mode === this.data.taskMode || this.data.saving) return;
    this._generation += 1;
    this.setData({ taskMode: mode, tasks: [], skip: 0, hasMore: false, loading: false, error: '', message: '' });
    this.loadTasks(true);
  },
  syncIdentity() {
    const session = getSession();
    if (!session || !session.identityConfirmed || !session.user || !['doctor', 'health_manager'].includes(session.role)) {
      this.clearState('请登录已确认的医生或健康管理师账号。');
      return false;
    }
    const actorId = String(session.user.id || session.user.actor_id || '');
    if (!actorId) { this.clearState('账号信息无效，请重新登录。'); return false; }
    const identityKey = `${session.role}:${actorId}:${String(session.sessionId || '')}`;
    if (!actorId || !this.isCurrent(identityKey)) {
      this.clearState('账号已切换，已清除上一账号的问卷任务。');
      this._identityKey = identityKey;
      this.setData({ actorId, role: session.role, roleLabel: session.role === 'doctor' ? '医生' : '健康管理师', error: '' });
      this.loadTasks(true);
    }
    return true;
  },
  clearState(message) {
    this._generation += 1;
    this._candidateGeneration += 1;
    this._followupGeneration += 1;
    this._followupPatientId = '';
    this._followupRetryReset = true;
    this._identityKey = '';
    this.setData({ actorId: '', role: '', roleLabel: '', tasks: [], total: 0, skip: 0, hasMore: false,
      createOpen: false, candidates: [], referenceOptions: [], formOptions: [], candidateTotal: 0, candidateSkip: 0, candidateHasMore: false,
      patientIndex: -1, referenceIndex: -1, formIndex: -1, followups: [], followupOptions: [{ id: '', description: '不关联随访' }],
      followupSkip: 0, followupTotal: 0, followupHasMore: false, followupError: '',
      webviewUrl: '', loading: false, candidateLoading: false, followupLoading: false, saving: false,
      error: message || '登录已失效，请重新登录。', message: '' });
  },
  async loadTasks(reset = false) {
    if (this.data.loading) return;
    const generation = ++this._generation;
    const identityKey = this._identityKey;
    const skip = reset ? 0 : this.data.skip;
    this.setData({ loading: true, error: '' });
    try {
      const path = this.data.taskMode === 'patient' ? '/integrations/forms/patient-self/tasks' : '/integrations/forms/fill-tasks';
      const result = await request(endpoint(`${path}?skip=${skip}&limit=${this.data.limit}`));
      if (generation !== this._generation || !this.isCurrent(identityKey)) return;
      if (!result || !Array.isArray(result.items)) throw new Error('问卷任务列表格式异常。');
      const items = result.items.map((task) => ({ ...task, statusLabel: labels[task.status] || task.status,
        title: task.visitName || `问卷 ${task.remoteRefs && task.remoteRefs.questionnaire_id || ''}` }));
      this.setData({ tasks: reset ? items : this.data.tasks.concat(items), skip: skip + items.length,
        total: Number(result.total || 0), hasMore: skip + items.length < Number(result.total || 0) });
    } catch (error) {
      if (generation === this._generation && this.isCurrent(identityKey)) {
        if (error.statusCode === 401) this.clearState('登录已失效，请重新登录。');
        else this.setData({ error: error.message || '问卷任务加载失败。' });
      }
    } finally { if (generation === this._generation && this.isCurrent(identityKey)) this.setData({ loading: false }); }
  },
  async refresh() { await this.loadTasks(true); },
  async loadMore() { await this.loadTasks(false); },
  async openCreate() {
    if (this.data.candidateLoading || this.data.saving) return;
    const generation = ++this._candidateGeneration;
    this._followupGeneration += 1;
    this._followupPatientId = '';
    this._followupRetryReset = true;
    const identityKey = this._identityKey;
    this.setData({ createOpen: true, candidateLoading: true, error: '', patientIndex: -1, referenceIndex: -1, formIndex: -1, followups: [], followupOptions: [{ id: '', description: '不关联随访' }], followupIndex: 0, followupLoading: false, followupError: '', followupSkip: 0, followupTotal: 0, followupHasMore: false });
    try {
      const page = await request(endpoint('/integrations/forms/fill-candidates?skip=0&limit=50'));
      if (generation !== this._candidateGeneration || !this.isCurrent(identityKey)) return;
      if (!page || !Array.isArray(page.patients)) throw new Error('可填报患者目录格式异常。');
      this.setData({ candidates: page.patients, candidateTotal: Number(page.total || 0), candidateSkip: (page.skip || 0) + page.patients.length, candidateLimit: page.limit || 50, candidateHasMore: (page.skip || 0) + page.patients.length < Number(page.total || 0) });
    } catch (error) {
      if (generation === this._candidateGeneration && this.isCurrent(identityKey)) this.setData({ createOpen: false, error: error.message || '无法读取已审核的患者和问卷关联。' });
    } finally { if (generation === this._candidateGeneration && this.isCurrent(identityKey)) this.setData({ candidateLoading: false }); }
  },
  async loadMoreCandidates() {
    if (!this.data.candidateHasMore || this.data.candidateLoading) return;
    const generation = ++this._candidateGeneration;
    const identityKey = this._identityKey;
    this.setData({ candidateLoading: true });
    try {
      const page = await request(endpoint(`/integrations/forms/fill-candidates?skip=${this.data.candidateSkip}&limit=${this.data.candidateLimit}`));
      if (generation !== this._candidateGeneration || !this.isCurrent(identityKey)) return;
      if (!page || !Array.isArray(page.patients)) throw new Error('可填报患者目录格式异常。');
      this.setData({ candidates: this.data.candidates.concat(page.patients), candidateSkip: (page.skip || 0) + page.patients.length,
        candidateTotal: Number(page.total || 0), candidateHasMore: (page.skip || 0) + page.patients.length < Number(page.total || 0) });
    } catch (error) { if (generation === this._candidateGeneration && this.isCurrent(identityKey)) this.setData({ error: error.message || '无法加载更多可填报患者。' }); }
    finally { if (generation === this._candidateGeneration && this.isCurrent(identityKey)) this.setData({ candidateLoading: false }); }
  },
  closeCreate() {
    if (this.data.saving) return;
    this._followupGeneration += 1;
    this._followupPatientId = '';
    this.setData({ createOpen: false, followupLoading: false });
  },
  onPatientChange(event) {
    const patientIndex = Number(event.detail.value);
    const patient = this.data.candidates[patientIndex];
    const referenceOptions = (patient && Array.isArray(patient.references) ? patient.references : []).map((reference) => ({
      ...reference, display: `项目 ${reference.project_id} · 中心 ${reference.center_id} · 受试者 ${reference.subject_id}`,
    }));
    this.setData({ patientIndex, referenceIndex: -1, formIndex: -1, referenceOptions, formOptions: [], followups: [], followupOptions: [{ id: '', description: '不关联随访' }], followupIndex: 0 });
    return this.loadPatientFollowups(patient ? patient.patient_id : '');
  },
  onReferenceChange(event) {
    const referenceIndex = Number(event.detail.value);
    const patient = this.data.candidates[this.data.patientIndex];
    const reference = patient && patient.references[referenceIndex];
    const formOptions = (reference && Array.isArray(reference.forms) ? reference.forms : []).map((form) => ({
      ...form, display: `${form.title} · ${purposeLabels[form.purpose] || form.purpose} · 版本 ${form.version}`,
    }));
    this.setData({ referenceIndex, formIndex: -1, formOptions });
  },
  onFormChange(event) { this.setData({ formIndex: Number(event.detail.value) }); },
  onFollowupChange(event) { this.setData({ followupIndex: Number(event.detail.value) }); },
  async loadPatientFollowups(patientId, reset = true) {
    const generation = ++this._followupGeneration;
    this._followupPatientId = String(patientId || '');
    const identityKey = this._identityKey;
    if (!this._followupPatientId) {
      this._followupRetryReset = true;
      this.setData({ followups: [], followupOptions: [{ id: '', description: '不关联随访' }], followupIndex: 0, followupLoading: false, followupError: '', followupSkip: 0, followupTotal: 0, followupHasMore: false });
      return;
    }
    const skip = reset ? 0 : this.data.followupSkip;
    this._followupRetryReset = reset;
    this.setData({ followupLoading: true, followupError: '', ...(reset ? { followups: [], followupOptions: [{ id: '', description: '不关联随访' }], followupIndex: 0, followupSkip: 0, followupTotal: 0, followupHasMore: false } : {}) });
    try {
      const page = await request(endpoint(`/health-records/followup-workbench?patient_id=${encodeURIComponent(this._followupPatientId)}&skip=${skip}&limit=50`));
      if (generation !== this._followupGeneration || !this.isCurrent(identityKey) || this._followupPatientId !== String(patientId)) return;
      if (!page || !Array.isArray(page.items)) throw new Error('随访列表格式异常。');
      const items = page.items.filter((row) => !['completed', 'canceled', 'cancelled'].includes(row.status));
      const followups = reset ? items : this.data.followups.concat(items.filter((item) => !this.data.followups.some((current) => current.id === item.id)));
      const pageSkip = Number.isInteger(page.skip) ? page.skip : skip;
      const followupSkip = pageSkip + page.items.length;
      const followupTotal = Number(page.total || 0);
      this.setData({ followups, followupOptions: [{ id: '', description: '不关联随访' }, ...followups.map((item) => ({ id: item.id, description: item.description || item.id, visit_code: item.visit_code }))],
        followupSkip, followupTotal, followupHasMore: followupSkip < followupTotal });
    } catch (error) {
      if (generation === this._followupGeneration && this.isCurrent(identityKey) && this._followupPatientId === String(patientId)) {
        this.setData({ followupError: error.message || '读取关联随访失败，请重试。' });
      }
    } finally {
      if (generation === this._followupGeneration && this.isCurrent(identityKey) && this._followupPatientId === String(patientId)) this.setData({ followupLoading: false });
    }
  },
  async loadMorePatientFollowups() {
    if (!this.data.followupHasMore || this.data.followupLoading || !this._followupPatientId) return;
    await this.loadPatientFollowups(this._followupPatientId, false);
  },
  async retryPatientFollowups() {
    if (this.data.followupLoading || !this._followupPatientId) return;
    await this.loadPatientFollowups(this._followupPatientId, this._followupRetryReset);
  },
  async createTask() {
    const patient = this.data.candidates[this.data.patientIndex];
    const reference = patient && patient.references[this.data.referenceIndex];
    const form = reference && reference.forms[this.data.formIndex];
    if (!patient || !reference || !form || this.data.saving) return;
    if (!apiBaseUrl) return this.setData({ error: '尚未配置小程序 API 地址。' });
    const apiBase = new URL(apiBaseUrl);
    if (apiBase.protocol !== 'https:') return this.setData({ error: '填报任务需要 HTTPS 系统域名。' });
    const selectedFollowup = this.data.followupOptions[this.data.followupIndex];
    this.setData({ saving: true, error: '', message: '' });
    const identityKey = this._identityKey;
    try {
      const selfFill = this.data.taskMode === 'patient';
      const refs = { remote_project_id: reference.project_id, remote_center_id: reference.center_id,
        remote_subject_id: reference.subject_id, remote_questionnaire_id: form.form_id };
      await request(endpoint(selfFill ? '/integrations/forms/patient-self/tasks' : '/integrations/forms/fill-tasks'), { method: 'POST', data: {
        patient_id: patient.patient_id,
        ...refs,
        form_binding_id: form.binding_id,
        form_purpose: form.purpose,
        allowed_origin: apiBase.origin,
        ...(selectedFollowup && selectedFollowup.id ? { followup_visit_id: selectedFollowup.id, ...(selectedFollowup.visit_code ? { visit_code: selectedFollowup.visit_code } : {}) } : {}),
      }, header: { 'content-type': 'application/json' } });
      if (!this.isCurrent(identityKey)) return;
      this.setData({ createOpen: false, message: selfFill ? '已分配患者本人填写。' : '已按已审核的患者和问卷关联创建任务。' });
      await this.loadTasks(true);
    } catch (error) {
      if (this.isCurrent(identityKey)) {
        if (error.statusCode === 401) this.clearState('登录已失效，请重新登录。');
        else this.setData({ error: error.message || '创建问卷任务失败。' });
      }
    } finally { if (this.isCurrent(identityKey)) this.setData({ saving: false }); }
  },
  async launchTask(event) {
    const taskId = String(event.currentTarget.dataset.id || '');
    if (!taskId || this.data.saving) return;
    this.setData({ saving: true, error: '' });
    const identityKey = this._identityKey;
    try {
      const result = await request(endpoint(`/integrations/forms/fill-tasks/${encodeURIComponent(taskId)}/launch`), { method: 'POST' });
      if (!this.isCurrent(identityKey)) return;
      if (result.taskId !== taskId || typeof result.webviewUrl !== 'string') throw new Error('小程序未收到受信任的填报入口。');
      if (!apiBaseUrl) throw new Error('尚未配置小程序 API 地址。');
      const apiBase = new URL(apiBaseUrl);
      const launchUrl = new URL(result.webviewUrl);
      const expectedPrefix = `${apiBase.pathname.replace(/\/$/, '')}/integrations/forms/fill-tasks/launch-bridge/`;
      if (launchUrl.protocol !== 'https:' || launchUrl.origin !== apiBase.origin || !launchUrl.pathname.startsWith(expectedPrefix)
          || launchUrl.search || launchUrl.hash || !launchUrl.pathname.slice(expectedPrefix.length)) throw new Error('填报入口地址校验失败，已停止打开。');
      wx.navigateTo({ url: `/pages/clinical/tasks/webview/index?url=${encodeURIComponent(launchUrl.href)}&taskId=${encodeURIComponent(taskId)}` });
    } catch (error) {
      if (this.isCurrent(identityKey)) {
        if (error.statusCode === 401) this.clearState('登录已失效，请重新登录。');
        else this.setData({ error: error.message || '填报入口暂不可用。' });
      }
    } finally { if (this.isCurrent(identityKey)) this.setData({ saving: false }); }
  },
  async confirmTask(event) {
    const taskId = String(event.currentTarget.dataset.id || '');
    if (!taskId || this.data.saving) return;
    this.setData({ saving: true, error: '', message: '' });
    const identityKey = this._identityKey;
    try {
      const result = await request(endpoint(`/integrations/forms/fill-tasks/${encodeURIComponent(taskId)}/confirm`), { method: 'POST' });
      if (!this.isCurrent(identityKey)) return;
      if (result.status === 'confirmed') this.setData({ message: '远端已核实提交，随访节点进入待医护审阅。' });
      else this.setData({ message: '远端尚未核实到已提交答卷，可继续填写后再核实。' });
      await this.loadTasks(true);
    } catch (error) {
      if (this.isCurrent(identityKey)) {
        if (error.statusCode === 401) this.clearState('登录已失效，请重新登录。');
        else this.setData({ error: error.message || '核实失败；请确认远端答卷状态。' });
      }
    } finally { if (this.isCurrent(identityKey)) this.setData({ saving: false }); }
  },
  cancelTask(event) {
    const taskId = String(event.currentTarget.dataset.id || ''), identityKey = this._identityKey;
    if (!taskId || this.data.saving) return;
    wx.showModal({ title: '取消问卷任务', content: '确认取消？源端会话会同步作废，已核实提交的任务不能取消。',
      confirmText: '确认取消', cancelText: '返回', success: (result) => { if (result.confirm && this.isCurrent(identityKey)) this.performCancel(taskId); } });
  },
  revokePatientTask(event) {
    const taskId = String(event.currentTarget.dataset.id || ''), identityKey = this._identityKey;
    if (!taskId || this.data.saving || !this.isCurrent(identityKey)) return;
    wx.showModal({ title: '取消患者问卷', content: '确认取消分配？患者将不能继续填写。', success: async result => {
      if (!result.confirm || !this.isCurrent(identityKey)) return;
      this.setData({ saving: true, error: '' });
      try {
        await request(`/integrations/forms/patient-self/tasks/${encodeURIComponent(taskId)}/revoke`, { method: 'POST', data: { reason: '医护取消分配' } });
        if (this.isCurrent(identityKey)) { this.setData({ message: '取消请求已处理。' }); await this.loadTasks(true); }
      } catch (error) { if (this.isCurrent(identityKey)) this.setData({ error: error.message || '取消失败，请重试。' }); }
      finally { if (this.isCurrent(identityKey)) this.setData({ saving: false }); }
    } });
  },
  async refreshPatientTask(event) {
    const taskId = String(event.currentTarget.dataset.id || ''), identityKey = this._identityKey;
    if (!taskId || this.data.saving || !this.isCurrent(identityKey)) return;
    this.setData({ saving: true, error: '' });
    try {
      await request(`/integrations/forms/patient-self/tasks/${encodeURIComponent(taskId)}`);
      if (this.isCurrent(identityKey)) { this.setData({ message: '已核实源端提交状态。' }); await this.loadTasks(true); }
    } catch (error) { if (this.isCurrent(identityKey)) this.setData({ error: error.message || '核实状态失败。' }); }
    finally { if (this.isCurrent(identityKey)) this.setData({ saving: false }); }
  },
  async confirmPatientTask(event) {
    const taskId = String(event.currentTarget.dataset.id || ''), identityKey = this._identityKey;
    if (!taskId || this.data.saving || !this.isCurrent(identityKey)) return;
    this.setData({ saving: true, error: '' });
    try {
      const result = await request(`/integrations/forms/patient-self/tasks/${encodeURIComponent(taskId)}/confirm`, { method: 'POST' });
      if (!this.isCurrent(identityKey)) return;
      this.setData({ message: result.followupVisitId ? '患者答卷已核验，请到随访记录中审阅。' : '患者答卷已核验。' });
      await this.loadTasks(true);
    } catch (error) { if (this.isCurrent(identityKey)) this.setData({ error: error.message || '答卷核验失败，请重试。' }); }
    finally { if (this.isCurrent(identityKey)) this.setData({ saving: false }); }
  },
  async performCancel(taskId) {
    this.setData({ saving: true, error: '' });
    const identityKey = this._identityKey;
    try {
      await request(endpoint(`/integrations/forms/fill-tasks/${encodeURIComponent(taskId)}/cancel`), { method: 'POST' });
      if (!this.isCurrent(identityKey)) return;
      this.setData({ message: '任务已取消，源端会话已作废。' });
      await this.loadTasks(true);
    } catch (error) {
      if (this.isCurrent(identityKey)) {
        if (error.statusCode === 401) this.clearState('登录已失效，请重新登录。');
        else this.setData({ error: error.message || '取消任务失败。' });
      }
    } finally { if (this.isCurrent(identityKey)) this.setData({ saving: false }); }
  },
  closeWebview() { this.setData({ webviewUrl: '' }); wx.navigateBack(); },
  openTasks() { wx.navigateTo({ url: '/pages/clinical/tasks/index' }); },
});

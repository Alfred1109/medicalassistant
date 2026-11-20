const { request, getSession, getAccessToken } = require('../../../services/api');

const statusLabels = { completed: '已执行', partial: '部分执行', not_done: '未执行' };
const reviewLabels = { pending: '待核验', verified: '核验通过', return_for_supplement: '退回补充' };
const idOf = (row) => String(row && (row.id || row._id) || '');
const requestId = () => `cycle-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
const reviewAttachments = (row) => [
  ...(row.attachments || []).map(attachment => ({ ...attachment, sourceLabel: '患者训练视频' })),
  ...(row.supplements || []).flatMap(supplement => (supplement.attachments || []).map(attachment => ({
    ...attachment, sourceLabel: `补充材料${supplement.submitted_at ? ` · ${supplement.submitted_at}` : ''}`, supplementNote: supplement.note || '',
  }))),
].filter(attachment => String(attachment.content_type || '').startsWith('video/'));
const otherAttachments = (row) => [
  ...(row.attachments || []), ...(row.supplements || []).flatMap(supplement => supplement.attachments || []),
].filter(attachment => !String(attachment.content_type || '').startsWith('video/')).map(attachment => attachment.name).filter(Boolean).join('、');

Page({
  data: {
    patientId: '', patientName: '', plans: [], selectedPlanId: '', selectedPlanName: '', selectedPlanIndex: 0,
    cycles: [], feedback: [], feedbackSkip: 0, feedbackHasMore: false,
    loading: false, saving: false, error: '', message: '', cycleTitle: '', cycleStart: '', cycleEnd: '',
    cycleNotes: {}, editingCycle: null,
  },
  onLoad(options) {
    this._generation = 0;
    this._identity = this.identity();
    const patientId = String(options.patientId || '');
    if (!this._identity) return this.setData({ error: '请先使用已确认的医生或健康管理师账号登录。' });
    if (!patientId) return this.setData({ error: '缺少患者信息，请从授权患者档案进入。' });
    let patientName = String(options.patientName || '');
    try { patientName = decodeURIComponent(patientName); } catch (_) {}
    this.setData({ patientId, patientName });
    this.loadPlans();
  },
  onShow() {
    if (!this._identity || this.identity() !== this._identity) this.clearForIdentityChange();
  },
  onUnload() { this.abortVideoDownloads(); this._generation += 1; },
  abortVideoDownloads() {
    (this._videoDownloads || []).forEach(task => { if (task && typeof task.abort === 'function') task.abort(); });
    this._videoDownloads = [];
  },
  identity() {
    const session = getSession();
    if (!session || !session.identityConfirmed || !['doctor', 'health_manager'].includes(session.role)) return '';
    const user = session.user || {};
    const actorId = String(user.id || user.actor_id || '');
    return actorId ? `${session.role}:${actorId}:${session.sessionId || ''}` : '';
  },
  clearForIdentityChange() {
    this.abortVideoDownloads();
    this._generation += 1;
    this._identity = '';
    this.setData({ patientId: '', patientName: '', plans: [], cycles: [], feedback: [], selectedPlanId: '', selectedPlanName: '', selectedPlanIndex: 0, feedbackSkip: 0, feedbackHasMore: false,
      cycleNotes: {}, editingCycle: null, cycleTitle: '', cycleStart: '', cycleEnd: '', loading: false, saving: false, message: '', error: '登录身份已变化，请返回并重新进入。' });
  },
  current(generation) {
    return !!this._identity && this.identity() === this._identity && generation === this._generation;
  },
  async loadPlans() {
    const generation = ++this._generation;
    this.setData({ loading: true, error: '', message: '' });
    try {
      const plans = await request(`/rehabilitation/plans?patient_id=${encodeURIComponent(this.data.patientId)}&skip=0&limit=100`);
      if (!this.current(generation)) return;
      if (!Array.isArray(plans)) throw new Error('康复方案响应格式异常。');
      const visiblePlans = plans.filter(plan => plan && plan.status !== 'draft' && idOf(plan)).map(plan => ({ ...plan,
        displayName: `${plan.name || plan.content?.name || '康复方案'}${plan.status && plan.status !== 'active' ? '（历史）' : ''}`,
      }));
      this.setData({ plans: visiblePlans, selectedPlanId: '', selectedPlanName: '', selectedPlanIndex: 0, cycles: [], feedback: [] });
      if (visiblePlans.length) await this.selectPlan({ currentTarget: { dataset: { id: idOf(visiblePlans[0]) } } });
      else this.setData({ message: '该患者暂无可管理的康复方案。' });
    } catch (error) {
      if (this.current(generation)) this.setData({ error: error.message || '康复方案加载失败，请重试。' });
    } finally {
      if (this.current(generation)) this.setData({ loading: false });
    }
  },
  async selectPlan(event) {
    const planId = String(event.currentTarget.dataset.id || '');
    const plan = this.data.plans.find(row => idOf(row) === planId);
    if (!plan) return;
    this.abortVideoDownloads();
    const generation = ++this._generation;
    this.setData({ selectedPlanId: planId, selectedPlanName: plan.name || plan.content?.name || '康复方案', selectedPlanIndex: this.data.plans.findIndex(row => idOf(row) === planId), cycles: [], feedback: [], feedbackSkip: 0, feedbackHasMore: false, loading: true, error: '', message: '', cycleNotes: {}, editingCycle: null, cycleTitle: '', cycleStart: '', cycleEnd: '' });
    try {
      const [cycles, feedback] = await Promise.all([
        request(`/rehabilitation/plans/${encodeURIComponent(planId)}/training-cycles`),
        request(`/rehabilitation/plans/${encodeURIComponent(planId)}/patient-feedback?skip=0&limit=20`),
      ]);
      if (!this.current(generation)) return;
      if (!cycles || !Array.isArray(cycles.items) || !feedback || !Array.isArray(feedback.items) || typeof feedback.total !== 'number') throw new Error('训练记录响应格式异常。');
      const today = new Intl.DateTimeFormat('sv-SE', { timeZone: 'Asia/Shanghai' }).format(new Date());
      const cycleRows = cycles.items.map(cycle => ({ ...cycle,
        canAccept: cycle.status === 'open' && cycle.end_date < today && !(cycle.pending_reviews_count > 0),
        canEdit: cycle.status === 'open' && cycle.start_date > today && cycle.feedback_count === 0,
      }));
      const rows = feedback.items.map(row => ({ ...row, reviewAttachments: reviewAttachments(row), otherAttachmentNames: otherAttachments(row), hasVideo: reviewAttachments(row).length > 0,
        canReview: (row.clinical_review?.status || 'pending') === 'pending' && row.intervention_type === 'exercise' && ['completed', 'partial'].includes(row.execution_status),
        executionLabel: statusLabels[row.execution_status] || '执行情况未知', reviewLabel: reviewLabels[row.clinical_review?.status] || (row.intervention_type === 'exercise' && ['completed', 'partial'].includes(row.execution_status) ? '待核验' : '无需视频核验'),
        note: '', videos: [], videoReady: false, videoLoading: false, videoError: '' }));
      this.setData({ cycles: cycleRows, feedback: rows, feedbackSkip: rows.length, feedbackHasMore: rows.length < feedback.total, error: '' });
    } catch (error) {
      if (this.current(generation)) this.setData({ error: error.message || '训练记录加载失败，请重试。' });
    } finally {
      if (this.current(generation)) this.setData({ loading: false });
    }
  },
  onPlanChange(event) {
    const plan = this.data.plans[Number(event.detail.value)];
    if (plan) this.selectPlan({ currentTarget: { dataset: { id: idOf(plan) } } });
  },
  async loadFeedbackVideos(event) {
    const index = Number(event.currentTarget.dataset.index);
    const row = this.data.feedback[index];
    if (!row || row.videoLoading || row.videoReady || !row.reviewAttachments.length) return;
    const generation = this._generation;
    const token = getAccessToken();
    if (!token) return this.markVideoError(generation, index, '登录状态已失效，请重新登录后核验视频。');
    this.setData({ [`feedback[${index}].videoLoading`]: true, [`feedback[${index}].videoError`]: '' });
    const videos = [];
    try {
      for (const [attachmentIndex, attachment] of row.reviewAttachments.entries()) {
        const url = await this.downloadVideo(generation, this.data.selectedPlanId, attachment, token);
        if (!this.current(generation)) return;
        videos[attachmentIndex] = { ...attachment, url };
      }
      this.setData({ [`feedback[${index}].videos`]: videos, [`feedback[${index}].videoReady`]: videos.length === row.reviewAttachments.length,
        [`feedback[${index}].videoLoading`]: false, [`feedback[${index}].videoError`]: '' });
    } catch (error) {
      this.markVideoError(generation, index, error.message || '训练视频加载失败，暂不能核验。');
    }
  },
  downloadVideo(generation, planId, attachment, token) {
    if (!attachment || !attachment.id) return Promise.reject(new Error('训练视频附件信息无效。'));
    const base = require('../../../config').apiBaseUrl.replace(/\/+$/, '');
    return new Promise((resolve, reject) => {
      const task = wx.downloadFile({
        url: `${base}/rehabilitation/plans/${encodeURIComponent(planId)}/patient-feedback/media/${encodeURIComponent(attachment.id)}`,
        header: { Authorization: `Bearer ${token}` },
        success: result => {
          if (!this.current(generation)) return reject(new Error('登录状态已变化，视频未加载。'));
          if (result.statusCode !== 200 || !result.tempFilePath) return reject(new Error('训练视频加载失败，暂不能核验。'));
          resolve(result.tempFilePath);
        },
        fail: () => reject(new Error('训练视频加载失败，暂不能核验。')),
      });
      if (task) (this._videoDownloads || (this._videoDownloads = [])).push(task);
    });
  },
  markVideoError(generation, index, message) {
    if (!this.current(generation)) return;
    const feedback = this.data.feedback.slice();
    if (!feedback[index]) return;
    feedback[index] = { ...feedback[index], videoLoading: false, videoError: message };
    this.setData({ feedback });
  },
  async loadMoreFeedback() {
    if (!this.data.feedbackHasMore || this.data.loading) return;
    const generation = this._generation;
    const planId = this.data.selectedPlanId;
    this.setData({ loading: true, error: '' });
    try {
      const page = await request(`/rehabilitation/plans/${encodeURIComponent(planId)}/patient-feedback?skip=${this.data.feedbackSkip}&limit=20`);
      if (!this.current(generation)) return;
      if (!page || !Array.isArray(page.items)) throw new Error('训练反馈响应格式异常。');
      const additions = page.items.map(row => ({ ...row, reviewAttachments: reviewAttachments(row), otherAttachmentNames: otherAttachments(row), hasVideo: reviewAttachments(row).length > 0,
        canReview: (row.clinical_review?.status || 'pending') === 'pending' && row.intervention_type === 'exercise' && ['completed', 'partial'].includes(row.execution_status),
        executionLabel: statusLabels[row.execution_status] || '执行情况未知', reviewLabel: reviewLabels[row.clinical_review?.status] || (row.intervention_type === 'exercise' && ['completed', 'partial'].includes(row.execution_status) ? '待核验' : '无需视频核验'),
        note: '', videos: [], videoReady: false, videoLoading: false, videoError: '' }));
      const feedback = this.data.feedback.concat(additions);
      this.setData({ feedback, feedbackSkip: feedback.length, feedbackHasMore: feedback.length < page.total });
    } catch (error) {
      if (this.current(generation)) this.setData({ error: error.message || '加载更多训练反馈失败。' });
    } finally { if (this.current(generation)) this.setData({ loading: false }); }
  },
  onCycleTitle(event) { this.setData({ cycleTitle: event.detail.value }); },
  onCycleStart(event) { this.setData({ cycleStart: event.detail.value }); },
  onCycleEnd(event) { this.setData({ cycleEnd: event.detail.value }); },
  editCycle(event) {
    const cycle = this.data.cycles[Number(event.currentTarget.dataset.index)];
    if (!cycle || !cycle.canEdit) return;
    this.setData({ editingCycle: cycle, cycleTitle: cycle.title, cycleStart: cycle.start_date, cycleEnd: cycle.end_date, error: '', message: '' });
  },
  cancelCycleEdit() { this.setData({ editingCycle: null, cycleTitle: '', cycleStart: '', cycleEnd: '' }); },
  async createCycle() {
    const { cycleTitle, cycleStart, cycleEnd, selectedPlanId } = this.data;
    if (!cycleTitle.trim() || !cycleStart || !cycleEnd || cycleEnd < cycleStart) return this.setData({ error: '请填写周期名称和有效的起止日期。' });
    if (this.data.editingCycle) {
      const cycle = this.data.editingCycle;
      await this.mutate(`/rehabilitation/plans/${encodeURIComponent(selectedPlanId)}/training-cycles/${encodeURIComponent(cycle.id)}`, {
        method: 'PUT', data: { request_id: requestId(), expected_revision: cycle.revision, title: cycleTitle.trim(), start_date: cycleStart, end_date: cycleEnd },
      }, '训练周期已调整。', { editingCycle: null, cycleTitle: '', cycleStart: '', cycleEnd: '' });
      return;
    }
    await this.mutate(`/rehabilitation/plans/${encodeURIComponent(selectedPlanId)}/training-cycles`, {
      method: 'POST', data: { request_id: requestId(), title: cycleTitle.trim(), start_date: cycleStart, end_date: cycleEnd },
    }, '训练周期已保存。', { cycleTitle: '', cycleStart: '', cycleEnd: '' });
  },
  onReviewNote(event) { this.setData({ [`feedback[${Number(event.currentTarget.dataset.index)}].note`]: event.detail.value }); },
  async reviewFeedback(event) {
    const index = Number(event.currentTarget.dataset.index);
    const row = this.data.feedback[index];
    const status = String(event.currentTarget.dataset.status || '');
    const note = String(row && row.note || '').trim();
    if (!row || !['verified', 'return_for_supplement'].includes(status)) return;
    if (!row.canReview || (row.clinical_review?.status && row.clinical_review.status !== 'pending')) return this.setData({ error: '此反馈当前不处于待核验状态，请刷新后查看。' });
    if (status === 'verified' && (!row.videoReady || !row.hasVideo)) return this.setData({ error: '核验通过前请先加载并确认训练视频。' });
    if (status === 'return_for_supplement' && !note) return this.setData({ error: '退回补充时请填写原因。' });
    await this.mutate(`/rehabilitation/plans/${encodeURIComponent(this.data.selectedPlanId)}/patient-feedback/${encodeURIComponent(row.id)}/review`, {
      method: 'POST', data: { expected_revision: Number(row.clinical_review?.revision || 0), status, note },
    }, status === 'verified' ? '视频已核验。' : '已退回患者补充。');
  },
  onCycleNote(event) { this.setData({ [`cycleNotes.${event.currentTarget.dataset.id}`]: event.detail.value }); },
  async acceptCycle(event) {
    const cycle = this.data.cycles[Number(event.currentTarget.dataset.index)];
    if (!cycle || cycle.status !== 'open') return;
    const cycleNote = String(this.data.cycleNotes[cycle.id] || '').trim();
    if (!cycleNote) return this.setData({ error: '请填写周期验收记录。' });
    const today = new Intl.DateTimeFormat('sv-SE', { timeZone: 'Asia/Shanghai' }).format(new Date());
    if (cycle.end_date >= today) return this.setData({ error: '周期最后一天结束后才能统一验收。' });
    if (cycle.pending_reviews_count > 0) return this.setData({ error: '请先核验周期内所有训练视频。' });
    await this.mutate(`/rehabilitation/plans/${encodeURIComponent(this.data.selectedPlanId)}/training-cycles/${encodeURIComponent(cycle.id)}/acceptance`, {
      method: 'POST', data: { request_id: requestId(), expected_revision: cycle.revision, note: cycleNote },
    }, '训练周期已验收。', { [`cycleNotes.${cycle.id}`]: '' });
  },
  async mutate(path, options, message, cleared = {}) {
    if (!this._identity || this.identity() !== this._identity) { this.clearForIdentityChange(); return; }
    if (this.data.saving || !this.data.selectedPlanId) return;
    const generation = this._generation;
    this.setData({ saving: true, error: '', message: '' });
    try {
      await request(path, options);
      if (!this.current(generation)) return;
      this.setData({ ...cleared, message });
      await this.selectPlan({ currentTarget: { dataset: { id: this.data.selectedPlanId } } });
      if (this.identity() === this._identity) this.setData({ message });
    } catch (error) {
      if (this.current(generation)) this.setData({ error: error.message || '保存失败，请检查内容后重试。' });
    } finally { if (this.current(generation) || this.identity() === this._identity) this.setData({ saving: false }); }
  },
  onPullDownRefresh() { this.loadPlans().finally(() => wx.stopPullDownRefresh()); },
});

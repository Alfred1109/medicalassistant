const { request, uploadFile, getSession } = require('../../../services/api');
const sessionKey = (session) => `${String(session && session.user && (session.user.id || session.user.actor_id) || '')}|${String(session && session.sessionId || '')}`;
const sameSession = (expected) => {
  const current = getSession() || {};
  return !!(current.identityConfirmed && current.role === 'patient' && sessionKey(current) === sessionKey(expected));
};

function eventId() {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (char) => {
    const random = Math.floor(Math.random() * 16);
    return (char === 'x' ? random : ((random & 3) | 8)).toString(16);
  });
}
const feedbackStatusLabels = { completed: '已完成', partial: '部分完成', not_done: '未完成' };
const reviewStatusLabels = { pending: '待医护核验', verified: '核验通过', return_for_supplement: '请补充材料' };

Page({
  data: {
    planId: '', plan: null, feedback: [], trainingCycles: [], cycleLoading: false, cycleError: '', loading: false, loaded: false, submitting: false,
    error: '', feedbackError: '', feedbackSkip: 0, feedbackHasMore: false, feedbackLoading: false, selectedItemIndex: 0, selectedStatusIndex: 0,
    statusOptions: ['已完成', '部分完成', '未完成'], statusValues: ['completed', 'partial', 'not_done'], feelings: '',
    selectedVideoPath: '', selectedVideoName: '',
  },
  onLoad(options) { this.setData({ planId: String(options.plan_id || '') }); },
  onShow() {
    const session = getSession() || {};
    if (!session.identityConfirmed || session.role !== 'patient') {
      this._sessionKey = '';
      this._pendingFeedback = null;
      this.setData({ plan: null, feedback: [], trainingCycles: [], cycleLoading: false, cycleError: '', loaded: true, loading: false, submitting: false, feedbackLoading: false, feedbackSkip: 0, feedbackHasMore: false, error: '请先使用患者账号登录并确认身份。', feedbackError: '', feelings: '', selectedVideoPath: '', selectedVideoName: '' });
      return;
    }
    const key = sessionKey(session);
    if (this._sessionKey !== key) {
      this._pendingFeedback = null;
      this.setData({ plan: null, feedback: [], trainingCycles: [], cycleLoading: false, cycleError: '', loaded: false, loading: false, submitting: false, feedbackLoading: false, feedbackSkip: 0, feedbackHasMore: false, error: '', feedbackError: '', feelings: '', selectedVideoPath: '', selectedVideoName: '' });
    }
    this._sessionKey = key;
    this.loadPlan(session);
  },
  onPullDownRefresh() { this.loadPlan().finally(() => wx.stopPullDownRefresh()); },
  async loadPlan(session = getSession() || {}) {
    if (!session.identityConfirmed || session.role !== 'patient') return this.setData({ plan: null, feedback: [], loaded: true, error: '请先使用患者账号登录并确认身份。' });
    if (this.data.loading) return;
    if (!this.data.planId) return this.setData({ loaded: true, error: '方案标识缺失，请返回列表重试。' });
    this.setData({ loading: true, error: '', feedbackError: '' });
    try {
      const plan = await request(`/rehabilitation/publications/my-plans/${encodeURIComponent(this.data.planId)}`);
      if (!sameSession(session)) return;
      this.setData({ plan, loaded: true });
      this.loadTrainingCycles(session);
      await this.loadFeedback(session, true);
    } catch (error) {
      if (!sameSession(session)) return;
      this.setData({ loaded: true, error: error.message || '暂时无法读取康复方案。' });
    } finally { if (sameSession(session)) this.setData({ loading: false }); }
  },
  async loadTrainingCycles(session = getSession() || {}) {
    if (!this.data.planId || !session.identityConfirmed || session.role !== 'patient') return;
    this.setData({ cycleLoading: true, cycleError: '' });
    try {
      const result = await request(`/rehabilitation/plans/${encodeURIComponent(this.data.planId)}/training-cycles`);
      if (!sameSession(session)) return;
      if (!result || !Array.isArray(result.items) || typeof result.total !== 'number' || result.total < result.items.length) throw new Error('训练周期响应格式异常');
      this.setData({ trainingCycles: result.items, cycleError: '' });
    } catch (error) {
      if (!sameSession(session)) return;
      this.setData({ cycleError: error.message || '暂时无法读取训练周期。' });
    } finally { if (sameSession(session)) this.setData({ cycleLoading: false }); }
  },
  async loadFeedback(session = getSession() || {}, reset = true) {
    const plan = this.data.plan;
    if (!plan || !plan.version_id || this.data.feedbackLoading) return;
    const skip = reset ? 0 : this.data.feedbackSkip;
    this.setData({ feedbackLoading: true });
    try {
      const query = `skip=${skip}&limit=100`;
      const result = await request(`/rehabilitation/plans/${encodeURIComponent(this.data.planId)}/patient-feedback?${query}`);
      if (!sameSession(session)) return;
      if (!result || !Array.isArray(result.items) || typeof result.total !== 'number') throw new Error('反馈列表格式异常。');
      const rows = result.items.map(item => {
        const currentVersion = item.version_id === plan.version_id;
        const prescription = currentVersion && (plan.items || []).find(entry => entry.item_id === item.prescription_item_id);
        const interventionType = item.intervention_type || (currentVersion && prescription && prescription.intervention_type);
        const needsTrainingReview = interventionType === 'exercise'
          && ['completed', 'partial'].includes(item.execution_status);
        return { ...item,
        needsTrainingReview: Boolean(needsTrainingReview),
        statusLabel: feedbackStatusLabels[item.execution_status] || item.execution_status || '未记录',
        reviewStatusLabel: needsTrainingReview
          ? (reviewStatusLabels[item.clinical_review && item.clinical_review.status] || '待医护核验') : '',
        supplements: (item.supplements || []).map(supplement => ({ ...supplement,
          attachmentNames: (supplement.attachments || []).map(attachment => attachment.name).filter(Boolean).join('、'),
        })),
        supplementVideoPath: '', supplementVideoName: '', supplementNote: '', supplementSubmitting: false, supplementError: '',
      }; });
      this.setData({ feedback: reset ? rows : this.data.feedback.concat(rows), feedbackSkip: skip + rows.length,
        feedbackHasMore: skip + rows.length < result.total, feedbackError: '' });
    } catch (error) {
      if (!sameSession(session)) return;
      this.setData({ feedbackError: error.message || '暂时无法读取执行反馈。' });
    } finally { if (sameSession(session)) this.setData({ feedbackLoading: false }); }
  },
  loadMoreFeedback() { return this.loadFeedback(getSession() || {}, false); },
  updateFeedbackRow(index, patch) {
    const feedback = this.data.feedback.slice();
    if (!feedback[index]) return;
    feedback[index] = { ...feedback[index], ...patch };
    this.setData({ feedback });
  },
  chooseSupplementVideo(event) {
    const index = Number(event.currentTarget.dataset.index);
    const session = getSession() || {};
    if (!session.identityConfirmed || session.role !== 'patient') return wx.showToast({ title: '请先使用患者账号登录', icon: 'none' });
    if (!wx.chooseMedia) return wx.showToast({ title: '当前微信版本不支持选择视频', icon: 'none' });
    wx.chooseMedia({ count: 1, mediaType: ['video'], sourceType: ['album', 'camera'], maxDuration: 300,
      success: result => {
        if (!sameSession(session)) return;
        const file = result.tempFiles && result.tempFiles[0];
        if (!file || !file.tempFilePath) return;
        const name = String(file.tempFilePath).split('/').pop() || '补充训练视频';
        if (!['mp4', 'webm'].includes(name.split('.').pop().toLowerCase())) return wx.showToast({ title: '请选取 MP4 或 WebM 视频', icon: 'none' });
        if (Number(file.size) > 20 * 1024 * 1024) return wx.showToast({ title: '视频不能超过 20 MB', icon: 'none' });
        this._pendingSupplements = this._pendingSupplements || {};
        delete this._pendingSupplements[this.data.feedback[index].id];
        this.updateFeedbackRow(index, { supplementVideoPath: file.tempFilePath, supplementVideoName: name, supplementError: '' });
      },
    });
  },
  onSupplementNoteInput(event) { this.updateFeedbackRow(Number(event.currentTarget.dataset.index), { supplementNote: event.detail.value }); },
  async submitSupplement(event) {
    const index = Number(event.currentTarget.dataset.index);
    const feedback = this.data.feedback[index];
    const session = getSession() || {};
    if (!feedback || !session.identityConfirmed || session.role !== 'patient') return;
    const note = String(feedback.supplementNote || '').trim();
    if (!note) return wx.showToast({ title: '请填写补充说明', icon: 'none' });
    if (!feedback.supplementVideoPath) return wx.showToast({ title: '请选择补充训练视频', icon: 'none' });
    this._pendingSupplements = this._pendingSupplements || {};
    const fingerprint = JSON.stringify([sessionKey(session), this.data.planId, feedback.id, note, feedback.supplementVideoPath]);
    let pending = this._pendingSupplements[feedback.id];
    if (!pending || pending.fingerprint !== fingerprint) {
      pending = { fingerprint, event_id: eventId(), media_ids: [], uploadedPath: '' };
      this._pendingSupplements[feedback.id] = pending;
    }
    this.updateFeedbackRow(index, { supplementSubmitting: true, supplementError: '' });
    try {
      if (!pending.media_ids.length) {
        const media = await uploadFile(`/rehabilitation/plans/${encodeURIComponent(this.data.planId)}/patient-feedback/media`, feedback.supplementVideoPath);
        if (!sameSession(session)) return;
        if (!media || !media.id || !['video/mp4', 'video/webm'].includes(media.content_type)) throw new Error('视频上传结果无效，请重新选择后重试。');
        pending.media_ids = [media.id]; pending.uploadedPath = feedback.supplementVideoPath;
      }
      await request(`/rehabilitation/plans/${encodeURIComponent(this.data.planId)}/patient-feedback/${encodeURIComponent(feedback.id)}/supplements`, {
        method: 'POST', data: { event_id: pending.event_id, note, media_ids: pending.media_ids },
        header: { 'content-type': 'application/json' },
      });
      if (!sameSession(session)) return;
      delete this._pendingSupplements[feedback.id];
      this.updateFeedbackRow(index, { supplementSubmitting: false, supplementError: '', supplementNote: '', supplementVideoPath: '', supplementVideoName: '' });
      await this.loadFeedback(session, true);
    } catch (error) {
      if (!sameSession(session)) return;
      this.updateFeedbackRow(index, { supplementSubmitting: false, supplementError: error.message || '补充材料提交失败，请重试。' });
    }
  },
  onItemChange(event) { this._pendingFeedback = null; this.setData({ selectedItemIndex: Number(event.detail.value), selectedVideoPath: '', selectedVideoName: '' }); },
  onStatusChange(event) { this._pendingFeedback = null; this.setData({ selectedStatusIndex: Number(event.detail.value) }); },
  onFeelingsInput(event) { this.setData({ feelings: event.detail.value }); },
  chooseTrainingVideo() {
    const session = getSession() || {};
    if (!session.identityConfirmed || session.role !== 'patient') return wx.showToast({ title: '请先使用患者账号登录', icon: 'none' });
    if (!wx.chooseMedia) return wx.showToast({ title: '当前微信版本不支持选择视频', icon: 'none' });
    wx.chooseMedia({ count: 1, mediaType: ['video'], sourceType: ['album', 'camera'], maxDuration: 300,
      success: result => {
        if (!sameSession(session)) return;
        const file = result.tempFiles && result.tempFiles[0];
        if (!file || !file.tempFilePath) return;
        const name = String(file.tempFilePath).split('/').pop() || '训练视频';
        const ext = name.split('.').pop().toLowerCase();
        if (!['mp4', 'webm'].includes(ext)) return wx.showToast({ title: '请选取 MP4 或 WebM 视频', icon: 'none' });
        if (Number(file.size) > 20 * 1024 * 1024) return wx.showToast({ title: '视频不能超过 20 MB', icon: 'none' });
        this._pendingFeedback = null;
        this.setData({ selectedVideoPath: file.tempFilePath, selectedVideoName: name });
      },
    });
  },
  async submitFeedback() {
    const session = getSession() || {};
    if (!session.identityConfirmed || session.role !== 'patient') return this.setData({ plan: null, feedback: [], error: '登录状态已失效，请重新登录。' });
    const plan = this.data.plan;
    const item = plan && plan.items && plan.items[this.data.selectedItemIndex];
    const feelings = String(this.data.feelings || '').trim();
    if (!item || !item.item_id) return wx.showToast({ title: '当前方案没有可反馈的处方项目', icon: 'none' });
    if (!feelings) return wx.showToast({ title: '请填写本次执行感受', icon: 'none' });
    if (this.data.submitting) return;
    const fields = { version_id: plan.version_id, prescription_item_id: item.item_id,
      execution_status: this.data.statusValues[this.data.selectedStatusIndex], feelings };
    const isExercise = item.intervention_type === 'exercise';
    if (isExercise && fields.execution_status !== 'not_done' && !this.data.selectedVideoPath) {
      return wx.showToast({ title: '已执行或部分执行，请上传训练视频', icon: 'none' });
    }
    const fingerprint = JSON.stringify([sessionKey(session), this.data.planId, fields, this.data.selectedVideoPath]);
    if (!this._pendingFeedback || this._pendingFeedback.fingerprint !== fingerprint) {
      this._pendingFeedback = { fingerprint, data: { ...fields, event_id: eventId(),
        performed_at: new Date().toISOString(), media_ids: [] }, uploadedPath: '' };
    }
    const pending = this._pendingFeedback;
    this.setData({ submitting: true, feedbackError: '' });
    try {
      if (isExercise && fields.execution_status !== 'not_done' && !pending.data.media_ids.length) {
        if (!sameSession(session)) return;
        const media = await uploadFile(`/rehabilitation/plans/${encodeURIComponent(this.data.planId)}/patient-feedback/media`, this.data.selectedVideoPath);
        if (!sameSession(session)) return;
        if (!media || !media.id || media.content_type !== 'video/mp4' && media.content_type !== 'video/webm') throw new Error('视频上传结果无效，请重新选择后重试。');
        pending.data.media_ids = [media.id];
        pending.uploadedPath = this.data.selectedVideoPath;
      }
      await request(`/rehabilitation/plans/${encodeURIComponent(this.data.planId)}/patient-feedback`, {
        method: 'POST',
        data: pending.data,
        header: { 'content-type': 'application/json' },
      });
      if (!sameSession(session)) return;
      if (this._pendingFeedback === pending) this._pendingFeedback = null;
      this.setData({ feelings: '', selectedVideoPath: '', selectedVideoName: '' });
      wx.showToast({ title: '反馈已记录', icon: 'success' });
      this.loadTrainingCycles(session);
      await this.loadFeedback(session, true);
    } catch (error) {
      if (!sameSession(session)) return;
      this.setData({ feedbackError: error.message || '反馈提交失败，请稍后重试。' });
    } finally { if (sameSession(session)) this.setData({ submitting: false }); }
  },
});

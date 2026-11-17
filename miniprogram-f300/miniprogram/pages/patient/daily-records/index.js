const { request, getSession } = require('../../../services/api');
const sessionKey = (session) => `${String(session && session.user && (session.user.id || session.user.actor_id) || '')}|${String(session && session.sessionId || '')}`;
const sameSession = (expected) => {
  const current = getSession() || {};
  return !!(current.identityConfirmed && current.role === 'patient' && sessionKey(current) === sessionKey(expected));
};

function today() {
  const date = new Date();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${date.getFullYear()}-${month}-${day}`;
}

Page({
  data: {
    records: [], loading: false, loaded: false, saving: false, deletingRecordId: '', deleteConfirming: false,
    editingRecordId: '', error: '', success: '',
    date: today(), painLevel: '', mood: '', sleep: '', exerciseCompleted: false, note: '',
  },
  onShow() {
    const session = getSession() || {};
    const key = sessionKey(session);
    if (this._sessionKey !== key) {
      this._requestVersion = (this._requestVersion || 0) + 1;
      this.setData({ records: [], loading: false, loaded: false, saving: false, deletingRecordId: '', deleteConfirming: false,
        editingRecordId: '', error: '', success: '', date: today(), painLevel: '', mood: '', sleep: '', exerciseCompleted: false, note: '' });
    }
    this._sessionKey = key;
    this.loadRecords();
  },
  async onPullDownRefresh() { try { await this.loadRecords(); } finally { wx.stopPullDownRefresh(); } },
  async loadRecords() {
    const session = getSession() || {};
    if (!session.identityConfirmed || session.role !== 'patient') {
      this._sessionKey = '';
      this._requestVersion = (this._requestVersion || 0) + 1;
      this.setData({ records: [], loading: false, loaded: true, saving: false, deletingRecordId: '', deleteConfirming: false,
        editingRecordId: '', error: '请先使用患者账号登录并确认身份。', date: today(), painLevel: '', mood: '', sleep: '', exerciseCompleted: false, note: '' });
      return;
    }
    const key = sessionKey(session);
    if (this._sessionKey !== key) this.setData({ date: today(), painLevel: '', mood: '', sleep: '', exerciseCompleted: false, note: '' });
    this._sessionKey = key;
    if (this.data.loading) return;
    const requestVersion = this._requestVersion = (this._requestVersion || 0) + 1;
    this.setData({ loading: true, error: '' });
    try {
      const result = await request('/patients/daily-records');
      if (!sameSession(session) || requestVersion !== this._requestVersion) return;
      this.setData({ records: Array.isArray(result) ? result : [], loaded: true, error: '' });
    } catch (error) {
      if (!sameSession(session) || requestVersion !== this._requestVersion) return;
      this.setData({ records: [], loaded: true, error: error.message || '暂时无法读取日常记录。' });
    } finally { if (requestVersion === this._requestVersion) this.setData({ loading: false }); }
  },
  editRecord(event) {
    const session = getSession() || {};
    if (!session.identityConfirmed || session.role !== 'patient') return this.setData({ error: '请重新登录患者账号后操作。' });
    const id = String(event.currentTarget.dataset.id || '');
    const record = this.data.records.find((item) => String(item.id) === id);
    if (!id || !record) return this.setData({ error: '记录已变化，请刷新后重试。' });
    this.setData({ editingRecordId: id, date: String(record.date || '').slice(0, 10),
      painLevel: String(record.pain_level), mood: record.mood || '', sleep: record.sleep || '',
      exerciseCompleted: !!record.exercise_completed, note: record.note || '', error: '', success: '' });
  },
  cancelEdit() {
    this.setData({ editingRecordId: '', date: today(), painLevel: '', mood: '', sleep: '', exerciseCompleted: false, note: '', error: '', success: '' });
  },
  onDateChange(event) { this.setData({ date: event.detail.value }); },
  onPainInput(event) { this.setData({ painLevel: event.detail.value }); },
  onMoodInput(event) { this.setData({ mood: event.detail.value }); },
  onSleepInput(event) { this.setData({ sleep: event.detail.value }); },
  onExerciseChange(event) { this.setData({ exerciseCompleted: event.detail.value }); },
  onNoteInput(event) { this.setData({ note: event.detail.value }); },
  async saveRecord() {
    const session = getSession() || {};
    if (!session.identityConfirmed || session.role !== 'patient') {
      this._sessionKey = '';
      this._requestVersion = (this._requestVersion || 0) + 1;
      this.setData({ records: [], loading: false, loaded: true, saving: false, deletingRecordId: '', deleteConfirming: false,
        editingRecordId: '', error: '登录状态已失效，请重新登录。', date: today(), painLevel: '', mood: '', sleep: '', exerciseCompleted: false, note: '' });
      return;
    }
    const painValue = String(this.data.painLevel ?? '').trim();
    if (!painValue) return this.setData({ error: '请填写疼痛程度（0 到 10 的整数）。' });
    const pain = Number(painValue);
    if (!Number.isInteger(pain) || pain < 0 || pain > 10) return this.setData({ error: '疼痛程度请填写 0 到 10 的整数。' });
    const mood = String(this.data.mood || '').trim();
    const sleep = String(this.data.sleep || '').trim();
    const note = String(this.data.note || '').trim();
    if (!mood || !sleep || !note) return this.setData({ error: '请填写心情、睡眠情况和备注。' });
    if (this.data.saving) return;
    const editingRecordId = String(this.data.editingRecordId || '');
    this.setData({ saving: true, error: '', success: '' });
    try {
      if (!sameSession(session)) return;
      await request(editingRecordId
        ? `/patients/daily-records/${encodeURIComponent(editingRecordId)}`
        : '/patients/daily-records', {
        method: editingRecordId ? 'PUT' : 'POST',
        data: { date: this.data.date, pain_level: pain, mood, sleep, exercise_completed: !!this.data.exerciseCompleted, note },
        header: { 'content-type': 'application/json' },
      });
      if (!sameSession(session)) return;
      const success = editingRecordId ? '日常记录已更新。' : '日常记录已保存。';
      this.setData({ editingRecordId: '',
        painLevel: '', mood: '', sleep: '', exerciseCompleted: false, note: '', date: today() });
      await this.loadRecords();
      if (sameSession(session)) this.setData({ success });
    } catch (error) {
      if (!sameSession(session)) return;
      this.setData({ error: error.message || '保存失败，请检查内容后重试。' });
    } finally { if (sameSession(session)) this.setData({ saving: false }); }
  },
  confirmDelete(event) {
    const session = getSession() || {};
    const id = String(event.currentTarget.dataset.id || '');
    if (!session.identityConfirmed || session.role !== 'patient') return this.setData({ error: '请重新登录患者账号后操作。' });
    if (!id || !this.data.records.some((item) => String(item.id) === id)) return this.setData({ error: '记录已变化，请刷新后重试。' });
    if (this.data.saving || this.data.deletingRecordId || this.data.deleteConfirming) return;
    this.setData({ deleteConfirming: true, error: '', success: '' });
    wx.showModal({
      title: '删除日常记录', content: '删除后无法恢复，确定删除这条记录吗？',
      confirmText: '删除', confirmColor: '#b34343',
      success: (result) => {
        if (!sameSession(session)) return;
        this.setData({ deleteConfirming: false });
        if (result.confirm) this.deleteRecord(id, session);
      },
      fail: () => { if (sameSession(session)) this.setData({ deleteConfirming: false }); },
    });
  },
  async deleteRecord(id, session = getSession() || {}) {
    if (!sameSession(session)) return;
    if (this.data.deletingRecordId || this.data.saving) return;
    this.setData({ deletingRecordId: id, error: '', success: '' });
    try {
      await request(`/patients/daily-records/${encodeURIComponent(id)}`, { method: 'DELETE' });
      if (!sameSession(session)) return;
      const records = this.data.records.filter((record) => String(record.id) !== id);
      this.setData({ records });
      if (this.data.editingRecordId === id) this.cancelEdit();
      await this.loadRecords();
      if (sameSession(session)) this.setData({ success: '日常记录已删除。' });
    } catch (error) {
      if (!sameSession(session)) return;
      this.setData({ error: error.message || '删除失败，请刷新后重试。' });
    } finally { if (sameSession(session)) this.setData({ deletingRecordId: '' }); }
  },
});

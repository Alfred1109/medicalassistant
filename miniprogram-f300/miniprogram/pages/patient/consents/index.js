const { request, getSession } = require('../../../services/api');

const sessionKey = (session) => `${String(session && session.user && (session.user.id || session.user.actor_id) || '')}|${String(session && session.sessionId || '')}`;
const sameSession = (expected) => {
  const current = getSession() || {};
  return !!(current.identityConfirmed && current.role === 'patient' && sessionKey(current) === sessionKey(expected));
};
const statusLabels = { pending: '待阅读与回应', signed: '已同意', declined: '已拒绝' };

Page({
  data: { documents: [], loading: false, loaded: false, error: '' },
  onShow() {
    const session = getSession() || {};
    const key = sessionKey(session);
    if (this._sessionKey !== key) this.setData({ documents: [], loaded: false, error: '' });
    this._sessionKey = key;
    this.loadDocuments(session);
  },
  async onPullDownRefresh() { try { await this.loadDocuments(); } finally { wx.stopPullDownRefresh(); } },
  async loadDocuments(session = getSession() || {}) {
    if (!session.identityConfirmed || session.role !== 'patient') {
      this._sessionKey = '';
      this.setData({ documents: [], loaded: true, error: '请先使用患者账号登录并确认身份。' });
      return;
    }
    if (this.data.loading) return;
    this.setData({ loading: true, error: '' });
    try {
      const context = await request('/health-records/patient-context');
      if (!context || !context.patient_id) throw new Error('无法确定当前患者档案，请联系系统管理员。');
      const result = await request(`/consent/documents?patient_id=${encodeURIComponent(context.patient_id)}`);
      if (!sameSession(session)) return this.setData({ documents: [], loaded: true, error: '登录状态已变化，请重新进入患者页面。' });
      const rows = result && Array.isArray(result.documents) ? result.documents : [];
      this.setData({ documents: rows.map((row) => ({ ...row, status_label: statusLabels[row.status] || '状态未说明' })), loaded: true, error: '' });
    } catch (error) {
      if (!sameSession(session)) return this.setData({ documents: [], loaded: true, error: '登录状态已变化，请重新进入患者页面。' });
      this.setData({ documents: [], loaded: true, error: error.message || '暂时无法读取知情同意文件。' });
    } finally { this.setData({ loading: false }); }
  },
  openDocument(event) {
    const id = String(event.currentTarget.dataset.id || '');
    if (id) wx.navigateTo({ url: `/pages/patient/consent-detail/index?document_id=${encodeURIComponent(id)}` });
  },
});

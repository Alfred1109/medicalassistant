const { request, getSession } = require('../../../services/api');
const PAGE_SIZE = 100;
const sessionKey = (session) => `${String(session && session.user && (session.user.id || session.user.actor_id) || '')}|${String(session && session.sessionId || '')}`;
const sameSession = (expected) => {
  const current = getSession() || {};
  return !!(current.identityConfirmed && current.role === 'patient' && sessionKey(current) === sessionKey(expected));
};

Page({
  data: { records: [], loading: false, loadingMore: false, loaded: false, hasMore: false, moreError: '', error: '' },
  onShow() {
    const session = getSession() || {};
    const key = sessionKey(session);
    if (this._sessionKey !== key) this.setData({ records: [], loaded: false, hasMore: false, moreError: '', error: '' });
    this._sessionKey = key;
    this.loadRecords(true);
  },
  async onPullDownRefresh() { try { await this.loadRecords(true); } finally { wx.stopPullDownRefresh(); } },
  async loadRecords(reset = true) {
    const session = getSession() || {};
    if (!session.identityConfirmed || session.role !== 'patient') {
      this._sessionKey = '';
      this.setData({ records: [], loaded: true, hasMore: false, error: '请先使用患者账号登录并确认身份。' });
      return;
    }
    if (this.data.loading || this.data.loadingMore) return;
    const skip = reset ? 0 : this.data.records.length;
    this.setData({ [reset ? 'loading' : 'loadingMore']: true, error: reset ? '' : this.data.error, moreError: '' });
    try {
      const context = await request('/health-records/patient-context');
      if (!context || !context.patient_id) throw new Error('无法确定当前患者档案，请联系系统管理员。');
      const result = await request(`/health-records?patient_id=${encodeURIComponent(context.patient_id)}&skip=${skip}&limit=${PAGE_SIZE}`);
      if (!sameSession(session)) return this.setData({ records: [], loaded: true, hasMore: false, error: '登录状态已变化，请重新进入患者页面。' });
      const items = Array.isArray(result) ? result : [];
      const records = reset ? items : this.data.records.concat(items);
      this.setData({ records, loaded: true, hasMore: items.length === PAGE_SIZE, error: '' });
    } catch (error) {
      if (!sameSession(session)) return this.setData({ records: [], loaded: true, hasMore: false, error: '登录状态已变化，请重新进入患者页面。' });
      if (reset) this.setData({ records: [], loaded: true, error: error.message || '暂时无法读取健康档案，请稍后重试。' });
      else this.setData({ moreError: error.message || '加载更多失败，请重试。' });
    } finally { this.setData({ [reset ? 'loading' : 'loadingMore']: false }); }
  },
  loadMore() { return this.loadRecords(false); },
});

const { request, getSession } = require('../../../services/api');
const PAGE_SIZE = 100;
const sessionKey = (session) => `${String(session && session.user && (session.user.id || session.user.actor_id) || '')}|${String(session && session.sessionId || '')}`;
const sameSession = (expected) => {
  const current = getSession() || {};
  return !!(current.identityConfirmed && current.role === 'patient' && sessionKey(current) === sessionKey(expected));
};

Page({
  data: { plans: [], loading: false, loadingMore: false, loaded: false, hasMore: false, moreError: '', error: '' },
  onShow() {
    const session = getSession() || {};
    const key = sessionKey(session);
    if (this._sessionKey !== key) this.setData({ plans: [], loaded: false, hasMore: false, moreError: '', error: '' });
    this._sessionKey = key;
    this.loadPlans(true);
  },
  async onPullDownRefresh() {
    try { await this.loadPlans(true); } finally { wx.stopPullDownRefresh(); }
  },
  async loadPlans(reset = true) {
    const session = getSession() || {};
    if (!session.identityConfirmed || session.role !== 'patient') {
      this._sessionKey = '';
      this.setData({ plans: [], loaded: true, hasMore: false, error: '请先使用患者账号登录并确认身份。' });
      return;
    }
    if (this.data.loading || this.data.loadingMore) return;
    const skip = reset ? 0 : this.data.plans.length;
    this.setData({ [reset ? 'loading' : 'loadingMore']: true, error: reset ? '' : this.data.error, moreError: '' });
    try {
      const result = await request(`/rehabilitation/publications/my-plans?skip=${skip}&limit=${PAGE_SIZE}`);
      if (!sameSession(session)) return this.setData({ plans: [], loaded: true, hasMore: false, error: '登录状态已变化，请重新进入患者页面。' });
      const items = Array.isArray(result) ? result : result && Array.isArray(result.items) ? result.items : [];
      const plans = reset ? items : this.data.plans.concat(items);
      const total = Number(result && result.total);
      this.setData({ plans, loaded: true, hasMore: Number.isFinite(total) ? plans.length < total : items.length === PAGE_SIZE, error: '' });
    } catch (error) {
      if (!sameSession(session)) return this.setData({ plans: [], loaded: true, hasMore: false, error: '登录状态已变化，请重新进入患者页面。' });
      if (reset) this.setData({ plans: [], loaded: true, error: error.message || '暂时无法读取康复方案，请稍后重试。' });
      else this.setData({ moreError: error.message || '加载更多失败，请重试。' });
    } finally { this.setData({ [reset ? 'loading' : 'loadingMore']: false }); }
  },
  loadMore() { return this.loadPlans(false); },
  openPlan(event) {
    const id = String(event.currentTarget.dataset.id || '');
    if (id) wx.navigateTo({ url: `/pages/patient/plan-detail/index?plan_id=${encodeURIComponent(id)}` });
  },
});

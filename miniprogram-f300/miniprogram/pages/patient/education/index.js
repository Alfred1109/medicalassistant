const { request, getSession } = require('../../../services/api');
const PAGE_SIZE = 100;
const sessionKey = (session) => `${String(session && session.user && (session.user.id || session.user.actor_id) || '')}|${String(session && session.sessionId || '')}`;
const sameSession = (expected) => {
  const current = getSession() || {};
  return !!(current.identityConfirmed && current.role === 'patient' && sessionKey(current) === sessionKey(expected));
};

Page({
  data: { plans: [], sourceCount: 0, total: 0, loading: false, loadingMore: false, loaded: false, hasMore: false, moreError: '', error: '' },
  onShow() {
    const session = getSession() || {};
    const key = sessionKey(session);
    if (this._sessionKey !== key) this.setData({ plans: [], sourceCount: 0, total: 0, loaded: false, hasMore: false, moreError: '', error: '' });
    this._sessionKey = key;
    this.loadEducation(true);
  },
  async onPullDownRefresh() { try { await this.loadEducation(true); } finally { wx.stopPullDownRefresh(); } },
  async loadEducation(reset = true) {
    const session = getSession() || {};
    if (!session.identityConfirmed || session.role !== 'patient') {
      this._sessionKey = '';
      this.setData({ plans: [], sourceCount: 0, total: 0, loaded: true, hasMore: false, error: '请先使用患者账号登录并确认身份。' });
      return;
    }
    if (this.data.loading || this.data.loadingMore) return;
    const skip = reset ? 0 : this.data.sourceCount;
    this.setData({ [reset ? 'loading' : 'loadingMore']: true, error: reset ? '' : this.data.error, moreError: '' });
    try {
      const result = await request(`/rehabilitation/publications/my-plans?skip=${skip}&limit=${PAGE_SIZE}`);
      if (!sameSession(session)) return this.setData({ plans: [], sourceCount: 0, loaded: true, hasMore: false, error: '登录状态已变化，请重新进入患者页面。' });
      const rows = result && Array.isArray(result.items) ? result.items : [];
      const plans = (result && Array.isArray(result.items) ? result.items : []).map((plan) => ({
        ...plan,
        guidance_items: (Array.isArray(plan.items) ? plan.items : []).filter((item) =>
          !!(item.patient_instructions || item.description || (Array.isArray(item.execution_requirements) && item.execution_requirements.length) || item.guidance_video_url)),
        has_guidance: !!(plan.content && plan.content.patient_instructions)
          || (Array.isArray(plan.items) && plan.items.some((item) => item.patient_instructions || item.description || item.guidance_video_url
            || (Array.isArray(item.execution_requirements) && item.execution_requirements.length))),
      }));
      const visible = plans.filter((plan) => plan.has_guidance);
      const allPlans = reset ? visible : this.data.plans.concat(visible);
      const sourceCount = skip + rows.length;
      const total = Number(result && result.total) || 0;
      this.setData({ plans: allPlans, sourceCount, total, loaded: true, hasMore: sourceCount < total, error: '' });
    } catch (error) {
      if (!sameSession(session)) return this.setData({ plans: [], sourceCount: 0, loaded: true, hasMore: false, error: '登录状态已变化，请重新进入患者页面。' });
      if (reset) this.setData({ plans: [], sourceCount: 0, total: 0, loaded: true, error: error.message || '暂时无法读取康复指导。' });
      else this.setData({ moreError: error.message || '加载更多失败，请重试。' });
    } finally { this.setData({ [reset ? 'loading' : 'loadingMore']: false }); }
  },
  loadMore() { return this.loadEducation(false); },
});

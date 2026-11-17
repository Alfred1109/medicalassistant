const { request, getSession } = require('../../../services/api');
const PAGE_SIZE = 100;
const sessionKey = (session) => `${String(session && session.user && (session.user.id || session.user.actor_id) || '')}|${String(session && session.sessionId || '')}`;
const sameSession = (expected) => {
  const current = getSession() || {};
  return !!(current.identityConfirmed && current.role === 'patient' && sessionKey(current) === sessionKey(expected));
};

const statusLabels = {
  scheduled: '待安排',
  awaiting_fill: '待填写',
  filled: '已填写，待审核',
  completed: '已完成',
  overdue: '已逾期',
  lost: '已失访',
  canceled: '已取消',
  cancelled: '已取消',
};
const typeLabels = { phone: '电话', online: '线上', onsite: '门诊', home_visit: '家庭访视', remote_monitoring: '远程监测', group: '小组', other: '其他' };

Page({
  data: { followups: [], loading: false, loadingMore: false, loaded: false, hasMore: false, moreError: '', error: '' },
  onShow() {
    const session = getSession() || {};
    const key = sessionKey(session);
    if (this._sessionKey !== key) this.setData({ followups: [], loaded: false, hasMore: false, moreError: '', error: '' });
    this._sessionKey = key;
    this.loadFollowups(true);
  },
  async onPullDownRefresh() { try { await this.loadFollowups(true); } finally { wx.stopPullDownRefresh(); } },
  async loadFollowups(reset = true) {
    const session = getSession() || {};
    if (!session.identityConfirmed || session.role !== 'patient') {
      this._sessionKey = '';
      this.setData({ followups: [], loaded: true, hasMore: false, error: '请先使用患者账号登录并确认身份。' });
      return;
    }
    if (this.data.loading || this.data.loadingMore) return;
    const skip = reset ? 0 : this.data.followups.length;
    this.setData({ [reset ? 'loading' : 'loadingMore']: true, error: reset ? '' : this.data.error, moreError: '' });
    try {
      const context = await request('/health-records/patient-context');
      if (!context || !context.patient_id) throw new Error('无法确定当前患者档案，请联系系统管理员。');
      const result = await request(`/health-records/followups?patient_id=${encodeURIComponent(context.patient_id)}&skip=${skip}&limit=${PAGE_SIZE}`);
      if (!sameSession(session)) return this.setData({ followups: [], loaded: true, hasMore: false, error: '登录状态已变化，请重新进入患者页面。' });
      const items = (Array.isArray(result) ? result : []).map((item) => ({
        ...item,
        status_label: statusLabels[item.status] || item.status || '状态未说明',
        type_label: typeLabels[item.follow_up_type] || item.follow_up_type || '方式未说明',
      }));
      const followups = reset ? items : this.data.followups.concat(items);
      this.setData({ followups, loaded: true, hasMore: items.length === PAGE_SIZE, error: '' });
    } catch (error) {
      if (!sameSession(session)) return this.setData({ followups: [], loaded: true, hasMore: false, error: '登录状态已变化，请重新进入患者页面。' });
      if (reset) this.setData({ followups: [], loaded: true, error: error.message || '暂时无法读取随访安排。' });
      else this.setData({ moreError: error.message || '加载更多失败，请重试。' });
    } finally { this.setData({ [reset ? 'loading' : 'loadingMore']: false }); }
  },
  loadMore() { return this.loadFollowups(false); },
});

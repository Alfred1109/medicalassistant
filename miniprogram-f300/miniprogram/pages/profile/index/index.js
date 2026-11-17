const { getSession } = require('../../../services/api');
Page({
  data: { user: null, roleLabel: '' },
  onShow() {
    const session = getSession();
    if (!session || !session.identityConfirmed) return this.setData({ user: null, roleLabel: '' });
    const labels = { patient: '患者', doctor: '医生', health_manager: '健康管理师' };
    this.setData({ user: session.user, roleLabel: labels[session.role] || session.role });
  },
  openPatientPage(event) {
    const session = getSession();
    if (!session || !session.identityConfirmed || session.role !== 'patient') return;
    const paths = { followups: '/pages/patient/followups/index', education: '/pages/patient/education/index', consent: '/pages/patient/consents/index', daily: '/pages/patient/daily-records/index' };
    const url = paths[event.currentTarget.dataset.page];
    if (url) wx.navigateTo({ url });
  },
  logout() {
    const pages = getCurrentPages();
    const root = pages[0];
    if (root && typeof root.logout === 'function') root.logout();
    wx.navigateBack({ delta: Math.max(1, pages.length - 1) });
  },
});

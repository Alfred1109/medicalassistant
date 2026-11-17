const { getSession } = require('../../services/api');
const NAV = {
  patient: [
    { key: 'home', label: '首页', url: '/pages/patient/home/index' },
    { key: 'plans', label: '康复', url: '/pages/patient/plans/index' },
    { key: 'health', label: '健康', url: '/pages/patient/records/index' },
    { key: 'messages', label: '消息', url: '/pages/messages/index/index' },
    { key: 'profile', label: '我的', url: '/pages/profile/index/index' },
  ],
  clinical: [
    { key: 'home', label: '工作台', url: '/pages/clinical/index/index?view=workbench' },
    { key: 'patients', label: '患者', url: '/pages/clinical/index/index?view=patients' },
    { key: 'followups', label: '随访', url: '/pages/clinical/index/index?view=followups' },
    { key: 'messages', label: '消息', url: '/pages/messages/index/index' },
    { key: 'profile', label: '我的', url: '/pages/profile/index/index' },
  ],
};
Component({
  properties: { current: { type: String, value: '' } },
  data: { items: [] },
  lifetimes: { attached() { this.refresh(); } },
  pageLifetimes: { show() { this.refresh(); } },
  methods: {
    refresh() {
      const s = getSession();
      const role = s && s.identityConfirmed && s.role;
      this.setData({ items: role === 'patient' ? NAV.patient : (role === 'doctor' || role === 'health_manager' ? NAV.clinical : []) });
    },
    navigate(e) {
      const item = this.data.items.find(value => value.key === e.currentTarget.dataset.key);
      if (!item || item.key === this.data.current) return;
      const pages = getCurrentPages();
      if (pages.length > 1) wx.navigateBack({ delta: pages.length - 1, success: () => wx.navigateTo({ url: item.url }) });
      else wx.navigateTo({ url: item.url });
    },
  },
});

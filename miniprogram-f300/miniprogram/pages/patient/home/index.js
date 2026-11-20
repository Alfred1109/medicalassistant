const { request, getSession } = require('../../../services/api');
const sessionKey = (session) => `${String(session && session.user && (session.user.id || session.user.actor_id) || '')}|${String(session && session.sessionId || '')}`;
const sameSession = (expected) => {
  const current = getSession() || {};
  return !!(current.identityConfirmed && current.role === 'patient' && sessionKey(current) === sessionKey(expected));
};

const sections = [
  { key: 'plans', title: '康复方案', description: '查看已发布方案与处方内容' },
  { key: 'records', title: '健康档案', description: '查看医护记录和健康数据' },
  { key: 'daily-records', title: '日常记录', description: '记录疼痛、睡眠、心情和训练' },
  { key: 'followups', title: '随访安排', description: '查看医护为你安排的随访' },
  { key: 'questionnaires', title: '我的问卷', description: '填写医护分配给你的问卷' },
  { key: 'consents', title: '知情同意', description: '阅读并回应发给你的知情同意文件' },
  { key: 'education', title: '康复指导', description: '查看方案中附带的患者指导' },
];

Page({
  data: {
    sections, userName: '', error: '',
    todos: [], todoLoading: false, todoLoaded: false, todoError: '',
    metrics: [], metricsLoading: false, metricsLoaded: false, metricsError: '',
    plans: [], plansLoading: false, plansLoaded: false, plansError: '',
  },
  onShow() {
    const session = getSession() || {};
    if (!session.identityConfirmed || session.role !== 'patient') {
      this._sessionKey = '';
      this.setData({ userName: '', error: '请先使用患者账号登录并确认身份。', todos: [], todoLoaded: false, todoError: '', metrics: [], metricsLoaded: false, metricsError: '', plans: [], plansLoaded: false, plansError: '' });
      return;
    }
    const key = sessionKey(session);
    if (this._sessionKey !== key) this.setData({ todos: [], todoLoaded: false, todoError: '', metrics: [], metricsLoaded: false, metricsError: '', plans: [], plansLoaded: false, plansError: '' });
    this._sessionKey = key;
    this.setData({ userName: (session.user && (session.user.name || session.user.display_name || session.user.email)) || '患者', error: '' });
    this.loadTodos(session);
    this.loadMetrics(session);
    this.loadPlans(session);
  },
  async loadTodos(expected = getSession() || {}) {
    if (!sameSession(expected)) return this.setData({ todos: [], todoLoaded: true, todoError: '请重新登录后查看。' });
    this.setData({ todoLoading: true, todoError: '' });
    try {
      const result = await request('/patients/todo-center');
      if (!sameSession(expected)) return;
      if (!Array.isArray(result?.items) || !Array.isArray(result?.source_errors)) throw new Error('待办接口响应有误。');
      this.setData({ todos: result.items, todoLoaded: true,
        todoError: result.source_errors.length ? '部分待办暂时无法读取，当前列表可能不完整。' : '' });
    } catch (error) {
      if (!sameSession(expected)) return;
      this.setData({ todos: [], todoLoaded: true, todoError: error.message || '待办事项加载失败。' });
    } finally { if (sameSession(expected)) this.setData({ todoLoading: false }); }
  },
  openTodo(event) {
    const session = getSession();
    if (!sameSession(session) || sessionKey(session) !== this._sessionKey) return;
    const item = this.data.todos.find(row => row.id === event.currentTarget.dataset.id);
    const match = /^(questionnaire|consent):([0-9a-fA-F]{24})$/.exec(item?.id || '');
    if (!match || item.type !== match[1]) return;
    const url = match[1] === 'consent'
      ? `/pages/patient/consent-detail/index?document_id=${match[2]}`
      : `/pages/patient/questionnaires/index?task_id=${match[2]}`;
    wx.navigateTo({ url });
  },
  async loadMetrics(expected = getSession() || {}) {
    if (!sameSession(expected)) return this.setData({ metrics: [], metricsLoaded: true, metricsError: '请重新登录后查看。' });
    this.setData({ metricsLoading: true, metricsError: '' });
    try {
      const result = await request('/patients/health-metrics');
      if (!sameSession(expected)) return this.setData({ metrics: [], metricsLoaded: true, metricsError: '登录状态已变化，请重新进入患者页面。' });
      this.setData({ metrics: Array.isArray(result) ? result : [], metricsLoaded: true, metricsError: '' });
    } catch (error) {
      if (!sameSession(expected)) return this.setData({ metrics: [], metricsLoaded: true, metricsError: '登录状态已变化，请重新进入患者页面。' });
      this.setData({ metrics: [], metricsLoaded: true, metricsError: error.message || '健康指标加载失败。' });
    } finally { this.setData({ metricsLoading: false }); }
  },
  async loadPlans(expected = getSession() || {}) {
    if (!sameSession(expected)) return this.setData({ plans: [], plansLoaded: true, plansError: '请重新登录后查看。' });
    this.setData({ plansLoading: true, plansError: '' });
    try {
      const result = await request('/rehabilitation/publications/my-plans?skip=0&limit=5');
      if (!sameSession(expected)) return this.setData({ plans: [], plansLoaded: true, plansError: '登录状态已变化，请重新进入患者页面。' });
      this.setData({ plans: result && Array.isArray(result.items) ? result.items : [], plansLoaded: true, plansError: '' });
    } catch (error) {
      if (!sameSession(expected)) return this.setData({ plans: [], plansLoaded: true, plansError: '登录状态已变化，请重新进入患者页面。' });
      this.setData({ plans: [], plansLoaded: true, plansError: error.message || '康复方案加载失败。' });
    } finally { this.setData({ plansLoading: false }); }
  },
  retryBlock(event) {
    const block = event.currentTarget.dataset.block;
    const session = getSession() || {};
    if (block === 'todos') this.loadTodos(session);
    if (block === 'metrics') this.loadMetrics(session);
    if (block === 'plans') this.loadPlans(session);
  },
  openSection(event) {
    const key = event.currentTarget.dataset.key;
    const routes = {
      plans: '/pages/patient/plans/index',
      records: '/pages/patient/records/index',
      'daily-records': '/pages/patient/daily-records/index',
      followups: '/pages/patient/followups/index',
      questionnaires: '/pages/patient/questionnaires/index',
      consents: '/pages/patient/consents/index',
      education: '/pages/patient/education/index',
    };
    if (routes[key]) wx.navigateTo({ url: routes[key] });
  },
  openCapture() {
    const pages = getCurrentPages();
    const root = pages[0];
    if (!root || typeof root.openCapture !== 'function') return wx.showToast({ title: '设备采集入口暂不可用', icon: 'none' });
    if (pages.length <= 1) return root.openCapture();
    wx.navigateBack({ delta: pages.length - 1, success: () => root.openCapture() });
  },
  openPlan(event) {
    const id = String(event.currentTarget.dataset.id || '');
    if (id) wx.navigateTo({ url: `/pages/patient/plan-detail/index?plan_id=${encodeURIComponent(id)}` });
  },
});

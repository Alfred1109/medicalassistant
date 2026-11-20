const { request, getSession } = require('../../../services/api');
const { apiBaseUrl } = require('../../../config');
const PAGE_SIZE = 50;
const labels = { assigned: '待填写', active: '填写中', submitted: '已提交', confirmed: '已核实', revoking: '正在取消', revoked: '已取消', cancelled: '已取消' };
const stamp = session => session && session.identityConfirmed && session.role === 'patient' && session.user
  ? `${session.user.id || session.user.actor_id || ''}:${session.sessionId}` : '';
Page({
  data: { items: [], skip: 0, hasMore: false, loading: false, opening: false, error: '' },
  onLoad(options = {}) {
    this._generation = 0;
    const taskId = String(options.task_id || '');
    this._taskId = /^[0-9a-f]{24}$/i.test(taskId) ? taskId.toLowerCase() : '';
    this._invalidTask = !!taskId && !this._taskId;
  },
  onShow() {
    const current = stamp(getSession());
    if (!current) { this._stamp = ''; this._generation++; this.setData({ items: [], error: '请先登录患者账号。', loading: false }); return; }
    if (current !== this._stamp) { this._stamp = current; this._generation++; this.setData({ items: [], skip: 0, hasMore: false, loading: false, opening: false }); }
    this.load(true);
  },
  onPullDownRefresh() { this.load(true).finally(() => wx.stopPullDownRefresh()); },
  isCurrent(key, generation) { return !!key && key === this._stamp && key === stamp(getSession()) && generation === this._generation; },
  async load(reset) {
    if (this.data.loading) return;
    const key = this._stamp, generation = this._generation, skip = reset ? 0 : this.data.skip;
    if (!this.isCurrent(key, generation)) return;
    if (this._invalidTask) { this.setData({ error: '问卷任务编号无效。' }); return; }
    this.setData({ loading: true, error: '' });
    try {
      let result;
      if (this._taskId) {
        const task = await request(`/integrations/forms/patient-self/tasks/${this._taskId}`);
        if (!task || task.id !== this._taskId) throw new Error('无法确认该问卷任务。');
        result = { items: [task], total: 1 };
      } else {
        result = await request(`/integrations/forms/patient-self/tasks?skip=${skip}&limit=${PAGE_SIZE}`);
      }
      if (!this.isCurrent(key, generation)) return;
      if (!result || !Array.isArray(result.items) || typeof result.total !== 'number') throw new Error('问卷任务列表格式异常。');
      const rows = result.items.map(item => ({ ...item, statusLabel: labels[item.status] || item.status || '状态未知', canLaunch: ['assigned', 'active'].includes(item.status) }));
      const items = reset ? rows : this.data.items.concat(rows);
      this.setData({ items, skip: skip + rows.length, hasMore: skip + rows.length < result.total });
    } catch (error) { if (this.isCurrent(key, generation)) this.setData({ error: error.message || '加载问卷失败。' }); }
    finally { if (this.isCurrent(key, generation)) this.setData({ loading: false }); }
  },
  loadMore() { return this.load(false); },
  async refreshStatus(event) {
    const id = String(event.currentTarget.dataset.id || ''), key = this._stamp, generation = this._generation;
    if (!id || !this.isCurrent(key, generation) || this.data.opening) return;
    this.setData({ opening: true, error: '' });
    try {
      if (!this._taskId) await request(`/integrations/forms/patient-self/tasks/${encodeURIComponent(id)}`);
      if (this.isCurrent(key, generation)) await this.load(true);
    } catch (error) { if (this.isCurrent(key, generation)) this.setData({ error: error.message || '刷新状态失败。' }); }
    finally { if (this.isCurrent(key, generation)) this.setData({ opening: false }); }
  },
  async launch(event) {
    const taskId = String(event.currentTarget.dataset.id || ''), key = this._stamp, generation = this._generation;
    if (!taskId || this.data.opening || !this.isCurrent(key, generation)) return;
    this.setData({ opening: true, error: '' });
    try {
      const result = await request(`/integrations/forms/patient-self/tasks/${encodeURIComponent(taskId)}/launch`, { method: 'POST' });
      if (!this.isCurrent(key, generation)) return;
      const base = new URL(apiBaseUrl), target = new URL(result.webviewUrl);
      const prefix = `${base.pathname.replace(/\/$/, '')}/integrations/forms/patient-self/launch-bridge/`;
      if (result.taskId !== taskId || base.protocol !== 'https:' || target.protocol !== 'https:' || target.origin !== base.origin || !target.pathname.startsWith(prefix) || !target.pathname.slice(prefix.length) || target.search || target.hash) throw new Error('问卷入口校验失败。');
      wx.navigateTo({ url: `/pages/patient/questionnaires/webview/index?url=${encodeURIComponent(target.href)}&taskId=${encodeURIComponent(taskId)}` });
    } catch (error) { if (this.isCurrent(key, generation)) this.setData({ error: error.message || '无法打开问卷。' }); }
    finally { if (this.isCurrent(key, generation)) this.setData({ opening: false }); }
  },
});

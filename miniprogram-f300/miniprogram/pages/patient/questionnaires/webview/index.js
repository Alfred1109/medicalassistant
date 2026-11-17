const { apiBaseUrl } = require('../../../../config');
const { getSession } = require('../../../../services/api');
Page({
  data: { url: '', error: '' },
  onLoad(options) {
    try {
      const session = getSession();
      if (!session || !session.identityConfirmed || session.role !== 'patient') throw new Error('请重新登录患者账号。');
      this._sessionId = session.sessionId;
      const base = new URL(apiBaseUrl), target = new URL(decodeURIComponent(options.url || ''));
      const prefix = `${base.pathname.replace(/\/$/, '')}/integrations/forms/patient-self/launch-bridge/`;
      if (base.protocol !== 'https:' || target.protocol !== 'https:' || target.origin !== base.origin || !target.pathname.startsWith(prefix) || !target.pathname.slice(prefix.length) || target.search || target.hash || !options.taskId) throw new Error('问卷入口地址无效。');
      this.setData({ url: target.href });
    } catch (error) { this.setData({ error: error.message || '无法打开问卷。' }); }
  },
  onShow() { const session = getSession(); if (this._sessionId && (!session || session.sessionId !== this._sessionId)) this.setData({ url: '', error: '登录状态已变化，请重新打开问卷。' }); },
  onWebviewError(event) { this.setData({ error: (event.detail && event.detail.errMsg) || '微信未能打开问卷，请检查业务域名。' }); },
  close() { wx.navigateBack(); },
});

const { apiBaseUrl } = require('../../../../config');

Page({
  data: { url: '', taskId: '', error: '' },
  onLoad(options) {
    try {
      const base = new URL(apiBaseUrl);
      const target = new URL(decodeURIComponent(options.url || ''));
      const prefix = `${base.pathname.replace(/\/$/, '')}/integrations/forms/fill-tasks/launch-bridge/`;
      if (base.protocol !== 'https:' || target.protocol !== 'https:' || target.origin !== base.origin
          || !target.pathname.startsWith(prefix) || !target.pathname.slice(prefix.length)
          || target.search || target.hash || !options.taskId) throw new Error('问卷入口地址无效或不受信任。');
      this.setData({ url: target.href, taskId: options.taskId });
    } catch (error) { this.setData({ error: error.message || '无法打开问卷入口。' }); }
  },
  onWebviewError(event) {
    const detail = event.detail && event.detail.errMsg;
    this.setData({ error: detail || '微信未能打开问卷域名。请确认该 HTTPS 域已加入小程序业务域名。' });
  },
  close() { wx.navigateBack(); },
});

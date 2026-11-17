const { request, getSession } = require('../../../services/api');

const sessionKey = (session) => `${String(session && session.user && (session.user.id || session.user.actor_id) || '')}|${String(session && session.sessionId || '')}`;
const sameSession = (expected) => {
  const current = getSession() || {};
  return !!(current.identityConfirmed && current.role === 'patient' && sessionKey(current) === sessionKey(expected));
};
const statusLabels = { pending: '待阅读与回应', signed: '已同意', declined: '已拒绝' };

Page({
  data: { documentId: '', document: null, signedName: '', loading: false, loaded: false, submitting: false, error: '' },
  onLoad(options) { this.setData({ documentId: String(options.document_id || '') }); },
  onShow() {
    const session = getSession() || {};
    if (!session.identityConfirmed || session.role !== 'patient') {
      this._sessionKey = '';
      this.setData({ document: null, signedName: '', loaded: true, error: '请先使用患者账号登录并确认身份。' });
      return;
    }
    const key = sessionKey(session);
    if (this._sessionKey !== key) this.setData({ document: null, signedName: '', loaded: false, error: '' });
    this._sessionKey = key;
    this.loadDocument(session);
  },
  async onPullDownRefresh() { try { await this.loadDocument(); } finally { wx.stopPullDownRefresh(); } },
  async loadDocument(session = getSession() || {}) {
    if (!session.identityConfirmed || session.role !== 'patient') {
      this.setData({ document: null, signedName: '', loaded: true, error: '请先使用患者账号登录并确认身份。' });
      return;
    }
    if (this.data.loading) return;
    if (!this.data.documentId) return this.setData({ loaded: true, error: '同意书标识缺失，请返回列表重试。' });
    this.setData({ loading: true, error: '' });
    try {
      const document = await request(`/consent/documents/${encodeURIComponent(this.data.documentId)}`);
      if (!sameSession(session)) return this.setData({ document: null, signedName: '', loaded: true, error: '登录状态已变化，请重新进入患者页面。' });
      this.setData({ document: { ...document, status_label: statusLabels[document.status] || '状态未说明' }, signedName: document.signed_name || '', loaded: true, error: '' });
    } catch (error) {
      if (!sameSession(session)) return this.setData({ document: null, signedName: '', loaded: true, error: '登录状态已变化，请重新进入患者页面。' });
      this.setData({ document: null, loaded: true, error: error.message || '暂时无法读取同意书。' });
    } finally { this.setData({ loading: false }); }
  },
  onSignedNameInput(event) { this.setData({ signedName: event.detail.value }); },
  confirmAccept() {
    const name = String(this.data.signedName || '').trim();
    if (!name) return wx.showToast({ title: '请填写签署姓名', icon: 'none' });
    const title = this.data.document && this.data.document.title || '知情同意文件';
    wx.showModal({ title: '确认同意', content: `请确认你已阅读《${title}》全文，并同意提交。系统将记录签署姓名和同意状态。`, confirmText: '确认同意', success: (result) => { if (result.confirm) this.submitDecision(true, name); } });
  },
  confirmDecline() {
    const title = this.data.document && this.data.document.title || '知情同意文件';
    wx.showModal({ title: '确认拒绝', content: `请确认你要拒绝《${title}》。系统将记录拒绝状态。`, confirmText: '确认拒绝', confirmColor: '#b34343', success: (result) => { if (result.confirm) this.submitDecision(false, ''); } });
  },
  async submitDecision(accepted, signedName) {
    const session = getSession() || {};
    if (!sameSession(session)) return this.setData({ document: null, error: '登录状态已失效，请重新登录。' });
    if (!this.data.document || this.data.document.status !== 'pending' || this.data.submitting) return;
    this.setData({ submitting: true, error: '' });
    try {
      await request(`/consent/documents/${encodeURIComponent(this.data.documentId)}/signature`, {
        method: 'POST', data: { signed_name: signedName, accepted }, header: { 'content-type': 'application/json' },
      });
      if (!sameSession(session)) return this.setData({ document: null, error: '登录状态已变化，未显示本次操作结果。' });
      await this.loadDocument(session);
      const actualStatus = this.data.document && this.data.document.status;
      if (actualStatus === (accepted ? 'signed' : 'declined')) wx.showToast({ title: accepted ? '同意状态已记录' : '拒绝状态已记录', icon: 'success' });
      else wx.showToast({ title: `当前状态：${this.data.document && this.data.document.status_label || '请刷新确认'}`, icon: 'none' });
      const pages = getCurrentPages();
      const listPage = pages.length > 1 ? pages[pages.length - 2] : null;
      if (listPage && typeof listPage.loadDocuments === 'function') await listPage.loadDocuments(session);
    } catch (error) {
      if (!sameSession(session)) return this.setData({ document: null, error: '登录状态已变化，请重新进入患者页面。' });
      this.setData({ error: error.message || '操作未能确认，请刷新查看当前状态。' });
      await this.loadDocument(session);
      const pages = getCurrentPages();
      const listPage = pages.length > 1 ? pages[pages.length - 2] : null;
      if (listPage && typeof listPage.loadDocuments === 'function') await listPage.loadDocuments(session);
    } finally { this.setData({ submitting: false }); }
  },
  backToList() { wx.navigateBack(); },
});

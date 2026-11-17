const api = require('../../../services/api');

const PAGE_SIZE = 50;
const REFRESH_INTERVAL_MS = 30000;
const ALLOWED_ROLES = new Set(['patient', 'doctor', 'health_manager']);

function errorMessage(error, fallback) {
  return error && error.message ? error.message : fallback;
}

let clientMessageSequence = 0;

function makeClientMessageId() {
  return new Promise((resolve, reject) => {
    if (typeof wx !== 'undefined' && typeof wx.getRandomValues === 'function') {
      wx.getRandomValues({ length: 16,
        success: result => resolve(`mini-${Array.from(new Uint8Array(result.randomValues), value => value.toString(16).padStart(2, '0')).join('')}`),
        fail: () => reject(new Error('无法生成消息幂等标识，请重试。')),
      });
      return;
    }
    // This value is only an idempotency key, never an authentication secret.
    clientMessageSequence += 1;
    resolve(`mini-${Date.now()}-${clientMessageSequence}`);
  });
}

Page({
  data: {
    session: null,
    roleLabel: '',
    conversations: [],
    conversationSkip: 0,
    hasMoreConversations: false,
    loadingMoreConversations: false,
    contacts: [],
    contactPickerOpen: false,
    contactsLoading: false,
    contactsError: '',
    activeId: '',
    activeConversation: null,
    sendAllowed: false,
    messages: [],
    draft: '',
    canSend: false,
    loading: false,
    loadingMessages: false,
    loadingEarlier: false,
    sending: false,
    error: '',
    messagesError: '',
    canLoadEarlier: false,
    notice: '',
  },
  _refreshTimer: null,
  _requestVersion: 0,
  _sessionStamp: '',
  _pendingMessage: null,

  sessionStamp(session) {
    if (!session || !session.user) return '';
    return `${session.sessionId || ''}:${session.role || session.user.role || ''}:${session.user.id || ''}`;
  },

  isCurrentSession(stamp) {
    return !!stamp && stamp === this._sessionStamp
      && stamp === this.sessionStamp(this.data.session)
      && stamp === this.sessionStamp(api.getSession());
  },

  onLoad() {
    this.loadSession();
  },

  onShow() {
    this.loadSession();
    this.startRefresh();
  },

  onHide() {
    this.stopRefresh();
  },

  onUnload() {
    this.stopRefresh();
    this._requestVersion += 1;
  },

  onPullDownRefresh() {
    this.refreshAll().finally(() => wx.stopPullDownRefresh());
  },

  loadSession() {
    const session = api.getSession();
    const user = session && session.user;
    const roleLabels = { patient: '患者', doctor: '医生', health_manager: '健康管理师' };
    if (!session || !session.identityConfirmed || !user || !ALLOWED_ROLES.has(session.role || user.role)) {
      this._sessionStamp = '';
      this._requestVersion += 1;
      this._pendingMessage = null;
      this.setData({ session: null, roleLabel: '', conversations: [], conversationSkip: 0,
        hasMoreConversations: false, messages: [], activeId: '',
        activeConversation: null, sendAllowed: false, contacts: [], contactPickerOpen: false,
        error: '请使用已确认身份的患者、医生或健康管理师账号登录。' });
      this.stopRefresh();
      return;
    }
    const role = session.role || user.role;
    const normalizedSession = { ...session, role };
    const nextStamp = this.sessionStamp(normalizedSession);
    const wasSignedIn = !!this._sessionStamp && this._sessionStamp === nextStamp;
    if (!wasSignedIn) {
      this._requestVersion += 1;
      this._pendingMessage = null;
      this.setData({ conversations: [], conversationSkip: 0, hasMoreConversations: false,
        messages: [], activeId: '', activeConversation: null, sendAllowed: false,
        contacts: [], contactPickerOpen: false, draft: '', canSend: false, messagesError: '' });
    }
    this._sessionStamp = nextStamp;
    this.setData({ session: normalizedSession, roleLabel: roleLabels[role] || '用户', error: '' });
    if (!wasSignedIn) this.refreshAll();
  },

  startRefresh() {
    this.stopRefresh();
    if (!this.data.session) return;
    this._refreshTimer = setInterval(() => this.refreshAll(true), REFRESH_INTERVAL_MS);
  },

  stopRefresh() {
    if (this._refreshTimer) clearInterval(this._refreshTimer);
    this._refreshTimer = null;
  },

  expireSession() {
    this._pendingMessage = null;
    this._sessionStamp = '';
    api.clearSession();
    this.stopRefresh();
    this._requestVersion += 1;
    this.setData({ session: null, conversations: [], conversationSkip: 0,
      hasMoreConversations: false, messages: [], activeId: '',
      activeConversation: null, sendAllowed: false, draft: '', canSend: false, error: '登录已过期，请重新登录。',
      contacts: [], contactPickerOpen: false, messagesError: '' });
  },

  async refreshAll(silent = false) {
    if (!this.data.session) return;
    const sessionStamp = this._sessionStamp;
    if (!silent) this.setData({ loading: true, error: '' });
    try {
      const requestedPages = Math.max(1, Math.ceil(this.data.conversationSkip / PAGE_SIZE));
      const collected = [];
      let lastBatchSize = 0;
      let nextSkip = 0;
      for (let index = 0; index < requestedPages; index += 1) {
        const batch = await api.request(`/communications/conversations?limit=${PAGE_SIZE}&skip=${nextSkip}`);
        if (!this.isCurrentSession(sessionStamp)) return;
        const pageRows = Array.isArray(batch) ? batch : [];
        collected.push(...pageRows);
        lastBatchSize = pageRows.length;
        nextSkip += pageRows.length;
        if (pageRows.length < PAGE_SIZE) break;
      }
      if (!this.isCurrentSession(sessionStamp)) return;
      const rows = Array.from(new Map(collected.map(item => [item.id, item])).values())
        .map(item => ({ ...item, can_send: item.can_send === true, other_user: item.other_user || {} }));
      this.setData({ conversations: rows, conversationSkip: nextSkip,
        hasMoreConversations: lastBatchSize === PAGE_SIZE, error: '' });
      if (this.data.activeId) {
        const activeConversation = rows.find(item => item.id === this.data.activeId) || null;
        if (!activeConversation) {
          this._requestVersion += 1;
          this.setData({ activeId: '', activeConversation: null, messages: [] });
        }
        this.setActiveConversation(activeConversation);
        if (activeConversation) await this.loadMessages(this.data.activeId, true);
      }
    } catch (error) {
      if (!this.isCurrentSession(sessionStamp)) return;
      if (error.statusCode === 401) {
        this.expireSession();
      } else if (!silent) this.setData({ error: errorMessage(error, '加载会话列表失败，请重试。') });
    } finally {
      if (this.isCurrentSession(sessionStamp) && !silent) this.setData({ loading: false });
    }
  },

  async loadMoreConversations() {
    if (!this.data.session || !this.data.hasMoreConversations || this.data.loadingMoreConversations) return;
    const sessionStamp = this._sessionStamp;
    this.setData({ loadingMoreConversations: true, error: '' });
    try {
      const batch = await api.request(`/communications/conversations?limit=${PAGE_SIZE}&skip=${this.data.conversationSkip}`);
      if (!this.isCurrentSession(sessionStamp)) return;
      const rows = Array.isArray(batch) ? batch : [];
      const merged = new Map(this.data.conversations.map(item => [item.id, item]));
      rows.forEach(item => merged.set(item.id, { ...item, can_send: item.can_send === true, other_user: item.other_user || {} }));
      this.setData({ conversations: Array.from(merged.values()),
        conversationSkip: this.data.conversationSkip + rows.length,
        hasMoreConversations: rows.length === PAGE_SIZE });
    } catch (error) {
      if (!this.isCurrentSession(sessionStamp)) return;
      if (error.statusCode === 401) this.expireSession();
      else this.setData({ error: errorMessage(error, '加载更多会话失败，请重试。') });
    } finally {
      if (this.isCurrentSession(sessionStamp)) this.setData({ loadingMoreConversations: false });
    }
  },

  async loadMessages(conversationId, silent = false) {
    if (!conversationId) return;
    const version = ++this._requestVersion;
    const sessionStamp = this._sessionStamp;
    if (!silent) this.setData({ loadingMessages: true, messagesError: '' });
    try {
      const messages = await api.request(`/communications/conversations/${encodeURIComponent(conversationId)}/messages?limit=${PAGE_SIZE}`);
      if (!this.isCurrentSession(sessionStamp)
          || version !== this._requestVersion || this.data.activeId !== conversationId) return;
      const rows = Array.isArray(messages) ? messages : [];
      this.setData({ messages: rows, canLoadEarlier: rows.length === PAGE_SIZE, messagesError: '' });
      if (rows.some(message => message.sender_id !== this.data.session.user.id && !message.read)) {
        await api.request(`/communications/conversations/${encodeURIComponent(conversationId)}/read`, { method: 'PUT' });
        if (!this.isCurrentSession(sessionStamp) || version !== this._requestVersion) return;
        this.setData({ conversations: this.data.conversations.map(item => item.id === conversationId
          ? { ...item, unread_count: 0 } : item) });
      }
    } catch (error) {
      if (!this.isCurrentSession(sessionStamp)) return;
      if (error.statusCode === 401) {
        this.expireSession();
      } else if (version === this._requestVersion && !silent) {
        this.setData({ messagesError: errorMessage(error, '加载消息失败，请重试。') });
      }
    } finally {
      if (this.isCurrentSession(sessionStamp) && version === this._requestVersion && !silent) this.setData({ loadingMessages: false });
    }
  },

  async selectConversation(event) {
    const id = event.currentTarget.dataset.id;
    const conversation = this.data.conversations.find(item => item.id === id);
    if (!id || !conversation) return;
    this.setData({ activeId: id, messages: [], messagesError: '',
      notice: '', canLoadEarlier: false });
    this.setActiveConversation({ ...conversation, other_user: conversation.other_user || {} });
    await this.loadMessages(id);
  },

  setActiveConversation(conversation) {
    const sendStatusText = {
      care_relationship_ended: '医患管理关系已解除，历史消息仍可查看，双方不能继续发送。',
      account_invalid: '账号当前不可用，暂时不能发送消息。',
      access_unavailable: '当前会话暂不可发送消息。',
    };
    const activeConversation = conversation ? {
      ...conversation,
      can_send: conversation.can_send === true,
      send_status_text: sendStatusText[conversation.send_block_reason] || '当前会话暂不可发送消息。',
    } : null;
    const sendAllowed = !!(activeConversation && activeConversation.can_send);
    if (!sendAllowed) {
      this._pendingMessage = null;
      this.setData({ activeConversation, sendAllowed, draft: '', canSend: false });
      return;
    }
    this.setData({ activeConversation, sendAllowed });
  },

  async refreshActiveConversationStatus(conversationId, sessionStamp) {
    const conversation = await api.request(`/communications/conversations/${encodeURIComponent(conversationId)}`);
    if (!this.isCurrentSession(sessionStamp) || this.data.activeId !== conversationId) return;
    this.setActiveConversation({ ...conversation, other_user: conversation.other_user || {} });
  },

  async loadEarlier() {
    const { activeId, messages, loadingEarlier } = this.data;
    if (!activeId || !messages.length || loadingEarlier) return;
    const sessionStamp = this._sessionStamp;
    this.setData({ loadingEarlier: true, messagesError: '' });
    try {
      const beforeId = messages[0].id;
      const earlier = await api.request(`/communications/conversations/${encodeURIComponent(activeId)}/messages?limit=${PAGE_SIZE}&before_id=${encodeURIComponent(beforeId)}`);
      if (!this.isCurrentSession(sessionStamp) || this.data.activeId !== activeId) return;
      const rows = Array.isArray(earlier) ? earlier : [];
      const existingIds = new Set(this.data.messages.map(message => message.id));
      this.setData({ messages: [...rows.filter(message => !existingIds.has(message.id)), ...this.data.messages],
        canLoadEarlier: rows.length === PAGE_SIZE });
    } catch (error) {
      if (!this.isCurrentSession(sessionStamp)) return;
      if (error.statusCode === 401) this.expireSession();
      else this.setData({ messagesError: errorMessage(error, '加载更早消息失败，请重试。') });
    } finally {
      if (this.isCurrentSession(sessionStamp)) this.setData({ loadingEarlier: false });
    }
  },

  onDraftInput(event) {
    const draft = event.detail.value;
    if (this._pendingMessage && String(draft || '').trim() !== this._pendingMessage.content) {
      this._pendingMessage = null;
    }
    this.setData({ draft, canSend: !!String(draft || '').trim() });
  },

  async sendMessage() {
    const content = String(this.data.draft || '').trim();
    const conversationId = this.data.activeId;
    if (!content || !conversationId || !this.data.sendAllowed || this.data.sending) return;
    const sessionStamp = this._sessionStamp;
    this.setData({ sending: true, messagesError: '', notice: '' });
    try {
      if (!this._pendingMessage || this._pendingMessage.content !== content
          || this._pendingMessage.conversationId !== conversationId) {
        const id = await makeClientMessageId();
        if (!this.isCurrentSession(sessionStamp)) return;
        this._pendingMessage = { content, conversationId, id };
      }
      if (!this.isCurrentSession(sessionStamp)) return;
      const saved = await api.request(`/communications/conversations/${encodeURIComponent(conversationId)}/messages`, {
        method: 'POST',
        header: { 'content-type': 'application/json' },
        data: { content, type: 'text', client_message_id: this._pendingMessage.id },
      });
      if (!this.isCurrentSession(sessionStamp)) return;
      this._pendingMessage = null;
      if (this.data.activeId !== conversationId) return;
      this.setData({ draft: '', canSend: false, messages: [...this.data.messages, saved] });
      this.refreshAll(true);
    } catch (error) {
      if (!this.isCurrentSession(sessionStamp)) return;
      if (error.statusCode === 401) {
        this.expireSession();
      } else {
        if (error.statusCode === 403) {
          await this.refreshActiveConversationStatus(conversationId, sessionStamp).catch(() => {
            if (this.isCurrentSession(sessionStamp) && this.data.activeId === conversationId) {
              this.setActiveConversation({ ...(this.data.activeConversation || {}), can_send: false,
                send_block_reason: 'access_unavailable' });
            }
          });
          if (this.isCurrentSession(sessionStamp) && this.data.activeId === conversationId
              && this.data.activeConversation && !this.data.activeConversation.can_send) {
            this.setData({ messagesError: this.data.activeConversation.send_status_text });
          } else if (this.isCurrentSession(sessionStamp)) {
            this.setData({ messagesError: errorMessage(error, '消息发送失败，请重试。') });
          }
        } else this.setData({ messagesError: errorMessage(error, '消息发送失败，请重试。') });
      }
    } finally {
      if (this.isCurrentSession(sessionStamp)) this.setData({ sending: false });
    }
  },

  async refreshCurrent() {
    await this.refreshAll();
  },

  showContactDirectoryNotice() {
    this.setData({ contactPickerOpen: true, contactsError: '', notice: '' });
    this.loadContacts();
  },

  closeContactPicker() { this.setData({ contactPickerOpen: false }); },
  stopPropagation() {},

  async loadContacts() {
    if (!this.data.session || this.data.contactsLoading) return;
    const sessionStamp = this._sessionStamp;
    this.setData({ contactsLoading: true, contactsError: '' });
    try {
      const result = await api.request('/communications/contacts');
      if (!this.isCurrentSession(sessionStamp)) return;
      const contacts = Array.isArray(result) ? result : [];
      this.setData({ contacts: contacts.filter(item => item && item.id && item.role) });
    } catch (error) {
      if (!this.isCurrentSession(sessionStamp)) return;
      if (error.statusCode === 401) this.expireSession();
      else this.setData({ contactsError: errorMessage(error, '加载授权联系人失败，请重试。') });
    } finally {
      if (this.isCurrentSession(sessionStamp)) this.setData({ contactsLoading: false });
    }
  },

  async selectContact(event) {
    const participantId = event.currentTarget.dataset.id;
    const contact = this.data.contacts.find(item => item.id === participantId);
    if (!contact || !this.data.session || this.data.sending) return;
    const sessionStamp = this._sessionStamp;
    this.setData({ sending: true, contactsError: '' });
    try {
      const created = await api.request('/communications/authorized-conversations', {
        method: 'POST',
        header: { 'content-type': 'application/json' },
        data: { participant_id: contact.id, type: 'chat' },
      });
      if (!this.isCurrentSession(sessionStamp)) return;
      this.setData({ contactPickerOpen: false });
      await this.refreshAll();
      if (!this.isCurrentSession(sessionStamp)) return;
      const conversation = this.data.conversations.find(item => item.id === created.id);
      if (conversation) await this.selectConversation({ currentTarget: { dataset: { id: conversation.id } } });
      else this.setData({ notice: '会话已建立，列表暂未返回该会话，请刷新后查看。' });
    } catch (error) {
      if (!this.isCurrentSession(sessionStamp)) return;
      if (error.statusCode === 401) this.expireSession();
      else this.setData({ contactsError: errorMessage(error, '无法建立会话，请刷新联系人后重试。') });
    } finally {
      if (this.isCurrentSession(sessionStamp)) this.setData({ sending: false });
    }
  },
});

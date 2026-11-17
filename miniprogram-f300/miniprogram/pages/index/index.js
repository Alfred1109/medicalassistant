const { apiBaseUrl } = require('../../config');
const { veepooBle, veepooFeature } = require('../../libs/veepoo/index');
const { heartRateCallbackFailure, normalizeHeartRateCallback } = require('../../utils/readings');
const { createPkcePair, miniProgramRandomBytes } = require('../../utils/miniAuth');

const api = require('../../services/api');
const { request } = api;

function asArray(value) { return Array.isArray(value) ? value : (value && Array.isArray(value.items) ? value.items : []); }
function idOf(value) { return value ? String(value.id || value._id || value.patient_id || '') : ''; }

Page({
  data: {
    username: '', password: '', authMode: '', loggedIn: false, user: {}, roleLabel: '',
    identityConfirmed: false, oidcWebviewUrl: '', oidcLoading: false, oidcReadyUser: null, oidcReadyRoleLabel: '',
    patients: [], patientIndex: 0, devices: [], deviceIndex: 0, selectedDeviceId: '',
    scanResults: [], scanning: false, connected: false, authenticated: false,
    bleStatus: '未连接', hardwareId: '', firmware: '', heartRate: '', measuring: false,
    confirmUpload: false, confirmBinding: false, pendingReading: null, recentReadings: [], busy: false, message: '', activePanel: 'home',
  },
  _authTimer: null,
  _scanStartedAt: 0,
  _measurementStartedAt: 0,
  _lastHeartEvent: null,
  _oidcTransaction: null,
  _oidcPollTimer: null,
  _miniExpiryTimer: null,
  _oidcPollInFlight: false,
  _connectionGeneration: 0,
  _deviceListGeneration: 0,

  onLoad() {
    if (!apiBaseUrl) this.setData({ message: '需配置公开 HTTPS API 地址后才能连接系统。' });
    this.initializeAuthMode();
  },
  onShow() {
    if (this.data.loggedIn && this.data.identityConfirmed && !api.getSession()) this.expireOneIdSession();
  },
  onUnload() {
    this._connectionGeneration += 1;
    if (this.data.measuring) this.stopHeartRate();
    if (this.data.scanning) veepooBle.veepooWeiXinSDKStopSearchBleManager(() => {});
    if (this.data.connected) veepooBle.veepooWeiXinSDKloseBluetoothAdapterManager(() => {});
    if (this._authTimer) clearTimeout(this._authTimer);
    if (this._oidcPollTimer) clearTimeout(this._oidcPollTimer);
    if (this._miniExpiryTimer) clearTimeout(this._miniExpiryTimer);
    if (this._oidcTransaction) this.cancelOneIdTransaction(this._oidcTransaction, true);
    api.clearSession();
  },
  onUsernameInput(event) { this.setData({ username: event.detail.value }); },
  onPasswordInput(event) { this.setData({ password: event.detail.value }); },
  async withBusy(action) {
    if (this.data.busy) return;
    this.setData({ busy: true, message: '' });
    try { await action(); }
    catch (error) {
      if (error.statusCode === 401) {
        this.expireOneIdSession();
        wx.removeStorageSync('rehab_access_token');
      } else this.setData({ message: error.message || '操作失败' });
    } finally { this.setData({ busy: false }); }
  },
  async initializeAuthMode() {
    try {
      const config = await request('/auth/config', { noAuth: true });
      const mode = config && config.mode;
      if (mode !== 'legacy' && mode !== 'oidc') throw new Error('系统登录配置无效。');
      this.setData({ authMode: mode });
      if (mode === 'oidc') {
        wx.removeStorageSync('rehab_access_token');
        if (api.getMiniToken()) api.clearSession();
        return;
      }
      api.clearSession();
      if (wx.getStorageSync('rehab_access_token')) await this.restoreLegacySession();
    } catch (error) {
      this.setData({ message: error.message || '无法读取系统登录配置。' });
    }
  },
  async login() {
    if (this.data.authMode !== 'legacy') {
      return this.setData({ message: '当前系统使用 OneID，请点击 OneID 登录。' });
    }
    const username = String(this.data.username || '').trim();
    const password = String(this.data.password || '');
    if (!username || !password) return this.setData({ message: '请输入用户名和密码。' });
    this.setData({ busy: true, message: '' });
    try {
      const body = `username=${encodeURIComponent(username)}&password=${encodeURIComponent(password)}`;
      const token = await request('/users/login', { method: 'POST', noAuth: true, data: body,
        header: { 'content-type': 'application/x-www-form-urlencoded' } });
      if (!token || !token.access_token) throw new Error('登录响应缺少访问令牌。');
      wx.setStorageSync('rehab_access_token', token.access_token);
      this.setData({ password: '' });
      await this.finishLogin(token.user);
    } catch (error) { this.setData({ message: error.message || '登录失败' }); }
    finally { this.setData({ busy: false }); }
  },
  async restoreLegacySession() {
    this.setData({ busy: true, message: '' });
    try {
      const config = await request('/auth/config', { noAuth: true });
      this.setData({ authMode: config.mode || '' });
      if (config.mode !== 'legacy' || config.oidc_enabled) {
        wx.removeStorageSync('rehab_access_token');
        this.setData({ authMode: config.mode || 'oidc' });
        throw new Error('系统已切换到 OneID，请使用 OneID 登录。');
      }
      await this.finishLogin(await request('/users/me'));
    } catch (error) {
      wx.removeStorageSync('rehab_access_token');
      this.setData({ loggedIn: false, message: error.message || '无法恢复登录状态，请重新登录。' });
    } finally { this.setData({ busy: false }); }
  },
  async finishLogin(user) {
    if (!user) user = await request('/users/me');
    const roleLabels = { patient: '患者', doctor: '医生', health_manager: '健康管理师', admin: '管理员' };
    api.setSession(user);
    this.setData({ loggedIn: true, identityConfirmed: true, user, roleLabel: roleLabels[user.role] || user.role || '用户', message: '' });
    await this.loadPatientsAndDevices();
    this.openRoleHome(user.role);
  },
  async startOneIdLogin() {
    if (this.data.authMode !== 'oidc' || this.data.oidcLoading || this._oidcTransaction) return;
    this.setData({ oidcLoading: true, message: '' });
    try {
      const pair = await createPkcePair(miniProgramRandomBytes);
      const created = await request('/auth/mini/transactions', {
        method: 'POST', noAuth: true, data: { code_challenge: pair.challenge },
        header: { 'content-type': 'application/json' },
      });
      if (!created || typeof created.transaction_id !== 'string' || !created.transaction_id
          || typeof created.webview_url !== 'string' || !Number.isFinite(Number(created.expires_in))) {
        throw new Error('OneID 登录初始化响应无效。');
      }
      this.assertTrustedWebviewUrl(created.webview_url);
      this._oidcTransaction = {
        id: created.transaction_id,
        verifier: pair.verifier,
        expiresAt: Date.now() + Math.max(1, Number(created.expires_in)) * 1000,
        pollInterval: Math.max(1, Math.min(5, Number(created.poll_interval) || 2)),
        readyUser: null,
      };
      this.setData({ oidcWebviewUrl: created.webview_url, message: '请在 OneID 页面完成登录。' });
      this.scheduleOidcPoll(0);
    } catch (error) {
      this.setData({ message: error.message || '无法启动 OneID 登录。' });
    } finally {
      this.setData({ oidcLoading: false });
    }
  },
  assertTrustedWebviewUrl(value) {
    const base = String(apiBaseUrl || '').match(/^(https:\/\/[^/]+)/i);
    if (!base || !value.startsWith(`${base[1]}/`) || /[?#].*(verifier|token|secret|challenge)=/i.test(value)) {
      throw new Error('OneID 登录页面地址不可信，已停止打开。');
    }
  },
  onOneIdWebviewMessage() {
    // The web-view message is only a wake-up hint; authentication state always
    // comes from the server-side transaction poll, never from message data.
    this.scheduleOidcPoll(0);
  },
  scheduleOidcPoll(delayMs) {
    if (this._oidcPollTimer) clearTimeout(this._oidcPollTimer);
    if (!this._oidcTransaction) return;
    this._oidcPollTimer = setTimeout(() => this.pollOneIdTransaction(), Math.max(0, delayMs));
  },
  async pollOneIdTransaction() {
    const transaction = this._oidcTransaction;
    if (!transaction || this._oidcPollInFlight) return;
    if (Date.now() >= transaction.expiresAt) {
      this.finishOneIdTransaction('OneID 登录已过期，请重新开始。');
      return;
    }
    this._oidcPollInFlight = true;
    try {
      const result = await request(`/auth/mini/transactions/${encodeURIComponent(transaction.id)}/poll`, {
        method: 'POST', noAuth: true, data: { verifier: transaction.verifier },
        header: { 'content-type': 'application/json' },
      });
      if (this._oidcTransaction !== transaction) return;
      if (result.status === 'ready') {
        transaction.readyUser = result.user;
        if (!result.user || !result.user.id || !result.user.role || !result.user.display_name) {
          this.finishOneIdTransaction('OneID 返回的账号信息不完整，无法继续。');
          return;
        }
        this.setData({ oidcWebviewUrl: '', oidcReadyUser: result.user,
          oidcReadyRoleLabel: this.roleLabelFor(result.user.role),
          message: '请先核对 OneID 账号和角色，再确认继续。' });
        return;
      }
      if (result.status === 'denied') {
        this.finishOneIdTransaction('OneID 账号尚未完成系统授权，暂时不能进入患者数据。');
        return;
      }
      if (result.status === 'expired') {
        this.finishOneIdTransaction('OneID 登录已过期，请重新开始。');
        return;
      }
      if (!['pending', 'oidc_started', 'awaiting_confirmation'].includes(result.status)) {
        throw new Error('OneID 登录状态响应无效。');
      }
      this.scheduleOidcPoll(transaction.pollInterval * 1000);
    } catch (error) {
      if (this._oidcTransaction === transaction) {
        this.setData({ message: error.message || '查询 OneID 登录状态失败，正在重试。' });
        this.scheduleOidcPoll(transaction.pollInterval * 1000);
      }
    } finally {
      this._oidcPollInFlight = false;
    }
  },
  sameConfirmedIdentity(expected, actual) {
    if (!expected || !actual) return false;
    const expectedId = String(expected.id || '');
    const actualId = String(actual.id || actual.actor_id || '');
    return !!expectedId && expectedId === actualId && expected.role === actual.role;
  },
  async confirmOneIdActor() {
    const transaction = this._oidcTransaction;
    if (!transaction || !transaction.readyUser || !this.data.oidcReadyUser || this.data.busy) return;
    this.setData({ busy: true, message: '' });
    try { await this.exchangeOneIdTransaction(transaction); }
    finally { this.setData({ busy: false }); }
  },
  async exchangeOneIdTransaction(transaction) {
    try {
      const result = await request(`/auth/mini/transactions/${encodeURIComponent(transaction.id)}/exchange`, {
        method: 'POST', noAuth: true, data: { verifier: transaction.verifier },
        header: { 'content-type': 'application/json' },
      });
      if (!result || typeof result.access_token !== 'string' || !result.access_token
          || String(result.token_type || '').toLowerCase() !== 'bearer'
          || !Number.isFinite(Number(result.expires_in)) || Number(result.expires_in) < 1
          || !this.sameConfirmedIdentity(transaction.readyUser, result.user)) {
        throw new Error('OneID 会话身份核对失败，未登录。');
      }
      api.setMiniToken(result.access_token);
      const user = result.user;
      const displayName = user.display_name || user.name || user.full_name || user.email || user.id;
      this._oidcTransaction = null;
      if (this._oidcPollTimer) clearTimeout(this._oidcPollTimer);
      this.setData({ oidcWebviewUrl: '', oidcReadyUser: null, oidcReadyRoleLabel: '', loggedIn: true, identityConfirmed: false,
        user: { ...user, name: displayName }, roleLabel: this.roleLabelFor(user.role),
        patients: [], devices: [], selectedDeviceId: '', message: '',
        identityReview: { displayName, id: user.id, role: this.roleLabelFor(user.role) } });
      if (this._miniExpiryTimer) clearTimeout(this._miniExpiryTimer);
      this._miniExpiryTimer = setTimeout(() => this.expireOneIdSession(),
        Math.min(Number(result.expires_in), 3600) * 1000);
    } catch (error) {
      api.clearSession();
      this.finishOneIdTransaction(error.message || 'OneID 会话兑换失败，请重新登录。');
    } finally {
      this._oidcTransaction = null;
      this._oidcPollInFlight = false;
    }
  },
  roleLabelFor(role) {
    const labels = { patient: '患者', doctor: '医生', health_manager: '健康管理师', admin: '管理员' };
    return labels[role] || role || '未知角色';
  },
  openCapture() {
    if (!this.data.loggedIn || !this.data.identityConfirmed) return;
    this.setData({ activePanel: 'device' });
  },
  openRoleHome(role) {
    if (typeof wx.navigateTo !== 'function') return;
    const url = role === 'patient' ? '/pages/patient/home/index'
      : (role === 'doctor' || role === 'health_manager' ? '/pages/clinical/index/index?view=workbench' : '');
    if (url) wx.navigateTo({ url });
  },
  openHome() { this.setData({ activePanel: 'home' }); },
  openPage(event) {
    if (!this.data.loggedIn || !this.data.identityConfirmed) return;
    const paths = {
      patientHome: '/pages/patient/home/index', plans: '/pages/patient/plans/index',
      records: '/pages/patient/records/index', followups: '/pages/patient/followups/index',
      clinical: '/pages/clinical/index/index?view=workbench',
      patients: '/pages/clinical/index/index?view=patients',
      staffFollowups: '/pages/clinical/index/index?view=followups',
      messages: '/pages/messages/index/index', profile: '/pages/profile/index/index',
    };
    const path = paths[event.currentTarget.dataset.page];
    if (path) wx.navigateTo({ url: path });
  },
  async confirmOneIdIdentity() {
    if (!api.getMiniToken() || !this.data.loggedIn || this.data.identityConfirmed) return;
    this.setData({ busy: true, message: '' });
    try {
      // Re-fetch the authenticated principal after exchange before exposing any
      // patient/device actions. The display is bound to the server session.
      const user = await request('/users/me');
      if (!this.sameConfirmedIdentity(this.data.user, user)) throw new Error('账号状态与 OneID 登录确认不一致，请重新登录。');
      api.setSession(user);
      this.setData({ identityConfirmed: true, user: { ...user, name: user.name || user.full_name || user.email },
        roleLabel: this.roleLabelFor(user.role), identityReview: null });
      await this.loadPatientsAndDevices();
      this.openRoleHome(user.role);
    } catch (error) {
      this.setData({ message: error.message || '无法确认登录账号。' });
    } finally {
      this.setData({ busy: false });
    }
  },
  finishOneIdTransaction(message) {
    const transaction = this._oidcTransaction;
    this._oidcTransaction = null;
    this._oidcPollInFlight = false;
    if (this._oidcPollTimer) clearTimeout(this._oidcPollTimer);
    this.setData({ oidcWebviewUrl: '', oidcReadyUser: null, oidcReadyRoleLabel: '', message: message || '' });
    if (transaction) this.cancelOneIdTransaction(transaction, true);
  },
  cancelOneIdTransaction(transaction, quiet) {
    if (!transaction) return Promise.resolve();
    return request(`/auth/mini/transactions/${encodeURIComponent(transaction.id)}/cancel`, {
      method: 'POST', noAuth: true, data: { verifier: transaction.verifier },
      header: { 'content-type': 'application/json' },
    }).catch(() => { if (!quiet) this.setData({ message: '登录已在本机取消，服务器事务会在短时限后过期。' }); });
  },
  async cancelOneIdLogin() {
    const transaction = this._oidcTransaction;
    this._oidcTransaction = null;
    if (this._oidcPollTimer) clearTimeout(this._oidcPollTimer);
    this.setData({ oidcWebviewUrl: '', oidcReadyUser: null, oidcReadyRoleLabel: '', message: '已取消 OneID 登录。' });
    await this.cancelOneIdTransaction(transaction, true);
  },
  expireOneIdSession() {
    if (this._miniExpiryTimer) clearTimeout(this._miniExpiryTimer);
    this._connectionGeneration += 1;
    this._deviceListGeneration += 1;
    if (this._authTimer) clearTimeout(this._authTimer);
    if (this.data.measuring) this.stopHeartRate();
    if (this.data.scanning) veepooBle.veepooWeiXinSDKStopSearchBleManager(() => {});
    if (this.data.connected) veepooBle.veepooWeiXinSDKloseBluetoothAdapterManager(() => {});
    api.clearSession();
    this._miniExpiryTimer = null;
    this.setData({ loggedIn: false, identityConfirmed: false, user: {}, patients: [], devices: [],
      selectedDeviceId: '', pendingReading: null, recentReadings: [], confirmUpload: false, identityReview: null, activePanel: 'home',
      scanning: false, scanResults: [], connected: false, authenticated: false,
      hardwareId: '', firmware: '', heartRate: '', measuring: false, bleStatus: '未连接',
      message: '登录已失效或会话已到期，请重新登录。' });
  },
  async logout() {
    this._connectionGeneration += 1;
    this._deviceListGeneration += 1;
    if (this._authTimer) clearTimeout(this._authTimer);
    if (this.data.measuring) this.stopHeartRate();
    if (this.data.connected) veepooBle.veepooWeiXinSDKloseBluetoothAdapterManager(() => {});
    const oldMiniToken = api.getMiniToken();
    api.clearSession();
    if (this._miniExpiryTimer) clearTimeout(this._miniExpiryTimer);
    this._miniExpiryTimer = null;
    wx.removeStorageSync('rehab_access_token');
    const transaction = this._oidcTransaction;
    this._oidcTransaction = null;
    if (this._oidcPollTimer) clearTimeout(this._oidcPollTimer);
    this.setData({ loggedIn: false, identityConfirmed: false, oidcWebviewUrl: '', oidcReadyUser: null, oidcReadyRoleLabel: '',
      user: {}, patients: [], devices: [], selectedDeviceId: '', connected: false, authenticated: false,
      hardwareId: '', firmware: '', pendingReading: null, recentReadings: [], confirmUpload: false, identityReview: null, activePanel: 'home',
      message: '已退出登录。' });
    if (transaction) await this.cancelOneIdTransaction(transaction, true);
    if (oldMiniToken) {
      await request('/auth/mini/session/logout', { method: 'POST', noAuth: true,
        accessToken: oldMiniToken, header: { 'content-type': 'application/json' } }).catch(() => {});
    }
  },
  async loadPatientsAndDevices() {
    if (!this.data.loggedIn || !this.data.identityConfirmed) throw new Error('请先完成登录身份确认。');
    const { user } = this.data;
    if (user.role === 'patient') {
      const self = await request('/users/me');
      this.setData({ patients: [{ ...self, id: idOf(self), name: self.name || self.email }], patientIndex: 0 });
    } else if (user.role === 'doctor') {
      const patients = asArray(await request('/doctors/patients?limit=100'));
      this.setData({ patients: patients.map((p) => ({ ...p, id: idOf(p), name: p.name || p.full_name || p.email || idOf(p) })), patientIndex: 0 });
    } else if (user.role === 'health_manager') {
      const patients = asArray(await request('/health-managers/patients?limit=100'));
      this.setData({ patients: patients.map((p) => ({ ...p, id: idOf(p), name: p.name || p.full_name || p.email || idOf(p) })), patientIndex: 0 });
    } else {
      this.setData({ patients: [], message: '当前账号角色不能从本原型选择患者。' });
      return;
    }
    if (this.data.patients.length) await this.loadDevices();
  },
  async loadDevices() {
    if (!this.data.loggedIn || !this.data.identityConfirmed) throw new Error('请先完成登录身份确认。');
    const patient = this.data.patients[this.data.patientIndex];
    if (!patient) return;
    const generation = ++this._deviceListGeneration;
    const { user } = this.data;
    const query = user.role === 'patient' ? '' : `?patient_id=${encodeURIComponent(idOf(patient))}`;
    const devices = asArray(await request(`/devices/${query}`));
    if (generation !== this._deviceListGeneration || !api.getSession()) return;
    const eligible = devices.filter((device) => String(device.model || '').toLowerCase().includes('f300') && device.status !== 'deleted');
    this.setData({ devices: eligible, deviceIndex: 0, selectedDeviceId: idOf(eligible[0]), pendingReading: null, recentReadings: [], confirmUpload: false,
      message: eligible.length ? '' : '该患者没有已登记的 F300。请先在系统设备管理中登记并绑定 F300。' });
    if (eligible.length) await this.loadRecentReadings(idOf(eligible[0]));
  },
  async loadRecentReadings(deviceId) {
    if (!deviceId) return;
    try {
      const records = asArray(await request(`/devices/${encodeURIComponent(deviceId)}/data?data_type=heart_rate&limit=10`));
      if (this.data.selectedDeviceId !== deviceId || !api.getSession()) return;
      this.setData({ recentReadings: records });
    } catch (error) {
      if (this.data.selectedDeviceId === deviceId) this.setData({ recentReadings: [], message: error.message || '无法读取设备记录。' });
    }
  },
  async onPatientChange(event) {
    this._connectionGeneration += 1;
    this._deviceListGeneration += 1;
    if (this._authTimer) clearTimeout(this._authTimer);
    if (this.data.measuring) this.stopHeartRate();
    if (this.data.scanning) veepooBle.veepooWeiXinSDKStopSearchBleManager(() => {});
    if (this.data.connected) veepooBle.veepooWeiXinSDKloseBluetoothAdapterManager(() => {});
    this._lastHeartEvent = null;
    this.setData({ patientIndex: Number(event.detail.value), devices: [], selectedDeviceId: '', pendingReading: null, recentReadings: [],
      confirmUpload: false, confirmBinding: false, scanning: false, scanResults: [], connected: false,
      authenticated: false, hardwareId: '', firmware: '', heartRate: '', measuring: false, bleStatus: '未连接' });
    await this.withBusy(() => this.loadDevices());
  },
  onDeviceChange(event) {
    this._connectionGeneration += 1;
    if (this._authTimer) clearTimeout(this._authTimer);
    if (this.data.measuring) this.stopHeartRate();
    if (this.data.connected) veepooBle.veepooWeiXinSDKloseBluetoothAdapterManager(() => {});
    this._lastHeartEvent = null;
    const deviceIndex = Number(event.detail.value);
    const device = this.data.devices[deviceIndex];
    this.setData({ deviceIndex, selectedDeviceId: idOf(device), pendingReading: null, recentReadings: [], confirmUpload: false,
      hardwareId: '', firmware: '', connected: false, authenticated: false, bleStatus: '未连接' });
    this.loadRecentReadings(idOf(device));
  },
  onPullDownRefresh() { this.withBusy(() => this.loadPatientsAndDevices()).finally(() => wx.stopPullDownRefresh()); },
  scan() {
    if (!this.data.loggedIn || !this.data.identityConfirmed) return this.setData({ message: '请先完成登录身份确认。' });
    if (!this.data.patients.length) return this.setData({ message: '请先选择一个有权访问的患者。' });
    this.setData({ scanning: true, scanResults: [], message: '正在扫描。请让手环靠近手机。' });
    this._scanStartedAt = Date.now();
    veepooBle.veepooWeiXinSDKStartScanDeviceAndReceiveScanningDevice((results) => {
      if (!this.data.scanning) return;
      if (results && results.errCode) return this.setData({ scanning: false, bleStatus: '蓝牙不可用', message: results.errMsg || '无法启动蓝牙扫描。' });
      const incoming = Array.isArray(results) ? results : [results];
      const existing = this.data.scanResults.slice();
      incoming.filter(Boolean).forEach((item) => {
        const index = existing.findIndex((old) => old.deviceId === item.deviceId);
        if (index >= 0) existing[index] = { ...existing[index], ...item };
        else existing.push(item);
      });
      this.setData({ scanResults: existing, message: existing.length ? '请选择实体 F300。请核对型号后再连接。' : this.data.message });
    });
    setTimeout(() => {
      if (!this.data.scanning) return;
      veepooBle.veepooWeiXinSDKStopSearchBleManager(() => {});
      this.setData({ scanning: false, message: this.data.scanResults.length ? this.data.message : '扫描结束，未发现设备。请检查手环电量和蓝牙权限后重试。' });
    }, 12000);
  },
  connect(event) {
    const deviceId = event.currentTarget.dataset.deviceid;
    const device = this.data.scanResults.find((item) => item.deviceId === deviceId);
    if (!device) return;
    const generation = ++this._connectionGeneration;
    if (this.data.scanning) veepooBle.veepooWeiXinSDKStopSearchBleManager(() => {});
    this.setData({ scanning: false, connected: false, authenticated: false, hardwareId: '', firmware: '', bleStatus: '连接中', message: '' });
    veepooBle.veepooWeiXinSDKBleConnectionServicesCharacteristicsNotifyManager(device, (result) => {
      if (generation !== this._connectionGeneration) {
        if (result && result.connection) veepooBle.veepooWeiXinSDKloseBluetoothAdapterManager(() => {});
        return;
      }
      if (!result || !result.connection) {
        this.setData({ bleStatus: '连接失败', message: (result && result.errMsg) || '未能建立手环连接。' });
        return;
      }
      this.setData({ connected: true, bleStatus: '已连接，验证设备中…' });
      veepooBle.veepooWeiXinSDKNotifyMonitorValueChange((payload) => {
        if (generation === this._connectionGeneration) this.onSdkEvent(payload);
      });
      veepooBle.veepooWeiXinSDKBLEConnectionStateChangeManager((state) => {
        if (generation !== this._connectionGeneration) return;
        if (state && (state.connected === false || state.connection === false)) {
          this.setData({ connected: false, authenticated: false, measuring: false, bleStatus: '连接已断开' });
        }
      });
      this._authTimer = setTimeout(() => {
        if (generation === this._connectionGeneration) veepooFeature.veepooBlePasswordCheckManager({ isPair: true });
      }, 500);
    });
  },
  onSdkEvent(event) {
    if (!event) return;
    if (Number(event.type) === 1) {
      const content = event.content || {};
      const verified = content.VPDevicepassword === 'successfulVerification' || content.passwordCheck === true || content.authenticated === true;
      const mac = String(content.VPDeviceMAC || content.mac || '').trim();
      if (verified && mac) {
      this.setData({ authenticated: true, hardwareId: mac, firmware: String(content.VPDeviceVersion || ''), bleStatus: '已连接并通过设备认证', message: '' });
      } else if (verified && !mac) {
        this.setData({ authenticated: false, bleStatus: '设备标识缺失', message: 'SDK 未返回稳定 VPDeviceMAC，暂不能安全匹配系统设备。' });
      } else {
        this.setData({ authenticated: false, bleStatus: '设备认证未通过', message: 'F300 未通过设备密钥认证。请检查设备型号和厂商兼容性。' });
      }
      return;
    }
    if (Number(event.type) === 51 && this.data.measuring) {
      const failure = heartRateCallbackFailure(event);
      if (failure) {
        this._lastHeartEvent = null;
        veepooFeature.veepooSendHeartRateTestSwitchManager({ switch: false });
        this.setData({ measuring: false, heartRate: '', pendingReading: null, confirmUpload: false,
          message: failure === 'device_busy' ? '设备正忙，本次不保存读数。请稍后重试。' : '设备未检测到佩戴，本次不保存读数。请正确佩戴后重试。' });
        return;
      }
      const reading = normalizeHeartRateCallback(event, this.data.hardwareId, Date.now());
      if (!reading) return;
      this._lastHeartEvent = reading;
      this.setData({ heartRate: reading.value, message: '收到一条实时心率回调。结束测量后可确认并上传。' });
    }
  },
  startHeartRate() {
    if (!this.data.loggedIn || !this.data.identityConfirmed) return this.setData({ message: '请先完成登录身份确认。' });
    if (!this.data.authenticated) return this.setData({ message: '请先连接设备并通过认证。' });
    this._measurementStartedAt = Date.now();
    this._lastHeartEvent = null;
    this.setData({ measuring: true, heartRate: '', pendingReading: null, confirmUpload: false, message: '请保持佩戴和静止，等待设备返回测量值。' });
    veepooFeature.veepooSendHeartRateTestSwitchManager({ switch: true });
  },
  stopHeartRate() {
    if (this.data.measuring) veepooFeature.veepooSendHeartRateTestSwitchManager({ switch: false });
    const pendingReading = this._lastHeartEvent;
    this.setData({ measuring: false, pendingReading: pendingReading || null, confirmUpload: false,
      message: pendingReading ? '测量已结束。确认患者和这条读数后再上传。' : '本次测量没有收到有效心率回调。' });
    this._lastHeartEvent = null;
  },
  onConfirmChange(event) { this.setData({ confirmUpload: (event.detail.value || []).includes('confirmed') }); },
  onBindingConfirmChange(event) { this.setData({ confirmBinding: (event.detail.value || []).includes('confirmed') }); },
  bindConnectedDevice() {
    if (!this.data.loggedIn || !this.data.identityConfirmed) return this.setData({ message: '请先完成登录身份确认。' });
    const patient = this.data.patients[this.data.patientIndex];
    const hardwareId = this.data.hardwareId;
    if (!patient || !this.data.authenticated || !hardwareId || !this.data.confirmBinding) return;
    this.withBusy(async () => {
      const payload = {
        device_type: '手环', name: 'Veepoo F300', manufacturer: 'Veepoo',
        model: 'F300', connection_type: 'bluetooth', settings: { claimed_hardware_id: hardwareId },
      };
      if (this.data.user.role !== 'patient') payload.patient_id = idOf(patient);
      const device = await request('/devices/bind', { method: 'POST', data: payload,
        header: { 'content-type': 'application/json' } });
      const deviceId = idOf(device);
      if (!deviceId) throw new Error('设备已提交绑定，但服务器响应缺少设备编号。请刷新设备列表核对。');
      this.setData({ selectedDeviceId: deviceId, devices: [device], deviceIndex: 0, confirmBinding: false,
        message: 'F300 已登记到所选患者。后端首次上传时还会核对并固定手环 MAC。' });
    });
  },
  uploadReading() {
    if (!this.data.loggedIn || !this.data.identityConfirmed) return this.setData({ message: '请先完成登录身份确认。' });
    const { pendingReading, selectedDeviceId, hardwareId } = this.data;
    if (!pendingReading || !selectedDeviceId || !hardwareId || !this.data.confirmUpload) return;
    this.withBusy(async () => {
      const payload = { hardware_id: hardwareId, readings: [pendingReading] };
      const result = await request(`/devices/${encodeURIComponent(selectedDeviceId)}/veepoo/readings`, { method: 'POST', data: payload,
        header: { 'content-type': 'application/json' } });
      const accepted = Number(result.accepted_count || 0);
      const duplicate = Number(result.duplicate_count || 0);
      const rejected = Number(result.rejected_count || 0);
      if (rejected || (accepted === 0 && duplicate === 0)) {
        const reason = (result.results || []).map((item) => item.reason || item.message).filter(Boolean).join('；');
        this.setData({ message: `服务器未确认读数入库${reason ? `：${reason}` : ''}。待上传读数已保留，可核对后重试。` });
        return;
      }
      this.setData({ pendingReading: null, confirmUpload: false,
        message: accepted > 0 ? `上传完成：服务器接收 ${accepted} 条读数。` : `这条读数此前已上传：重复 ${duplicate} 条，本地待上传记录已清除。` });
      await this.loadRecentReadings(selectedDeviceId);
    });
  },
  disconnect() {
    this._connectionGeneration += 1;
    if (this._authTimer) clearTimeout(this._authTimer);
    if (this.data.measuring) this.stopHeartRate();
    veepooBle.veepooWeiXinSDKloseBluetoothAdapterManager(() => this.setData({ connected: false, authenticated: false, bleStatus: '已断开' }));
    this.setData({ connected: false, authenticated: false, measuring: false, bleStatus: '已断开' });
  },
});

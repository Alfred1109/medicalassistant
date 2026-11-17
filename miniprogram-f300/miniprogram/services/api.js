const { apiBaseUrl } = require('../config');

function createClient(baseUrl, getWx = () => wx) {
  let miniToken = '';
  let session = null;
  let sessionSequence = 0;

  function request(path, options = {}) {
    const base = String(baseUrl || '').replace(/\/+$/, '');
    if (!/^https:\/\//i.test(base)) return Promise.reject(new Error('请先配置系统 HTTPS API 地址。'));
    const runtime = getWx();
    return new Promise((resolve, reject) => {
      const token = options.accessToken || miniToken || runtime.getStorageSync('rehab_access_token');
      const headers = { ...(options.header || {}) };
      if (token && (!options.noAuth || options.accessToken)) headers.Authorization = `Bearer ${token}`;
      runtime.request({
        url: `${base}${path}`, method: options.method || 'GET', data: options.data,
        header: headers, timeout: options.timeout || 15000,
        success(response) {
          if (response.statusCode >= 200 && response.statusCode < 300) return resolve(response.data);
          // A response from an old login must not sign out a newer session.
          if (response.statusCode === 401 && !options.noAuth && token === miniToken) {
            miniToken = '';
            session = null;
            runtime.removeStorageSync('rehab_access_token');
          }
          const detail = response.data && (response.data.detail || response.data.message || response.data.code);
          const message = typeof detail === 'string' ? detail : (detail && (detail.message || detail.code));
          const error = new Error(typeof message === 'string' ? message : `请求失败（HTTP ${response.statusCode}）`);
          error.statusCode = response.statusCode;
          error.payload = response.data;
          reject(error);
        },
        fail(error) { reject(new Error(error.errMsg || '网络请求失败')); },
      });
    });
  }

  function uploadFile(path, filePath, name = 'file') {
    const base = String(baseUrl || '').replace(/\/+$/, '');
    if (!/^https:\/\//i.test(base)) return Promise.reject(new Error('请先配置系统 HTTPS API 地址。'));
    const runtime = getWx();
    const token = miniToken || runtime.getStorageSync('rehab_access_token');
    const sequence = sessionSequence;
    return new Promise((resolve, reject) => {
      runtime.uploadFile({
        url: `${base}${path}`, filePath, name,
        header: token ? { Authorization: `Bearer ${token}` } : {}, timeout: 60000,
        success(response) {
          if (sequence !== sessionSequence || token !== (miniToken || runtime.getStorageSync('rehab_access_token'))) {
            return reject(new Error('登录状态已变化，请重新选择视频后重试。'));
          }
          let payload = response.data;
          if (typeof payload === 'string') {
            try { payload = JSON.parse(payload); } catch (_) { payload = null; }
          }
          if (response.statusCode >= 200 && response.statusCode < 300) return resolve(payload);
          if (response.statusCode === 401 && token === miniToken) {
            miniToken = ''; session = null; runtime.removeStorageSync('rehab_access_token');
          }
          const detail = payload && (payload.detail || payload.message || payload.code);
          const message = typeof detail === 'string' ? detail : (detail && (detail.message || detail.code));
          const error = new Error(typeof message === 'string' ? message : `上传失败（HTTP ${response.statusCode}）`);
          error.statusCode = response.statusCode; error.payload = payload;
          reject(error);
        },
        fail(error) { reject(new Error(error.errMsg || '视频上传失败，请检查网络后重试。')); },
      });
    });
  }

  return {
    request,
    uploadFile,
    setMiniToken(value) { miniToken = value || ''; },
    getMiniToken() { return miniToken; },
    setSession(user) {
      sessionSequence += 1;
      session = user ? { user, role: user.role, identityConfirmed: true, sessionId: sessionSequence } : null;
    },
    getSession() { return session; },
    clearSession() { sessionSequence += 1; miniToken = ''; session = null; },
  };
}

module.exports = { ...createClient(apiBaseUrl), createClient };

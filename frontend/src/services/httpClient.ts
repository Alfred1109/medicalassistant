import axios from 'axios';
import { API_BASE_URL, STORAGE_KEYS } from '../config/constants';
import { assertSameOrigin, csrfHeaders, getAuthConfig, loginPageUrl } from './authSession';

// Response and data-only API adapters share one authentication boundary.
const httpClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 10000,
  headers: { 'Content-Type': 'application/json' },
});

let pendingRefresh: { token: string; refreshToken: string; promise: Promise<string> } | null = null;

const isCredentialRequest = (url = '') => /\/users\/(login|register|refresh-token)(?:[/?]|$)/.test(url);

const isCurrentSession = (token: string, refreshToken: string) =>
  localStorage.getItem(STORAGE_KEYS.TOKEN) === token &&
  localStorage.getItem(STORAGE_KEYS.REFRESH_TOKEN) === refreshToken;

function clearAuthentication(): void {
  for (const key of [STORAGE_KEYS.TOKEN, STORAGE_KEYS.REFRESH_TOKEN,
    STORAGE_KEYS.USER, STORAGE_KEYS.TOKEN_EXPIRY]) localStorage.removeItem(key);
  if (!window.location.pathname.includes('/login')) window.location.href = loginPageUrl();
}

async function refreshAccessToken(token: string, refreshToken: string): Promise<string> {
  try {
    // Raw Axios deliberately has no application interceptors: refresh cannot recurse.
    const { data } = await axios.post(`${API_BASE_URL}/users/refresh-token`, {
      refresh_token: refreshToken,
    }, { timeout: 10000 });
    if (typeof data.access_token !== 'string' || !data.access_token ||
        typeof data.refresh_token !== 'string' || !data.refresh_token ||
        typeof data.expires_in !== 'number' || !Number.isFinite(data.expires_in) || data.expires_in <= 0) {
      throw new Error('令牌刷新响应无效');
    }
    if (!isCurrentSession(token, refreshToken)) throw new Error('登录状态已变化，请重新发起请求');
    localStorage.setItem(STORAGE_KEYS.TOKEN, data.access_token);
    localStorage.setItem(STORAGE_KEYS.REFRESH_TOKEN, data.refresh_token);
    localStorage.setItem(STORAGE_KEYS.TOKEN_EXPIRY, String(Date.now() + data.expires_in * 1000));
    return data.access_token;
  } catch (error) {
    if (isCurrentSession(token, refreshToken)) clearAuthentication();
    throw error;
  }
}

httpClient.interceptors.request.use(async (config) => {
  const authentication = await getAuthConfig();
  if (authentication.mode === 'oidc') {
    assertSameOrigin(new URL(config.url || '', new URL(`${API_BASE_URL}/`, window.location.origin)).href);
    config.withCredentials = true;
    config.headers.delete('Authorization');
    for (const [name, value] of Object.entries(csrfHeaders(config.method))) config.headers.set(name, value);
    return config;
  }
  let token = localStorage.getItem(STORAGE_KEYS.TOKEN);
  const expiry = localStorage.getItem(STORAGE_KEYS.TOKEN_EXPIRY);
  const refreshToken = localStorage.getItem(STORAGE_KEYS.REFRESH_TOKEN);
  // Credential entry and refresh must remain callable even with an expired old session.
  const credentialRequest = isCredentialRequest(config.url);
  if (!credentialRequest && token && expiry && refreshToken && Number(expiry) - Date.now() < 5 * 60 * 1000) {
    if (!pendingRefresh || pendingRefresh.token !== token || pendingRefresh.refreshToken !== refreshToken) {
      const operation = { token, refreshToken, promise: Promise.resolve('') };
      operation.promise = refreshAccessToken(token, refreshToken).finally(() => {
        if (pendingRefresh === operation) pendingRefresh = null;
      });
      pendingRefresh = operation;
    }
    token = await pendingRefresh.promise;
    if (localStorage.getItem(STORAGE_KEYS.TOKEN) !== token) throw new Error('登录状态已变化，请重新发起请求');
  }
  if (token && !credentialRequest) config.headers.set('Authorization', `Bearer ${token}`);
  return config;
});

httpClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const authentication = await getAuthConfig().catch(() => null);
    if (authentication?.mode === 'oidc') {
      if (error.response?.status === 401 && !/\/auth\//.test(error.config?.url || '')) {
        window.location.href = loginPageUrl();
      }
      return Promise.reject(error);
    }
    if (error.response?.status === 401 && error.config && !isCredentialRequest(error.config.url)) {
      const sent = error.config.headers?.get?.('Authorization') ?? error.config.headers?.Authorization;
      const current = localStorage.getItem(STORAGE_KEYS.TOKEN);
      // A delayed response from a signed-out session cannot invalidate a new login.
      if ((current && sent === `Bearer ${current}`) || (!current && !sent)) clearAuthentication();
    }
    return Promise.reject(error);
  },
);

export default httpClient;

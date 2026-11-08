import axios from 'axios';
import { API_BASE_URL } from '../config/api';
import { API_PREFIX } from '../config/constants';

export type AuthMode = 'legacy' | 'oidc';
export interface AuthConfig { mode: AuthMode; login_url: string | null; }
export const CSRF_COOKIE = '__Host-rehab_csrf';
export const CSRF_HEADER = 'X-CSRF-Token';
let configuration: Promise<AuthConfig> | null = null;

export function clearLegacyCredentials(): void {
  for (const key of ['token', 'refresh_token', 'token_expiry', 'user', 'userRole', 'persist:root']) {
    localStorage.removeItem(key);
  }
}

export function loginPageUrl(): string { return `${API_PREFIX}/auth/login`; }

/** OIDC credentials only belong to this origin; a configured remote API cannot receive them. */
export function assertSameOrigin(url: string): URL {
  const parsed = new URL(url, window.location.origin);
  if (parsed.origin !== window.location.origin || parsed.username || parsed.password) {
    throw new Error('统一登录地址必须与当前系统同源');
  }
  return parsed;
}

/** One configuration lookup gates all transports; errors never select a weaker mode. */
export function getAuthConfig(): Promise<AuthConfig> {
  if (!configuration) {
    configuration = axios.get(`${API_BASE_URL}/auth/config`, { timeout: 10000 }).then(({ data }) => {
      if (data?.mode !== 'legacy' && data?.mode !== 'oidc') throw new Error('登录配置响应无效');
      if (data.mode === 'oidc') {
        assertSameOrigin(API_BASE_URL);
        const login = assertSameOrigin(data.login_url);
        if (window.location.protocol !== 'https:' || login.protocol !== 'https:' || !login.pathname.endsWith('/auth/oidc/start')) {
          throw new Error('统一登录需要有效的 HTTPS 登录入口');
        }
        clearLegacyCredentials();
        return { mode: 'oidc' as const, login_url: login.href };
      }
      return { mode: 'legacy' as const, login_url: null };
    }).catch((error) => { configuration = null; throw error; });
  }
  return configuration;
}

export function csrfHeaders(method = 'GET'): Record<string, string> {
  if (['GET', 'HEAD', 'OPTIONS'].includes(method.toUpperCase())) return {};
  const value = document.cookie.split(';').map(part => part.trim()).find(part => part.startsWith(`${CSRF_COOKIE}=`))?.slice(CSRF_COOKIE.length + 1);
  if (!value) throw new Error('登录会话验证信息缺失，请刷新后重试');
  return { [CSRF_HEADER]: decodeURIComponent(value) };
}

export async function authRequestOptions(method = 'GET', url = API_BASE_URL) {
  const config = await getAuthConfig();
  if (config.mode === 'oidc') {
    assertSameOrigin(url);
    return { withCredentials: true, headers: csrfHeaders(method) };
  }
  return {};
}

export async function authenticatedWebSocketUrl(url: string): Promise<string> {
  const config = await getAuthConfig();
  const result = new URL(url.replace(/^http/, 'ws'), window.location.origin.replace(/^http/, 'ws'));
  if (config.mode === 'oidc') {
    if (result.origin !== window.location.origin.replace(/^http/, 'ws') || result.protocol !== 'wss:') {
      throw new Error('统一登录 WebSocket 必须使用同源 WSS');
    }
    result.searchParams.delete('token');
    return result.href;
  }
  const token = localStorage.getItem('token');
  if (!token) throw new Error('请先登录');
  result.searchParams.set('token', token);
  return result.href;
}

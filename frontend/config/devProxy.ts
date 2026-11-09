import type { ProxyOptions } from 'vite';

/** Public deployment path; API and WebSocket routes share this prefix. */
export function deploymentPrefix(value?: string): string {
  const prefix = value?.trim().replace(/\/+$/, '') ?? '';
  if (prefix && (!prefix.startsWith('/') || prefix.startsWith('//') || /[?#\\]/.test(prefix))) {
    throw new Error('VITE_API_PREFIX must be a root-relative deployment path');
  }
  return prefix;
}

/** Match route boundaries and strip only the public prefix, as nginx does. */
export function backendProxy(prefix: string, target: string): Record<string, ProxyOptions> {
  const escaped = prefix.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  return {
    [`^${escaped}/(?:api|ws)(?:/|\\?|$)`]: {
      target,
      changeOrigin: false,
      ws: true,
      rewrite: pathname => prefix ? pathname.slice(prefix.length) : pathname,
    },
  };
}

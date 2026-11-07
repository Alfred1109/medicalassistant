/**
 * VITE_API_URL historically accepted both an origin and an API root. Keep both
 * forms valid, including a deployment prefix, and expose one canonical API root.
 * Resource consumers append paths relative to this root, never another /api.
 */
export function normalizeApiBaseUrl(configured?: string): string {
  const value = configured?.trim() || '/api';
  let origin = '';
  let pathname: string;

  if (/^https?:\/\//i.test(value)) {
    const url = new URL(value);
    if (url.username || url.password || url.search || url.hash) {
      throw new Error('VITE_API_URL must not contain credentials, a query or a fragment');
    }
    origin = url.origin;
    pathname = url.pathname;
  } else {
    if (!value.startsWith('/') || value.startsWith('//') || /[?#\\]/.test(value)) {
      throw new Error('VITE_API_URL must be an http(s) URL or a root-relative path');
    }
    pathname = value;
  }

  const path = pathname.replace(/\/+$/, '');
  return `${origin}${path.endsWith('/api') ? path : `${path}/api`}`;
}

/** Explicit API URL takes priority; otherwise honor the deployment path. */
export function resolveApiBaseUrl(apiUrl?: string, deploymentPrefix?: string): string {
  return normalizeApiBaseUrl(apiUrl?.trim() || deploymentPrefix?.trim() || undefined);
}

import { resolveApiBaseUrl } from './apiBase';

// Canonical API root for Axios, RTK Query and direct HTTP consumers.
export const API_BASE_URL = resolveApiBaseUrl(import.meta.env.VITE_API_URL, import.meta.env.VITE_API_PREFIX);

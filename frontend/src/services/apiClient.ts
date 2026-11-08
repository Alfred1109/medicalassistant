import type { AxiosRequestConfig } from 'axios';
import httpClient from './httpClient';

// These callers expect response data; api.ts callers keep AxiosResponse.
// Preserve this adapter's historical 15s default and per-request overrides.
const configWithTimeout = (config?: AxiosRequestConfig): AxiosRequestConfig => ({ timeout: 15000, ...config });

const apiClient = {
  async get<T>(url: string, config?: AxiosRequestConfig): Promise<T> {
    return (await httpClient.get<T>(url, configWithTimeout(config))).data;
  },
  async post<T>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<T> {
    return (await httpClient.post<T>(url, data, configWithTimeout(config))).data;
  },
  async put<T>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<T> {
    return (await httpClient.put<T>(url, data, configWithTimeout(config))).data;
  },
  async delete<T>(url: string, config?: AxiosRequestConfig): Promise<T> {
    return (await httpClient.delete<T>(url, configWithTimeout(config))).data;
  },
};

export default apiClient;

import { useState, useEffect, useCallback } from 'react';
import { AxiosResponse, AxiosError } from 'axios';

/**
 * 通用API调用Hook，用于管理API调用的加载状态、数据和错误
 * @param apiFunction API调用函数
 * @param immediate 是否在组件挂载时立即执行API调用
 * @param initialArgs 初始参数（可选）
 */
export function useApi<T, P extends any[]>(
  apiFunction: (...args: P) => Promise<AxiosResponse<T>>,
  immediate = false,
  initialArgs?: P
) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState<boolean>(immediate);
  const [error, setError] = useState<Error | null>(null);
  const [lastArgs, setLastArgs] = useState<P | null>(initialArgs || null);

  // 执行API调用的函数
  const execute = useCallback(
    async (...args: P) => {
      setLoading(true);
      setError(null);
      setLastArgs(args);

      try {
        const response = await apiFunction(...args);
        setData(response.data);
        return response.data;
      } catch (err) {
        const axiosError = err as AxiosError;
        const errorMessage = 
          axiosError.response?.data?.message || 
          axiosError.message || 
          '发生未知错误';
        
        const error = new Error(errorMessage);
        setError(error);
        throw error;
      } finally {
        setLoading(false);
      }
    },
    [apiFunction]
  );

  // 当immediate为true且有初始参数时，在组件挂载时执行API调用
  useEffect(() => {
    if (immediate && initialArgs) {
      execute(...initialArgs);
    }
  }, [immediate, execute]); // 依赖initialArgs会导致重复调用，所以排除

  // 重置状态
  const reset = useCallback(() => {
    setData(null);
    setLoading(false);
    setError(null);
    setLastArgs(null);
  }, []);

  return {
    data,
    loading,
    error,
    execute,
    reset,
    lastArgs
  };
}

/**
 * 带有分页功能的API调用Hook
 */
export function usePaginatedApi<T, P extends any[]>(
  apiFunction: (...args: P) => Promise<AxiosResponse<{ items: T[]; total: number; page: number; pageSize: number }>>,
  pageSize = 10,
  initialPage = 1
) {
  const [page, setPage] = useState(initialPage);
  const [total, setTotal] = useState(0);
  const [items, setItems] = useState<T[]>([]);

  // 包装原始API函数以包含分页参数
  const wrappedApiFunction = useCallback(
    (...args: P) => {
      // 假设最后一个参数是params对象，如果不是则创建一个
      const lastArg = args.length > 0 ? args[args.length - 1] : {};
      const hasParams = typeof lastArg === 'object' && lastArg !== null && !Array.isArray(lastArg);
      
      const params = hasParams ? { ...lastArg, page, pageSize } : { page, pageSize };
      
      if (hasParams) {
        args[args.length - 1] = params;
      } else {
        args = [...args, params] as P;
      }
      
      return apiFunction(...args);
    },
    [apiFunction, page, pageSize]
  );

  const api = useApi(wrappedApiFunction);

  // 处理数据
  useEffect(() => {
    if (api.data) {
      setItems(api.data.items);
      setTotal(api.data.total);
    }
  }, [api.data]);

  // 页面变化时重新获取数据
  const onChangePage = useCallback(
    (newPage: number) => {
      setPage(newPage);
      if (api.lastArgs) {
        api.execute(...api.lastArgs);
      }
    },
    [api, setPage]
  );

  return {
    ...api,
    page,
    pageSize,
    total,
    items,
    onChangePage
  };
}

// 带有缓存功能的API调用
const apiCache = new Map<string, { data: any; timestamp: number }>();
const DEFAULT_CACHE_TIME = 5 * 60 * 1000; // 5分钟缓存

export function useCachedApi<T, P extends any[]>(
  apiFunction: (...args: P) => Promise<AxiosResponse<T>>,
  cacheKey: string,
  cacheTime = DEFAULT_CACHE_TIME,
  immediate = false,
  initialArgs?: P
) {
  const [cacheHit, setCacheHit] = useState(false);
  
  // 包装原始API函数以实现缓存
  const wrappedApiFunction = useCallback(
    async (...args: P) => {
      // 检查缓存
      const cacheEntry = apiCache.get(cacheKey);
      const now = Date.now();
      
      if (cacheEntry && now - cacheEntry.timestamp < cacheTime) {
        setCacheHit(true);
        return { data: cacheEntry.data } as AxiosResponse;
      }
      
      // 如果缓存无效或不存在，则调用原始API
      const response = await apiFunction(...args);
      
      // 更新缓存
      apiCache.set(cacheKey, {
        data: response.data,
        timestamp: now
      });
      
      setCacheHit(false);
      return response;
    },
    [apiFunction, cacheKey, cacheTime]
  );
  
  const api = useApi(wrappedApiFunction, immediate, initialArgs);
  
  // 清除特定键的缓存
  const clearCache = useCallback(() => {
    apiCache.delete(cacheKey);
  }, [cacheKey]);
  
  // 强制刷新（忽略缓存）
  const forceRefresh = useCallback(
    async (...args: P) => {
      clearCache();
      return api.execute(...args);
    },
    [api, clearCache]
  );
  
  return {
    ...api,
    cacheHit,
    clearCache,
    forceRefresh
  };
} 
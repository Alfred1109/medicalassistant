import { useCallback, useEffect, useRef, useState } from 'react';
import { apiService } from '../services/api';
import type { FollowUpFilters, FollowUpWorkbenchPage, FollowUpWorkbenchQuery } from '../types/followup';
import { buildFollowUpWorkbenchQuery } from '../utils/followupWorkbench';

type State = FollowUpWorkbenchPage & { key: string; loading: boolean; error: string | null };

export function useFollowUpWorkbench(identity: string, patientId: string, filters: FollowUpFilters,
  page: number, pageSize: number, setPage: (page: number) => void) {
  let query: FollowUpWorkbenchQuery | null = null;
  let validationError: string | null = null;
  try { query = buildFollowUpWorkbenchQuery(patientId, filters, page, pageSize); }
  catch (error) { validationError = error instanceof Error ? error.message : '筛选条件无效'; }
  const queryKey = JSON.stringify(query);
  const key = JSON.stringify([identity, queryKey, validationError]);
  const [refresh, setRefresh] = useState(0);
  const [state, setState] = useState<State>({ key: '', items: [], total: 0, skip: 0, limit: pageSize, loading: false, error: null });
  const generation = useRef(0);

  useEffect(() => {
    const current = ++generation.current;
    const controller = new AbortController();
    const empty = { key, items: [], total: 0, skip: page * pageSize, limit: pageSize };
    if (!identity || validationError || !query) {
      setState({ ...empty, loading: false, error: validationError });
      return () => { generation.current++; controller.abort(); };
    }
    setState({ ...empty, loading: true, error: null });
    const requestQuery: FollowUpWorkbenchQuery = JSON.parse(queryKey);
    void apiService.getFollowUpWorkbench(requestQuery, controller.signal).then(({ data }) => {
      if (controller.signal.aborted || generation.current !== current) return;
      if (!data || !Array.isArray(data.items) || !Number.isSafeInteger(data.total) || data.total < 0
          || data.skip !== requestQuery.skip || data.limit !== requestQuery.limit || data.items.length > data.limit
          || data.total < data.items.length) throw new Error('随访列表返回格式异常，请重试');
      const lastPage = Math.max(0, Math.ceil(data.total / pageSize) - 1);
      if (page > lastPage) { setPage(lastPage); return; }
      setState({ ...data, key, loading: false, error: null });
    }).catch(error => {
      if (controller.signal.aborted || generation.current !== current) return;
      const response = error?.response;
      const detail = response?.data?.detail;
      setState({ ...empty, loading: false, error: typeof detail === 'string' ? detail : error instanceof Error && !response ? error.message : '加载随访记录失败，请重试' });
    });
    return () => { generation.current++; controller.abort(); };
  // queryKey contains the complete normalized filter and paging contract.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [identity, key, queryKey, refresh, page, pageSize, setPage, validationError]);

  const reload = useCallback(() => { setRefresh(value => value + 1); }, []);
  const visible = state.key === key ? state : { key, items: [], total: 0, skip: page * pageSize, limit: pageSize, loading: Boolean(identity && !validationError), error: validationError };
  return { records: visible.items, total: visible.total, loading: visible.loading, error: visible.error, reload };
}

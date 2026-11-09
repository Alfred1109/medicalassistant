import { useCallback, useEffect, useRef, useState } from 'react';
import type { AxiosResponse } from 'axios';
import type { CatalogResult } from '../types/formCatalog';
import { formCatalogError } from '../services/formCatalog';

type Loader<T> = (cursor: string | undefined, signal: AbortSignal) => Promise<AxiosResponse<CatalogResult<T>>>;

/** Cursor pages belong to one selection. Aborted/late responses cannot cross projects. */
export function useFormCatalog<T>(key: string, loader: Loader<T> | null) {
  const [state, setState] = useState<{ key: string; items: T[]; cursor: string | null; more: boolean; loading: boolean; error: string | null }>({ key: '', items: [], cursor: null, more: false, loading: false, error: null });
  const current = useRef(0);
  const request = useRef<AbortController | null>(null);
  const load = useCallback(async (cursor?: string) => {
    if (!loader) return;
    request.current?.abort();
    const controller = new AbortController(); request.current = controller;
    const generation = ++current.current;
    setState(previous => ({ key, items: cursor && previous.key === key ? previous.items : [], cursor: cursor || null, more: false, loading: true, error: null }));
    try {
      const { data } = await loader(cursor, controller.signal);
      if (!Array.isArray(data.data) || !data.page || typeof data.page.has_more !== 'boolean'
          || (data.page.has_more && (typeof data.page.next_cursor !== 'string' || !data.page.next_cursor || data.page.next_cursor === cursor))) throw new Error('Invalid catalog page');
      if (current.current !== generation || controller.signal.aborted) return;
      setState(previous => ({ key, items: cursor && previous.key === key ? [...previous.items, ...data.data] : data.data,
        cursor: data.page.next_cursor, more: data.page.has_more, loading: false, error: null }));
    } catch (error) {
      if (current.current !== generation || controller.signal.aborted) return;
      setState(previous => ({ ...previous, loading: false, error: formCatalogError(error, '来源目录加载失败，请重试。') }));
    }
  }, [key, loader]);
  useEffect(() => {
    if (loader) void load(); else { current.current++; request.current?.abort(); setState({ key, items: [], cursor: null, more: false, loading: false, error: null }); }
    return () => { current.current++; request.current?.abort(); };
  }, [key, loader, load]);
  const visible = state.key === key ? state : { key, items: [], cursor: null, more: false, loading: Boolean(loader), error: null };
  return { items: visible.items, cursor: visible.cursor, more: visible.more, loading: visible.loading, error: visible.error, reload: () => load(), next: () => visible.more && !visible.loading ? load(visible.cursor || undefined) : undefined };
}

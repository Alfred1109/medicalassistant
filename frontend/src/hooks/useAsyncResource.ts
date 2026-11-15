import { useCallback, useEffect, useState } from 'react';

/** Read a resource for the current scope; cancelled or replaced requests cannot publish results. */
export function useAsyncResource<T>(load: (signal: AbortSignal) => Promise<T>, enabled = true) {
  const [revision, setRevision] = useState(0);
  const [state, setState] = useState<{
    load: typeof load; revision: number; data: T | null; error: unknown; loading: boolean;
  }>({ load, revision, data: null, error: null, loading: enabled });

  useEffect(() => {
    const controller = new AbortController();
    setState({ load, revision, data: null, error: null, loading: enabled });
    if (enabled) {
      Promise.resolve().then(() => load(controller.signal)).then(data => {
        if (!controller.signal.aborted) setState({ load, revision, data, error: null, loading: false });
      }, error => {
        if (!controller.signal.aborted) setState({ load, revision, data: null, error, loading: false });
      });
    }
    return () => controller.abort();
  }, [load, revision, enabled]);

  const reload = useCallback(() => setRevision(value => value + 1), []);
  const current = enabled && state.load === load && state.revision === revision;
  return {
    data: current ? state.data : null,
    error: current ? state.error : null,
    loading: enabled && (!current || state.loading),
    reload,
  };
}

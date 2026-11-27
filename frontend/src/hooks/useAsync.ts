import { useCallback, useEffect, useRef, useState, type DependencyList } from 'react';
import { errorMessage } from '../services/http';

export interface AsyncState<T> {
  data: T | null;
  loading: boolean;
  refreshing: boolean;
  error: string | null;
  updated: number | null;
  reload: () => void;
}

interface UseAsyncOptions {
  /** Poll interval in ms. 0/undefined = one-shot fetch. */
  intervalMs?: number;
  /** Skip fetching (e.g. route not active). */
  enabled?: boolean;
}

/**
 * Data-fetching primitive: loading / error / empty + optional polling.
 * Keeps the previous payload visible while refreshing so charts do not flash.
 */
export function useAsync<T>(
  fn: () => Promise<T>,
  deps: DependencyList,
  options: UseAsyncOptions = {},
): AsyncState<T> {
  const { intervalMs = 0, enabled = true } = options;
  const [nonce, setNonce] = useState(0);
  const [state, setState] = useState<{
    data: T | null;
    loading: boolean;
    refreshing: boolean;
    error: string | null;
    updated: number | null;
  }>({ data: null, loading: enabled, refreshing: false, error: null, updated: null });

  const fnRef = useRef(fn);
  fnRef.current = fn;

  useEffect(() => {
    if (!enabled) return undefined;
    let cancelled = false;

    const run = async (initial: boolean) => {
      if (initial) {
        setState((prev) => ({ ...prev, loading: true, error: null }));
      } else {
        setState((prev) => ({ ...prev, refreshing: true }));
      }
      try {
        const data = await fnRef.current();
        if (!cancelled) setState({ data, loading: false, refreshing: false, error: null, updated: Date.now() });
      } catch (error) {
        if (!cancelled) {
          setState((prev) => ({
            data: prev.data,
            loading: false,
            refreshing: false,
            error: errorMessage(error),
            updated: prev.updated,
          }));
        }
      }
    };

    void run(true);
    const timer = intervalMs > 0 ? window.setInterval(() => void run(false), intervalMs) : undefined;

    return () => {
      cancelled = true;
      if (timer) window.clearInterval(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, intervalMs, nonce, ...deps]);

  const reload = useCallback(() => setNonce((value) => value + 1), []);

  return { ...state, reload };
}

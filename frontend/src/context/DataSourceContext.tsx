import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react';
import { env } from '../config/env';
import { createDataSource } from '../services';
import type { DataSource, DataSourceMode } from '../types';

interface DataSourceContextValue {
  mode: DataSourceMode;
  source: DataSource;
  setMode: (mode: DataSourceMode) => void;
  endpoints: { orchestrator: string; edge: string; cloud: string; scheduler: string };
  refreshMs: number;
}

const DataSourceContext = createContext<DataSourceContextValue | null>(null);

export function DataSourceProvider({ children }: { children: ReactNode }) {
  const [mode, setMode] = useState<DataSourceMode>(env.dataMode);

  const source = useMemo(() => createDataSource(mode), [mode]);
  const setModeSafe = useCallback((next: DataSourceMode) => setMode(next), []);

  const value = useMemo<DataSourceContextValue>(
    () => ({
      mode,
      source,
      setMode: setModeSafe,
      endpoints: {
        orchestrator: env.orchestratorUrl,
        edge: env.edgeUrl,
        cloud: env.cloudUrl,
        scheduler: env.schedulerUrl,
      },
      refreshMs: env.refreshMs,
    }),
    [mode, source, setModeSafe],
  );

  return <DataSourceContext.Provider value={value}>{children}</DataSourceContext.Provider>;
}

export function useData(): DataSourceContextValue {
  const context = useContext(DataSourceContext);
  if (!context) throw new Error('useData must be used inside <DataSourceProvider>');
  return context;
}

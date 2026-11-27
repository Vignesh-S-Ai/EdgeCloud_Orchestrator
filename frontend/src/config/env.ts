import type { DataSourceMode } from '../types';

const read = (key: keyof ImportMetaEnv, fallback: string): string => {
  const value = import.meta.env[key];
  return typeof value === 'string' && value.trim().length > 0 ? value.trim() : fallback;
};

const stripSlash = (url: string) => url.replace(/\/+$/, '');

const rawMode = read('VITE_DATA_MODE', 'demo').toLowerCase();
const mode: DataSourceMode = rawMode === 'live' ? 'live' : 'demo';

const refreshRaw = Number(read('VITE_REFRESH_INTERVAL_MS', '5000'));

export const env = {
  dataMode: mode,
  orchestratorUrl: stripSlash(read('VITE_ORCHESTRATOR_URL', 'http://localhost:8003')),
  edgeUrl: stripSlash(read('VITE_EDGE_URL', 'http://localhost:8000')),
  cloudUrl: stripSlash(read('VITE_CLOUD_URL', 'http://localhost:8001')),
  schedulerUrl: stripSlash(read('VITE_SCHEDULER_URL', 'http://localhost:8002')),
  refreshMs: Number.isFinite(refreshRaw) && refreshRaw >= 1000 ? refreshRaw : 5000,
} as const;

/** Endpoints the backend actually exposes (documented in each service's routes.py). */
export const LIVE_ENDPOINTS = [
  'GET  /                 service info (all four services)',
  'GET  /health          liveness + model state',
  'GET  /metrics         CPU / RAM / disk snapshot (edge, cloud)',
  'POST /decision        placement decision (scheduler)',
  'POST /orchestrate     end-to-end placement + inference (orchestrator)',
] as const;

export const NO_ENDPOINT_REASON =
  'No backend endpoint serves this view yet. The FastAPI services expose only ' +
  '/, /health, /metrics (edge + cloud), /decision (scheduler) and /orchestrate. ' +
  'Switch to DEMO DATA to explore the interface, or add a backend endpoint and ' +
  'implement it in src/services/liveDataSource.ts.';

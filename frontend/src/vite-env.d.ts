/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_DATA_MODE?: string;
  readonly VITE_ORCHESTRATOR_URL?: string;
  readonly VITE_EDGE_URL?: string;
  readonly VITE_CLOUD_URL?: string;
  readonly VITE_SCHEDULER_URL?: string;
  readonly VITE_REFRESH_INTERVAL_MS?: string;
  readonly VITE_USE_PROXY?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

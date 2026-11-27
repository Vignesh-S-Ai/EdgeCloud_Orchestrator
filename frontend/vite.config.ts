import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  const orchestrator = env.VITE_ORCHESTRATOR_URL || 'http://localhost:8003';

  return {
    plugins: [react()],
    server: {
      host: true,
      port: 5173,
      // Optional same-origin proxy: set VITE_USE_PROXY=true to route API calls
      // through the dev server (useful when a backend does not send CORS
      // headers). All project FastAPI services currently allow every origin,
      // so the dashboard calls them directly by default.
      proxy:
        env.VITE_USE_PROXY === 'true'
          ? {
              '/api/orchestrator': { target: orchestrator, rewrite: (p) => p.replace(/^\/api\/orchestrator/, '') },
              '/api/edge': { target: env.VITE_EDGE_URL || 'http://localhost:8000', rewrite: (p) => p.replace(/^\/api\/edge/, '') },
              '/api/cloud': { target: env.VITE_CLOUD_URL || 'http://localhost:8001', rewrite: (p) => p.replace(/^\/api\/cloud/, '') },
              '/api/scheduler': { target: env.VITE_SCHEDULER_URL || 'http://localhost:8002', rewrite: (p) => p.replace(/^\/api\/scheduler/, '') },
            }
          : undefined,
    },
    build: {
      outDir: 'dist',
      sourcemap: false,
      chunkSizeWarningLimit: 900,
    },
  };
});

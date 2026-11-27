# CLOUD-13 Dashboard (frontend)

React + TypeScript + Vite + Tailwind CSS + Recharts + Lucide dashboard for the
**Edge-Cloud Orchestration for Low-Latency Workloads** project.

The dashboard is **read-only**: it never changes backend or AWS state, and it
never invents production numbers. Every screen is fed by a single
`DataSource` interface with two implementations:

| Mode | Source | Indicator |
|------|--------|-----------|
| `demo` (default) | `src/services/mock/mockStore.ts` – clearly labelled mock service | amber **DEMO DATA** badge in the top bar, sidebar and footer |
| `live` | `src/services/hybridDataSource.ts` – real FastAPI endpoints, with sample-data fallback for views that have no endpoint | green **LIVE BACKEND** badge + per-view chips |

### How live mode works (hybrid)

`HybridDataSource` calls the real services for everything they can serve and
falls back to the mock service **only** for views with no backend endpoint:

- **Live** (`LIVE DATA` chip, green): `/health`, `/metrics`, `/` service info
  on both nodes, orchestrator/scheduler health, and the real
  `POST /decision` probe. A failed probe is never replaced by mock data.
- **Sample** (`SAMPLE DATA` chip, dashed): routing/inference history,
  utilisation and latency time series, Kubernetes workloads, log stream –
  views the backend does not expose yet.

Every panel that uses sample data in live mode is tagged, so screenshots and
demos never present mock values as production metrics. Per-page chips are
rendered by `src/components/ui/SourceChips.tsx`; the classification lives
next to it (`LIVE_VIEWS`).

In demo mode the per-page chips are hidden (the global **DEMO DATA** badge
already covers the whole dashboard).

## Quick start

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173
```

Production build / local preview:

```bash
npm run build        # type-check (tsc --noEmit) + vite build -> dist/
npm run preview      # serves dist/ on http://localhost:4173
npm run typecheck    # type-check only
```

Node 18+ is required (tested with Node 24 / npm 11).

## Environment variables

Copy `.env.example` to `.env` (or `.env.local`) and adjust. All values have
safe defaults, so the dashboard runs with **no backend at all** in demo mode.

| Variable | Default | Purpose |
|----------|---------|---------|
| `VITE_DATA_MODE` | `demo` | `demo` or `live` initial data source |
| `VITE_ORCHESTRATOR_URL` | `http://localhost:8003` | Orchestrator base URL |
| `VITE_EDGE_URL` | `http://localhost:8000` | Edge node base URL (ServiceBus URL in K3s) |
| `VITE_CLOUD_URL` | `http://localhost:8001` | Cloud node base URL |
| `VITE_SCHEDULER_URL` | `http://localhost:8002` | Scheduler / decision engine base URL |
| `VITE_REFRESH_INTERVAL_MS` | `5000` | Health + metrics polling interval |
| `VITE_USE_PROXY` | `false` | Proxy API calls through the Vite dev server |

All four FastAPI services already run with `allow_origins=["*"]`, so the
browser calls them directly by default. Set `VITE_USE_PROXY=true` if you front
them with something that does not send CORS headers.

## Running against the real backend

From the **repository root**:

```bash
uvicorn edge.api.app:create_app --factory --host 0.0.0.0 --port 8000
uvicorn cloud.api.app:create_app --factory --host 0.0.0.0 --port 8001
uvicorn scheduler.api.app:create_app --factory --host 0.0.0.0 --port 8002
uvicorn orchestrator.api.app:create_app --factory --host 0.0.0.0 --port 8003
```

Then in `frontend/.env`:

```
VITE_DATA_MODE=live
VITE_EDGE_URL=http://localhost:8000
VITE_CLOUD_URL=http://localhost:8001
VITE_SCHEDULER_URL=http://localhost:8002
VITE_ORCHESTRATOR_URL=http://localhost:8003
```

Use the **Demo / Live** switch in the top bar to flip data sources at runtime.

## Backend endpoints actually used

Inspected from the repository source (no endpoints were invented):

| Service | Endpoint | Used for |
|---------|----------|----------|
| orchestrator | `GET /`, `GET /health` | service info, health pill |
| scheduler | `GET /health` | health pill |
| scheduler | `POST /decision` | "Scheduler decision probe" widget (real placement decision) |
| edge | `GET /health`, `GET /metrics`, `GET /` | health, CPU/RAM/disk, uptime/endpoints |
| cloud | `GET /health`, `GET /metrics`, `GET /` | health, CPU/RAM/disk, uptime/endpoints |

Views without a backend endpoint (request/routing history, inference history,
Kubernetes workloads, log stream, historical time series) fall back to the
clearly-labelled mock service in live mode and carry the **SAMPLE DATA** chip.

## Project structure

```
frontend/
├── index.html
├── vite.config.ts            # dev server + optional API proxy
├── tailwind.config.js        # dark infrastructure palette
├── .env.example
├── src/
│   ├── main.tsx              # providers + font/css bootstrap
│   ├── App.tsx               # hash router + routes
│   ├── config/
│   │   ├── env.ts            # env vars, endpoint list, no-endpoint reason
│   │   └── navigation.ts     # sidebar + route metadata
│   ├── context/DataSourceContext.tsx   # mode switch (demo <-> live)
│   ├── hooks/useAsync.ts     # loading / error / empty + polling
│   ├── types/index.ts        # API models (mirror Pydantic) + view-models
│   ├── services/
│   │   ├── http.ts           # fetch wrapper with timeouts
│   │   ├── api.ts            # typed clients for the 4 FastAPI services
│   │   ├── liveDataSource.ts # raw LIVE implementation (real endpoints only)
│   │   ├── hybridDataSource.ts # LIVE + sample-data fallback (what live mode uses)
│   │   ├── index.ts          # DataSource factory
│   │   └── mock/             # DEMO implementation (only place with invented data)
│   ├── components/
│   │   ├── layout/           # Sidebar, TopBar, AppShell
│   │   ├── ui/               # Panel, MetricCard, gauges, badges, states, tables
│   │   └── charts/           # latency, utilisation, donut, decision bars, route flow
│   ├── pages/                # the seven dashboard modules
│   └── lib/format.ts         # ms / % / uptime / time-ago formatting
```

## Dashboard modules

1. **Overview** – edge/cloud health, total requests, edge-vs-cloud split,
   average inference + scheduler latency, latency/utilisation charts, recent
   orchestration activity.
2. **Live Orchestration** – routing history table (filters/search), edge ->
   cloud routing visualisation, decision distribution, `POST /decision` probe.
3. **Edge Node** – CPU/RAM/disk gauges, connectivity (KubeEdge ServiceBus),
   health, inference latency, running workloads.
4. **Cloud Node** – same layout for the cloud node (ClusterIP :8001).
5. **Workloads** – pods, services, cluster nodes, running/pending/failed and
   restart counts.
6. **Inference Monitor** – request history, destination, duration, detection
   output with confidence bars.
7. **Logs & Monitoring** – level/source/time-range filtering over system
   events, scheduler activity, errors and warnings.

All screens include loading, empty and error states.

## Design notes

- Desktop-first, responsive down to tablet (collapsible sidebar).
- Dark infrastructure palette defined once in `tailwind.config.js`
  (`base`, `panel`, `line`, `ink`, `brand`, `ok/warn/bad`).
- Charts: Recharts (latency, utilisation, donut); SVG gauges and plain CSS
  bars where a chart library is overkill.
- Numbers are formatted consistently through `src/lib/format.ts`.

## Extending with a new live endpoint

1. Add the typed call in `src/services/api.ts`.
2. Return real data from `src/services/liveDataSource.ts` (replace the
   `null` for that view).
3. The page already renders `null` as the "no live endpoint" state, so no UI
   change is needed once real data flows.

# Edge-Cloud Orchestration for Low-Latency Workloads

Real-time YOLOv8 object detection workloads routed between edge and cloud based on live resource metrics. Built with Python/FastAPI, Docker, K3s/KubeEdge, and AWS EC2.

## Problem

Single cloud introduces network round-trip delay; single edge saturates under load. This project routes each workload to the location that best meets latency requirements using live CPU/RAM/disk and network metrics.

## Architecture

```
Client
  |
  v
Orchestrator (:30083 NodePort, public HTTP)
  |
  v
Scheduler (/decision)
  |-- fetch edge /metrics via KubeEdge ServiceBus :9443
  |-- fetch cloud /metrics via ClusterIP
  |-- measure cloud /health latency
  |-- RuleBasedPolicy -> EDGE | CLOUD | QUEUE | ERROR
  |
  v
Edge (/detect via ServiceBus)  OR  Cloud (/infer via ClusterIP)
  YOLOv8n (Ultralytics, ~6 MB)    YOLOv8n
  -> DetectionResult (byte-identical schema)
```

**Infrastructure**
- Cloud EC2: K3s control-plane + CloudCore (v1.23.1)
- Edge EC2 (dedicated): EdgeCore + edge-node pod (hostPort 8000)
- KubeEdge ServiceBus: `rest-source` (`/edge-ec2-node/edgecloud`) -> `servicebus-target` (`:8000`) via Rules `detect-route`, `health-route`, `metrics-route`, `video-route`

## Repository Structure

```
edge/                 # Edge YOLOv8 service (FastAPI, OpenCV, psutil)
cloud/                # Cloud YOLOv8 service (parity with edge)
scheduler/            # Placement decision engine
orchestrator/         # Single entry point, routes to selected node
infra/terraform/      # AWS VPC, EC2, ECR, security groups, RDS, IAM
infra/k3s/            # K8s namespace, deployments, services, KubeEdge Rules
infra/rebuild/        # 8-stage rebuild pipeline (00-collect … 08-validate)
docs/                 # Architecture, integration, validation, benchmark, rebuild guides
frontend/             # React dashboard (Vite + Tailwind + Recharts)
diagrams/             # SystemArchitecture, Deployment, Scheduler, Workflow
```

All internal imports are `edge.*` relative style. Run commands from repo root.

## Quick Start (Local)

```bash
python -m venv .venv
pip install -r edge/requirements.txt
pip install -r cloud/requirements.txt
pip install -r scheduler/requirements.txt
pip install -r orchestrator/requirements.txt
pip install pytest "httpx<0.28"  # dev extras (fastapi 0.109 compat)

# Edge (YOLOv8n auto-downloads ~6 MB on first /detect if missing)
uvicorn edge.api.app:create_app --factory --host 0.0.0.0 --port 8000

# Tests (fake detector, no camera/GPU/model needed)
pytest edge/tests -v
pytest cloud/tests -v
pytest scheduler/tests -v
pytest orchestrator/tests -v
```

Configuration via `EDGE_*` env vars or root `.env` (see `edge/.env.example`, `cloud/.env.example`):
- `EDGE_CAMERA_SOURCE` (0, RTSP URL, or file), `EDGE_CAMERA_OPEN_TIMEOUT_SEC=5`
- `EDGE_MODEL_PATH=yolov8n.pt`, `EDGE_MODEL_CONFIDENCE=0.5`

Docker (from repo root):
```bash
docker build -f edge/Dockerfile -t edge-node:0.1.0 .
docker build -f cloud/Dockerfile -t cloud-node:0.1.0 .
docker build -f scheduler/Dockerfile -t scheduler:0.1.0 .
docker build -f orchestrator/Dockerfile -t orchestrator:0.1.0 .
```

## Deployment (Safe)

Terraform from `infra/terraform` (see `docs/REBUILD_QUICKSTART.md` and `infra/rebuild/README.md`):
- Region `ap-south-1`, VPC `10.0.0.0/16`
- ECR login via `aws ecr get-login-password | docker login`
- K3s + KubeEdge install via `infra/rebuild/scripts/04-install-k3s.sh` and `05-install-kubeedge.sh`
- Deploy manifests: `kubectl apply -f infra/k3s/namespace.yaml` then deployments/services and `edgecloud-kubeedge-*.yaml`

Orchestrator edge URL: `http://10.0.1.113:9443/edge-ec2-node/edgecloud` (CloudCore REST :9443 -> ServiceBus). Scheduler metrics timeout `2.0s`, policy thresholds edge `70/70/85`, cloud `80/80/90`, max latency `200ms`.

## Dashboard (frontend/)

React + TypeScript + Vite + Tailwind + Recharts + Lucide dashboard with 7
modules: Overview, Live Orchestration, Edge Node, Cloud Node, Workloads,
Inference Monitor, Logs & Monitoring. Read-only — it never mutates backend or
AWS state.

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173
npm run build      # tsc --noEmit + vite build -> dist/
npm run preview    # serve dist/ on :4173
```

Two data modes, switched from the top bar:

- **demo** (default) — data from `src/services/mock/mockStore.ts`, flagged with
  a visible **DEMO DATA** badge in the top bar/sidebar/footer.
- **live** (hybrid) — calls the real endpoints (`edge :8000`, `cloud :8001`,
  `scheduler :8002`, `orchestrator :8003`); all four already allow CORS.
  Views with a backing endpoint (`/health`, `/metrics`, `/`, `POST /decision`)
  show real data behind a green **LIVE DATA** chip; views the backend does not
  serve yet (history, logs, workloads, time series) fall back to the mock
  service behind a dashed **SAMPLE DATA** chip, so mock values are never
  presented as live.

Config via `frontend/.env` (`VITE_DATA_MODE`, `VITE_EDGE_URL`,
`VITE_CLOUD_URL`, `VITE_SCHEDULER_URL`, `VITE_ORCHESTRATOR_URL`,
`VITE_REFRESH_INTERVAL_MS`, `VITE_USE_PROXY`). Full docs: `frontend/README.md`.

## Testing

- `edge/tests`: 15 cases (health, metrics, detect, video frame_step)
- `cloud/tests`: API + detector parity
- `scheduler/tests`: 5 suites (API, models, policies, decision engine, metrics client)
- `orchestrator/tests`: routing and error handling
- Production validation: 684+ requests, 100% success, 432 requests over 15 min, zero restarts (see `docs/PHASE8_END_TO_END_VALIDATION_REPORT.md`, `docs/PHASE9_PRODUCTION_HARDENING_REPORT.md`)

## Benchmarks

Scheduler `/decision` (no inference, `docs/phase10/10E/p10_10e_bench.py`):

| Concurrency | Baseline 10E-2 | Optimized 10E-6 | Improvement |
|-------------|----------------|-----------------|-------------|
| C1 | 2100.9 ms | 66.0 ms (with cache) | -96.9% |
| Live uncached | 2016.9 ms | 1107.7 ms | -46.7% |

`66 ms` is scheduler decision with cache hit, **not** AI inference. Full `/orchestrate` (scheduler + inference) C1 mean `415.6 ms` (scheduler ~275 ms + YOLO ~117 ms). Edge inference ~114-232 ms, cloud ~193 ms. See `docs/FINAL_BENCHMARK_RESULTS.md`.

## Limitations

- PostgreSQL RDS provisioned but no application code connects to it
- React dashboard is read-only (no Prometheus/Grafana yet)
- No TLS on orchestrator public API or CloudCore REST
- No automatic edge->cloud failover (cloud->edge fallback only for high priority when cloud fails)
- Physical camera not demonstrated (file/RTSP/webcam index supported)
- WSL2 legacy node remains `NotReady` and cordoned

## Reproducibility

- `infra/rebuild/rebuild.env.example` + `infra/rebuild/README.md` for new AWS account
- `docs/REBUILD_VERSION_MATRIX.md` for pinned versions (K3s v1.32.x, KubeEdge v1.23.1)
- `docs/CURRENT_WORKING_STATE_SNAPSHOT.md` for last known production topology
- `docs/REPOSITORY_REPRODUCIBILITY_AUDIT.md` for what is/isn't reproducible

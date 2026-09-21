# Edge Node

Part of the **Edge-Cloud Orchestration for Low-Latency Workloads** capstone.

The Edge Node is the workload host that sits next to the video source. It
captures frames, runs local **YOLOv8** inference, exposes a **FastAPI**
surface, reports system **metrics**, and makes a first **edge-vs-cloud**
scheduling decision. It is fully **Dockerized** and ready to be wrapped by
**K3s / KubeEdge**.

## Architecture

```
                 +---------------------- EDGE NODE -----------------------+
  camera / rtsp  |  edge/ai (capture + YOLO)                              |
  ------------>  |        |                                              |
                 |        v                                              |
                 |  edge/api (FastAPI)  <----- external world (cloud,    |
  curl / app     |  edge/monitoring     <----- dashboard, KubeEdge)      |
  ------------>  |  edge/scheduler      <----- only entry point          |
                 +-------------------------------------------------------+
```

**Layering rule (important):** the AI layer never talks to the cloud. All
external communication flows through the API layer only. The scheduler
consumes metrics from the monitoring layer and returns a decision; the cloud
integration (Module 2) will call the API, not the internals.

## Folder structure

```
edge/
├── ai/
│   ├── __init__.py
│   ├── camera.py      # CameraCapture: webcam / RTSP / video file, threaded + reconnecting
│   ├── detector.py    # YOLODetector: YOLOv8n load, predict, annotate, JPEG encoder
│   └── models.py      # Pydantic data models: BBox, Detection, DetectionResult
├── api/
│   ├── __init__.py
│   ├── app.py         # create_app() factory: lifespan, wiring, middleware, router
│   └── routes.py      # GET /, /health, /metrics, POST /detect, /detect/video
├── monitoring/
│   ├── __init__.py
│   └── metrics.py     # MetricsCollector + SystemMetrics (CPU, RAM, disk, timestamp)
├── scheduler/
│   ├── __init__.py
│   └── local_scheduler.py  # LocalScheduler: edge-vs-cloud decision engine
├── tests/
│   ├── test_api.py         # API tests with fakes (no camera/model needed)
│   └── test_scheduler.py   # Decision-engine unit tests
├── config.py         # Settings via pydantic-settings, EDGE_* env vars
├── requirements.txt
├── Dockerfile        # production build (CPU torch, non-root, healthcheck)
├── .env.example      # configuration template
└── README.md
```

## Responsibilities of every file

| File | Responsibility |
| --- | --- |
| `config.py` | Single source of truth for configuration. Reads `EDGE_*` env vars / `.env`, auto-detects the camera source type, parses class filters, exposes a cached `get_settings()`. |
| `ai/camera.py` | Opens webcam (index), RTSP stream or file via OpenCV. Webcam/RTSP run a background capture thread with a 2-frame buffer so inference never blocks capture; RTSP reconnects automatically. |
| `ai/detector.py` | Lazy-loads the Ultralytics YOLO model (downloads `yolov8n.pt` on first use). `predict()` is thread-safe, returns typed `DetectionResult`; helpers draw boxes and encode annotated frames to base64 JPEG. |
| `ai/models.py` | Pure data models decoupled from the ML stack (no torch/ultralytics imports), used by the API responses. |
| `api/app.py` | Application factory. Wires camera/detector/metrics/scheduler into `app.state`, sets up logging, CORS, lifespan cleanup, includes routes. |
| `api/routes.py` | The only public surface. `/` service info + scheduling decision, `/health` readiness probe, `/metrics` resource snapshot, `/detect` image inference, `/detect/video` streaming batch inference. |
| `monitoring/metrics.py` | Collects CPU %, RAM %/GB, disk %/GB and a UTC timestamp using psutil. Feeds `/metrics` and the scheduler. |
| `scheduler/local_scheduler.py` | Decision engine (Module 3 groundwork). Combines CPU, RAM and load into a composite score; high priority biases towards local, exhausted nodes offload to cloud. Stable `decide()` interface for later KubeEdge replacement. |
| `tests/*` | Unit tests that fake the detector so CI needs no camera or GPU. |
| `Dockerfile` | Multi-purpose production image: python:3.11-slim, CPU-only torch, non-root user, healthcheck. |
| `requirements.txt` | Pinned, compatible dependency set. |

## How to run (bare metal)

```bash
# 1. (recommended) create a venv
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Linux / macOS

# 2. install (see note about torch below)
pip install -r edge/requirements.txt

# 3. optional: copy the config template
cp edge/.env.example edge/.env    # Windows: copy edge\.env.example edge\.env

# 4. start the server from the REPOSITORY ROOT
uvicorn edge.api.app:create_app --factory --host 0.0.0.0 --port 8000
```

> The first start downloads `yolov8n.pt` (~6 MB) from the Ultralytics repo.

**Torch note:** on Windows/macOS the PyPI torch wheel is CPU-only and works
as-is. On Linux for CPU-only use
`pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu`
(the Dockerfile already does this).

### Camera sources

| Source | `EDGE_CAMERA_SOURCE` |
| --- | --- |
| Webcam index 0 | `0` |
| RTSP camera | `rtsp://user:pass@192.168.1.50:554/stream` |
| Video file | `C:\videos\sample.mp4` |

## How to test

```bash
pip install pytest httpx
pytest edge/tests -v
```

Tests fake the detector and use a dummy camera device, so they run anywhere:
health probe, metrics shape, valid/invalid `/detect` payloads, video upload
validation, and scheduler decisions (idle/loaded/priority/disabled).

### Manual smoke test

```bash
# health
curl http://localhost:8000/health

# metrics
curl http://localhost:8000/metrics

# detect - base64 JPEG body
$b64 = [Convert]::ToBase64String([IO.File]::ReadAllBytes("frame.jpg"))
$body = @{ image_base64 = $b64; annotated = $true } | ConvertTo-Json
curl -X POST http://localhost:8000/detect -H "Content-Type: application/json" -d $body

# detect - video upload
curl -X POST http://localhost:8000/detect/video -F "file=@clip.mp4" -F "frame_step=5"

# interactive docs
open http://localhost:8000/docs
```

## How to Dockerize

```bash
# build from the REPOSITORY ROOT (build context must contain edge/)
docker build -f edge/Dockerfile -t edge-node:0.1.0 .

# run (webcam needs /dev/video0; use RTSP/file for container demos)
docker run --rm -p 8000:8000 \
    -e EDGE_CAMERA_SOURCE="rtsp://user:pass@host:554/stream" \
    -e EDGE_MODEL_CONFIDENCE=0.6 \
    edge-node:0.1.0

# run with a local video file mounted in
docker run --rm -p 8000:8000 \
    -v "$PWD:/media" \
    -e EDGE_CAMERA_SOURCE="/media/clip.mp4" \
    edge-node:0.1.0

# healthcheck is built in; verify
docker inspect --format='{{json .State.Health}}' <container>
```

`docker-compose.yml` will be added in Module 2 to pair the node with the cloud
API and PostgreSQL.

## Configuration reference

All variables are optional; defaults are shown in `edge/.env.example`.

| Env var | Default | Purpose |
| --- | --- | --- |
| `EDGE_SERVICE_NAME` | `edge-node` | Service name reported by `/` |
| `EDGE_PORT` | `8000` | HTTP port |
| `EDGE_LOG_LEVEL` | `INFO` | Logging verbosity |
| `EDGE_CAMERA_SOURCE` | `0` | Webcam index / RTSP URL / file path |
| `EDGE_CAMERA_TYPE` | auto | Force `webcam`/`rtsp`/`file` |
| `EDGE_CAMERA_WIDTH` / `_HEIGHT` / `_FPS` | 640 / 480 / 30 | Capture resolution |
| `EDGE_MODEL_PATH` | `yolov8n.pt` | Weights file (auto-downloaded) |
| `EDGE_MODEL_CONFIDENCE` | `0.5` | Detection confidence threshold |
| `EDGE_MODEL_DEVICE` | `cpu` | `cpu` or `cuda` |
| `EDGE_MODEL_CLASSES` | empty | COCO class filter, e.g. `0,2,5` |
| `EDGE_SCHEDULER_*` | enabled, 80/80, medium | Decision engine thresholds/priority |
| `EDGE_MAX_UPLOAD_BYTES` | 200 MB | Video upload cap |

## Future: KubeEdge integration

The node is already packaged as an image with a healthcheck, so it becomes a
KubeEdge workload as-is:

1. Install KubeEdge `EdgeCore` on this node (see `cloud/` and `docs/` for the
   cloud side) and `CloudCore` on the master.
2. Build and push the image: `docker push <registry>/edge-node:0.1.0`.
3. Deploy with a `Deployment`/`DaemonSet` + `EdgeApplication` manifest; KubeEdge
   injects node name, cluster DNS and secrets via `DownwardAPI`/env.
4. Use the `startupProbe`/`readinessProbe` pointing at `/health` so EdgeCore
   only routes traffic to a model-ready node.
5. Replace `LocalScheduler` with a KubeEdge plugin / or let the cloud decision
   engine (Module 3) override `run_locally` by pushing labels, e.g.
   `edge.orchestrator/offload=true` to the node, which the scheduler reads from
   `/metrics` responses.

No code changes are required: the API contract (`/health`, `/metrics`,
`/detect`) is the interface KubeEdge and the cloud communicate with.

## Future: AWS integration

1. Push the same image to ECR:
   `aws ecr create-repository --repository-name edge-node` then `docker push`.
2. Edge nodes = EC2 instances (t3.micro/t3.medium, GPU later via `g4dn`) with
   K3s installed; the deployment manifest points at the ECR image.
3. EKS + CloudCore runs the cloud stack (FastAPI + PostgreSQL) — the node's
   `/metrics` and `/detect` become the cloud's data source.
4. Network: the node pushes results and metrics to the cloud API; optionally
   the cloud pulls with an agent. Route 53 / ALB in front of the cloud API.
5. The `EDGE_*` env vars become ECS/K8s `env`/ConfigMap entries, so one image
   works for a fleet of differently-configured nodes.

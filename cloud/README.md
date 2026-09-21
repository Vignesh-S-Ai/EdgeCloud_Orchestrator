# Cloud Node

Part of the **Edge-Cloud Orchestration for Low-Latency Workloads** capstone.

The Cloud Node is the remote inference service (AWS EC2 Free Tier target). It
receives base64-encoded images from Edge Nodes, runs **YOLOv8n** inference,
returns detection results, and reports system **metrics**. It establishes the
working flow:

```
EDGE -> CLOUD -> INFERENCE -> RESULT -> EDGE
```

The Edge and Cloud are **separate, decoupled services**. The Cloud Node is
self-contained (its own config, models, API, monitoring and tests) and never
imports anything from `edge/`. They only talk over HTTP using the shared
`image_base64` payload format.

## Architecture

```
                     +---------------------- CLOUD NODE ----------------------+
  edge / curl        |  cloud/ai (YOLOv8n inference)                          |
  image_base64 --->  |        |                                              |
                     |        v                                              |
                     |  cloud/api (FastAPI)  <----- only entry point         |
  edge / curl        |  cloud/monitoring     <----- resource metrics         |
  <-------------     +-------------------------------------------------------+
```

**Layering rule (important):** the AI layer never talks to the outside world.
All communication flows through the API layer only.

## Folder structure

```
cloud/
├── ai/
│   ├── __init__.py
│   ├── detector.py    # YOLODetector: YOLOv8n load, predict, annotate, JPEG encoder
│   └── models.py      # Pydantic models: BBox, Detection, DetectionResult
├── api/
│   ├── __init__.py
│   ├── app.py         # create_app() factory: lifespan, wiring, middleware, router
│   └── routes.py      # GET /, /health, /metrics, POST /infer
├── monitoring/
│   ├── __init__.py
│   └── metrics.py     # MetricsCollector + SystemMetrics (CPU, RAM, disk, timestamp)
├── tests/
│   ├── test_api.py         # API tests with a faked detector (no GPU/model)
│   └── test_detector.py    # Detector unit tests with a faked ultralytics module
├── config.py         # Settings via pydantic-settings, CLOUD_* env vars
├── requirements.txt
├── Dockerfile        # production build (CPU torch, headless OpenCV, non-root, healthcheck)
├── .env.example      # configuration template
└── README.md
```

## Responsibilities of every file

| File | Responsibility |
| --- | --- |
| `config.py` | Single source of truth for configuration. Reads `CLOUD_*` env vars / `.env`, parses class filters, exposes a cached `get_settings()`. |
| `ai/detector.py` | Lazy-loads the Ultralytics YOLO model (downloads `yolov8n.pt` on first use). `predict()` is thread-safe, returns typed `DetectionResult`; helpers draw boxes and encode annotated frames to base64 JPEG. Same interface as the Edge detector for benchmarking. |
| `ai/models.py` | Pure data models decoupled from the ML stack, schema-compatible with `edge.ai.models`. |
| `api/app.py` | Application factory. Wires detector/metrics into `app.state`, sets up logging, CORS, lifespan, includes routes. |
| `api/routes.py` | The only public surface. `/` service info, `/health` readiness probe, `/metrics` resource snapshot, `/infer` image inference. |
| `monitoring/metrics.py` | Collects CPU %, RAM %/GB, disk %/GB and a UTC timestamp using psutil. Format-compatible with the Edge Node. |
| `tests/*` | Unit tests that fake the detector and the `ultralytics` module, so CI needs no GPU, camera, or internet. |
| `Dockerfile` | Production image: python:3.11-slim, CPU-only torch, headless OpenCV, non-root user, healthcheck. |
| `requirements.txt` | Compatible dependency set (mirrors the Edge node minus camera/upload extras). |

## How to run (bare metal)

```bash
# 1. (recommended) create a venv
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Linux / macOS

# 2. install (see torch note below)
pip install -r cloud/requirements.txt

# 3. optional: copy the config template
cp cloud/.env.example cloud/.env    # Windows: copy cloud\.env.example cloud\.env

# 4. start the server from the REPOSITORY ROOT
uvicorn cloud.api.app:create_app --factory --host 0.0.0.0 --port 8001
```

> The first start downloads `yolov8n.pt` (~6 MB) from the Ultralytics repo.

**Torch note:** on Windows/macOS the PyPI torch wheel is CPU-only and works
as-is. On Linux for CPU-only use
`pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu`
(the Dockerfile already does this).

## How to test

```bash
pip install pytest httpx
pytest cloud/tests -v
```

Tests fake the detector and the `ultralytics` module, so they run anywhere
without a GPU, camera, model download, or internet.

### Manual smoke test

```bash
# health
curl http://localhost:8001/health

# metrics
curl http://localhost:8001/metrics

# infer - base64 JPEG body (same format as the Edge /detect endpoint)
$b64 = [Convert]::ToBase64String([IO.File]::ReadAllBytes("sampleimage.jpg"))
$body = @{ image_base64 = $b64; annotated = $true } | ConvertTo-Json
curl -X POST http://localhost:8001/infer -H "Content-Type: application/json" -d $body

# interactive docs
open http://localhost:8001/docs
```

## How to Dockerize

```bash
# build from the REPOSITORY ROOT (build context must contain cloud/)
docker build -f cloud/Dockerfile -t cloud-node:0.1.0 .

# run
docker run --rm -p 8001:8001 cloud-node:0.1.0

# healthcheck is built in; verify
docker inspect --format='{{json .State.Health}}' <container>
```

## Configuration reference

All variables are optional; defaults are shown in `cloud/.env.example`.

| Env var | Default | Purpose |
| --- | --- | --- |
| `CLOUD_SERVICE_NAME` | `cloud-node` | Service name reported by `/` |
| `CLOUD_PORT` | `8001` | HTTP port |
| `CLOUD_LOG_LEVEL` | `INFO` | Logging verbosity |
| `CLOUD_MODEL_PATH` | `yolov8n.pt` | Weights file (auto-downloaded) |
| `CLOUD_MODEL_CONFIDENCE` | `0.5` | Detection confidence threshold |
| `CLOUD_MODEL_DEVICE` | `cpu` | `cpu` or `cuda` |
| `CLOUD_MODEL_CLASSES` | empty | COCO class filter, e.g. `0,2,5` |
| `CLOUD_MAX_INFER_BYTES` | 10 MB | Max base64 image payload |

## Future

- Module 3: the orchestration layer that decides whether an inference runs on
  the Edge or is offloaded to this Cloud Node (`POST /infer` is the offload
  target). The `/metrics` endpoint is the data source for that decision.
- AWS EC2 deployment: see the Module 2 report in the project docs for exact
  Free Tier instructions.

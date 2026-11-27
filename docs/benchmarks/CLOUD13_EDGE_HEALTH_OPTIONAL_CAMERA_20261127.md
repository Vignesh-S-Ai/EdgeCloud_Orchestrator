# CLOUD-13 Edge Inference Readiness and Optional Camera Health

Date: 27 November 2026

## Change rationale

The Edge service's primary inference contract accepts uploaded images through `POST /detect`. A physical camera is optional. Previously, `GET /health` returned `degraded` whenever the optional local camera could not open, even when the YOLO model was loaded and image inference was available. The AWS Edge EC2 node has no directly attached webcam, so the old health status conflated camera availability with inference readiness.

## Updated health semantics

- `status=ok` when the inference model is loaded.
- `status=degraded` when the inference model is not loaded.
- `camera_open` remains in the response for backward compatibility.
- New `camera_status` field reports `connected` or `not_connected` independently.

This does not claim that a camera is connected. It makes the health signal reflect the service's core inference readiness.

## Files changed

- `edge/api/routes.py`
- `edge/tests/test_api.py`
- `frontend/src/types/index.ts`
- `frontend/src/pages/NodePage.tsx`
- `infra/k3s/edge-node-deployment.yaml` (image reference only; this manifest was not applied)

## Validation

- Edge API tests: 22 passed.
- Full repository test suite: 144 passed.
- Frontend TypeScript/Vite production build: passed.
- Live post-deployment health via KubeEdge:
  `{"status":"ok","model_loaded":true,"camera_open":false,"camera_status":"not_connected"}`
- Live end-to-end inference through the deployed orchestrator:
  HTTP 200; selected target Edge; actual target Edge; no fallback; 3 detections.
- All four deployments (Cloud, Edge, Orchestrator, Scheduler): 1/1 Ready; zero restarts observed.

## Deployment

Image tag: `health-camera-optional-20261127`

Image digest: `sha256:f978821342b9911d37558c2dcc6d1ff60a0684cc06c9d5fa9fa397005ee0afa6`

Base image digest: `sha256:fb6165722e861d1782957c46502109bf9d3c98461b51761fa3550fa19b4244cf`

Deployment was performed with `kubectl set image` on the existing Edge Deployment. The manifest was not applied, avoiding its pre-existing nodeSelector mismatch with the live cluster.

## Scope boundary

This change does not connect the laptop webcam to the Edge EC2 node. The Edge camera is still `not_connected`. Browser webcam capture and secure frame forwarding to the orchestrator/Edge inference API remain a separate frontend demonstration capability. No public ports were opened, and no Scheduler, Orchestrator, Cloud node or KubeEdge routing configuration was changed.

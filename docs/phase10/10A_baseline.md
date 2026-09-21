# Phase 10 — Gate 10A Baseline (captured, no production changes)

**Date:** 2026-09-02
**Phase 9 status:** COMPLETE / PASS (see `docs/PHASE9_PRODUCTION_HARDENING_REPORT.md`)
**Method:** read-only probes from orchestrator pod + cluster inspection. NO production changes applied during 10A.

## K8s / Cluster

- Nodes: `edge-ec2-node` (Ready, 10.0.1.123) + `ip-10-0-1-113` (Ready, control-plane). No WSL2 node.
- edgecloud pods: cloud-node, edge-node, orchestrator, scheduler — all `1/1 Running`, **RESTARTS 0**.
- Deployments: cloud-node/orchestrator/scheduler 14d, edge-node 12d (all 1/1).
- Services: cloud-node ClusterIP 10.43.45.189:8001; edge-node ClusterIP 10.43.218.215:8000; orchestrator NodePort 10.43.112.251:8003→30083; scheduler ClusterIP 10.43.201.181:8002.
- Rules: `detect-route`, `health-route`, `metrics-route`, `video-route`.
- RuleEndpoints: `rest-source`, `servicebus-target`.

## Application

- edge `/health` via ServiceBus → 200 `{"status":"degraded","model_loaded":true,"camera_open":false}`
- edge `/metrics` via ServiceBus → 200 `cpu 2.9% / ram 25.8% / disk 18.9%`
- **Live orchestrate (edge)** → 200, `selected/actual=edge`, reason capacity, decision 84.14; detection `cup` 1, 625×400.
  - **total 2189.1 ms | scheduler 2068.5 ms | inference 120.5 ms | model inference 94.34 ms**
  - scheduler = ~94% of total → the 10E optimization target.
- **Snapshot orchestrate (edge, CPU 12%)** → 200 `actual=edge`, 230.7 ms, score 69.86.
- **Snapshot orchestrate (cloud, overloaded edge CPU95/RAM90)** → 200 `actual=cloud`, 186.9 ms, score 15.58.
- Response schema / invariants: detection present, annotated_image_base64 present, full key-set (worker as Phase 9).

## Security (from orchestrator pod)

- `edge:8000` → **BLOCKED/TimeoutError**
- `edge:9443` → **BLOCKED/TimeoutError**
- `cloudcore:9443` (10.0.1.113) → **OPEN (plaintext HTTP)** — this is the 10C TLS target; reachable only on internal VPC (SG does not expose 9443 publicly).

## Video frame_step behavior (OLD buggy deployment — baseline)

Using 6-frame `tiny.mp4` via ServiceBus `POST /detect/video`:

| frame_step | status | total_frames | frames_processed | detections |
|---|---|---|---|---|
| 1 | 200 | 6 | **0** (BUG) | `{}` |
| 3 | 200 | 6 | 2 | `{}` |
| 5 | 200 | 6 | 2 | `{}` |
| 0 | **500** (edge 422 via CloudCore→500) | — | — | — |
| -1 | **500** (edge 422 via CloudCore→500) | — | — | — |
| 100 | 200 | 6 | 1 | `{}` |

- Confirms the **livestate `frame_step=1` → 0 frames** defect (10B target). step=3/5 match Phase 9 (2 frames on 6-frame video).
- `tiny.mp4` has no detectable object → detections `{}` even for valid steps; the 10B verification of *detections produced* will use the object-bearing video from 9F (`cup` source) or a step with a detectable frame.

**Command IDs (10A):** cluster `990f8c49`; app+perf+security `062f6faf`; video baseline `734c0de4`.

## Gate 10A verdict

**PASS (baseline recorded).** No production changes. Ready for 10B.

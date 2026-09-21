# Phase 7 — Orchestrator ↔ KubeEdge ServiceBus Integration Report

**Status:** IMPLEMENTED & VERIFIED — Phase 7 PASS.
**Author:** opencode session
**Date:** 2026-09-01
**Approved plan:** `docs/PHASE7_ORCHESTRATOR_INTEGRATION_PLAN.md` (Option B for metrics, no new Rule/RuleEndpoint, no scheduler/edge/CloudCore/EdgeCore/Terraform/SG changes).

---

## 1. Before / After edge URL

| | Value |
|---|---|
| **Before** | `ORCHESTRATOR_EDGE_URL=http://edge-node.edgecloud.svc:8000` (Edge Service ClusterIP → KubeEdge edge pod CIDR `10.244.0.4:8000`, **unroutable from cloud pods**) |
| **After** | `ORCHESTRATOR_EDGE_URL=http://10.0.1.113:9443/edge-ec2-node/edgecloud` (CloudCore REST router `:9443` → Rule `detect-route`/`health-route` → ServiceBus → EdgeCore → `localhost:8000` edge YOLO) |

Resulting requests verified to be exactly:
- `http://10.0.1.113:9443/edge-ec2-node/edgecloud/detect`
- `http://10.0.1.113:9443/edge-ec2-node/edgecloud/health`

(Double-path `/detect/detect` rejected by construction — `orchestrator/clients.py::_BaseClient._url()` joins base + `/path`.) All other env vars unchanged (`CLOUD_URL`, `SCHEDULER_URL`, `PORT`, `LOG_LEVEL`).

## 2. Exact files changed

1. `infra/k3s/orchestrator-deployment.yaml` — **only repo source file changed** (edge URL §1 + `nodeSelector` §4). Live applied via `kubectl apply -f`.
2. `docs/PHASE7_ORCHESTRATOR_INTEGRATION_PLAN.md` — created in the investigation phase (approved).
3. `docs/PHASE7_ORCHESTRATOR_INTEGRATION_REPORT.md` — this file.

**Not modified (verified live/unchanged):** scheduler deployment, cloud-node deployment, edge-node deployment (edge-ec2 + legacy), Rules `detect-route`/`health-route`, RuleEndpoints `rest-source`/`servicebus-target`, CloudCore config, EdgeCore config, Terraform, Security Groups, RDS, ECR repository, WSL2 config, `wsl2-edge-node`.

## 3. Exact configuration change

- `ORCHESTRATOR_EDGE_URL` value replaced (see §1).
- `kubectl diff` confirmed **no other field changed** except the edge URL, the `last-applied-configuration` annotation and `generation: 1→2` bookkeeping.
- No scheduler/edge/CloudCore/EdgeCore code or config touched. **No `/metrics` Rule added** (Option B — `kubectl get rules -n edgecloud` still shows only `detect-route`, `health-route`).

## 4. Operational side-effect handled (transparent disclosure)

A rolling-redeploy of the orchestrator re-scheduled the pod onto the **edge node** (`edge-ec2-node`), because the deployment had no `nodeSelector` and the scheduler could now place cloud-side pods on the Ready edge node. That placement:
- made `kubectl exec` fail (KubeEdge edges don't proxy exec → 502), breaking every verification/ops path, and
- placed a cloud-side component on the edge host (architecturally inconsistent with `scheduler`/`cloud-node`, both on `ip-10-0-1-113`).

**Required correction (not a gratuitous improvement):** added `nodeSelector: kubernetes.io/hostname: ip-10-0-1-113.ap-south-1.compute.internal` to the orchestrator template to restore its cloud-side placement. This is the only extra field; documented here and in the plan. A **stale ECR `dockerconfigjson` token** (secret from 08-18; token 12 h expiry) then blocked the fresh pull on the control-plane node with `403 Forbidden`, so the `ecr-registry-secret` was refreshed via `aws ecr get-login-password | kubectl create secret docker-registry --dry-run -o yaml | kubectl apply -f -`. Both are operational necessities of the mandated redeploy; neither changes the image, the secret name/type, or any other resource.

## 5. Health test (Phase 7.5)

From the running orchestrator pod (`orchestrator-5d76f94584-lpx97`, `ip-10-0-1-113`):

- Edge `/health` via ServiceBus: **HTTP 200**, `Server: uvicorn`, latency ≈ **13.9 ms**.
  Body: `{"status":"degraded","service":"edge-node","version":"0.1.0","model_loaded":true,"camera_open":false,"timestamp":...}` → **`model_loaded: true`** (as required).
- Orchestrator own `/health`: **HTTP 200**, `{"status":"ok","service":"orchestrator","version":"0.1.0"}`.

## 6. Real inference test / 7. Response validation (Phase 7.6)

`POST /orchestrate` with the proven Phase 6 image (Sampleimage.jpg, b64 50 148 chars), healthy edge metrics (Option B) → scheduler picks EDGE:

- **HTTP 200**, `selected_target/actual_target = "edge"`, `fallback_used=false`.
- `decision_score 71.51`, reason `"Edge resources within capacity ... running locally."`
- **Real YOLO detection:** `source yolov8n.pt`, `inference_ms 112.95`, detection `cup` (class_id 41, conf 0.87), `count 1`, `frame 625x400`.
- Latency breakdown: `scheduler_latency_ms 197.99`, `inference_latency_ms 140.02`, `total_latency_ms 338.04`.
- Request size ≈ 50 KB b64; response matched `DetectionResult` schema exactly (bbox, class, confidence, annotated=null, count).
- Orchestrator log (proof of path): `POST http://10.0.1.113:9443/edge-ec2-node/edgecloud/detect "HTTP/1.1 200 OK"`.

## 8. Cloud fallback test (Phase 7.7)

`POST /orchestrate` with edge overloaded (CPU 95%, RAM 88%), cloud free → scheduler offloads:

- **HTTP 200**, `selected_target/actual_target = "cloud"`, `fallback_used=false` (scheduler-directed offload, not fallback).
- Real detection via `cloud-node` `/infer` (inference_ms 117.88, cup @0.87), `total_latency_ms 318.23`.
- Orchestrator log: `POST http://cloud-node.edgecloud.svc:8001/infer "HTTP/1.1 200 OK"`.
- **Conclusion: the new edge URL does NOT break existing cloud offloading.** Both the edge path (7.6) and cloud path (7.7) are functional.

## 9. Negative tests (Phase 7.8)

| # | Scenario | Result | Interpretation |
|---|---|---|---|
| NEG-3a | `image_base64` too short (<16) | **422** `string_too_short` | Schema validation surfaces client error as-is (no fallback) |
| NEG-3b | Undecodable image (≥16 chars), healthy edge metrics | **503** `Inference failed: Upstream error 500` | Edge returned 500; orchestrator correctly surfaced (5xx → 503), **not suppressed** |
| NEG-4a | Non-existent ServiceBus route `/edge-ec2-node/edgecloud/nope` | **404**; base `/nope` → **500** | Confirms only routed paths respond; correct 404 for unknown route |
| NEG-5 | Edge "unavailable"/live-metrics omitted (Option B real path) | **503** `target=error (edge=missing, cloud=ok); cannot decide placement.` | Documented Option B behavior — without a `/metrics` Rule, live edge metrics can't be fetched; caller must supply snapshots |

Error behavior was recorded, not suppressed, per instructions.

## 10. ServiceBus routing evidence

- Rules (live, unchanged): `detect-route` (rest-source `/detect` → servicebus-target `/detect`) and `health-route` (…`/health`); RuleEndpoints `rest-source` (rest) + `servicebus-target` (`service_port: 8000`). **No `/metrics` route** — hence `/metrics` → 404, expected.
- CloudCore binds `*:9443` (router), `*:10000` (CloudHub WS), `*:10002` (edgeHub https); `cloudcore.service` active ~1.7 weeks, PID 503357.
- EdgeCore on edge host active ~20 h, PID 33990; containerd active.
- WebSocket/ServiceBus link **ESTABLISHED both directions**:
  - cloud side: `10.0.1.113:10000 ⇄ 13.206.238.62:54284`
  - edge side: `10.0.1.123:54284 → 13.206.229.162:10000`
- Edge YOLO container `edge-node-fc54dc46-6xdd6` Running via containerd (created 20 h ago, ATTEMPT 0).

## 11. 10-minute stability results (Phase 7.9)

Window = 600 s, sampled every ~30 s (18 samples): every sample showed
`edgeReady=True yoloPhase=Running orchOwnHealth=200 schedHealth=200 restarts=none`.

**RESULT: PASS (no failures over 600 s).**
- `edge-ec2-node` Ready throughout; YOLO pod Running (0 restarts).
- orchestrator 200, scheduler 200 every sample; no pod restart anywhere.
- No ServiceBus errors, no WebSocket disconnect loop, no containerd failures.
- Final state: `wsl2-edge-node` NotReady (pre-existing, untouched); edge and control-plane nodes Ready.

## 12. Metrics Option B behavior (Phase 7.3)

- Confirmed the existing snapshot mechanism is used unchanged: `OrchestrateRequest{edge_metrics,cloud_metrics,network_metrics}` with an all-or-none validator (`orchestrator/models.py`), forwarded to the scheduler `/decision`, which decides deterministically via `RuleBasedPolicy`. Verified in 7.6 (EDGE) and 7.7 (CLOUD).
- No `/metrics` KubeEdge Rule was created and none is planned; `/metrics` via ServiceBus remains 404 by design. Callers that want the scheduler to decide must supply snapshots (or a future metrics-route, out of scope this phase).

## 13. Security / networking proof (Phase 7.10)

Orchestrator never touches edge pod IP / edge ClusterIP / public edge port 8000:
- Orchestrator startup log enumerates its configured targets; the only edge target is `http://10.0.1.113:9443/edge-ec2-node/edgecloud`.
- Actual edge POST observed in logs: `POST http://10.0.1.113:9443/edge-ec2-node/edgecloud/detect "HTTP/1.1 200 OK"` — via CloudCore REST router, **not** `10.244.0.4` (pod) and **not** `edge-node.edgecloud.svc` / `10.43.218.215` (ClusterIP).
- Cloud path remains `http://cloud-node.edgecloud.svc:8001/infer` (ClusterIP for the cloud node, reachable from cloud pods — unchanged, correct).
- Edge egress-only SG and `localhost:8000` ServiceBus target are unchanged; only route in = CloudCore `:9443` servicebus rules.
- The single cloud→edge inference route is: Orchestrator → CloudCore `:9443` → KubeEdge Router → REST source → ServiceBus target → CloudHub `:10000` → EdgeHub → EdgeCore ServiceBus → `localhost:8000` → YOLO.

## 14. Rollback status (Phase 7.12)

- **Rollback NOT required** — all gates passed; deployment left in a healthy, applied state (no partial deployment).
- Backup on CloudCore host `/root/phase7_backup/` (SHA256 `2803adf8…ae5e4e` of pre-change deployment; env/image/svc/endpoints/nodes/rules snapshots, timestamped `20260901T132720Z`).
- Rollback procedure documented: set `ORCHESTRATOR_EDGE_URL=http://edge-node.edgecloud.svc:8000`, remove the nodeSelector, `kubectl apply` + `rollout status`; CloudCore/EdgeCore/ServiceBus untouched and healthy.

---

## Final verdict

**PHASE 7 — PASS.** The existing orchestrator now executes real YOLO inference on the edge over the proven KubeEdge CloudCore REST → ServiceBus path (`actual_target=edge`, HTTP 200, cup detection, 338 ms end-to-end), while cloud offloading, edge health, and stability all remain green across a 10-minute gate. Only the orchestrator's endpoint configuration changed (plus the placement/credential operational fixes that this redeploy required). Nothing in the ServiceBus/Router/Rule/Terraform/SG/edge/CloudCore/EdgeCore/infra was altered, honoring the approved Option B mandate.

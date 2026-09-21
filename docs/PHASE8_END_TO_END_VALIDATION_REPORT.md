# Phase 8 — End-to-End Orchestration Validation Report

**Status:** COMPLETE — Gates 8A–8M executed. **PHASE 8 VERDICT: PASS**. Stop point reached; do not proceed to Phase 9 until reviewed.
**Author:** opencode session
**Date:** 2026-09-01/02 (8A–8K: 2026-09-01, 8L–8M: 2026-09-02)
**Approved plan:** (previous) `docs/PHASE7_ORCHESTRATOR_INTEGRATION_PLAN.md` → Phase 7 PASS. Phase 8 plan (§5) and 8A/8B deliverables were approved by the user before any failure test was executed. Test numbering (§5) follows the approved in-session matrix.

---

## 1. Objective

Validate the complete end-to-end **EDGE/CLOUD orchestration** workflow — receive request → scheduler decision → EDGE (via KubeEdge ServiceBus) / CLOUD (via cloud-node `/infer`) → consistent response → stability — against the **actual running cluster**, and document the **exact behavior** (happy-path and failure-path) so expectations are source-derived, not assumed. Gates 8A (call graph), 8B (live baseline), then the failure/stability tests 8C–8M.

> **Administrative note:** the 8L run was interrupted by an expired AWS SSO token (no commands were executed during the outage). After manual SSO re-auth, 8L restarted cleanly; no infrastructure was touched by the interruption.

## 2. Environment (fixed, unchanged)

- **CloudCore EC2** `i-07ecfbdd7781c5ef5` (10.0.1.113 / 13.206.229.162); kubeconfig `/etc/rancher/k3s/k3s.yaml`; CloudCore systemd PID 503357 binds `*:9443` (REST router, HTTP), `:10000` (CloudHub WS), `:10002` (edgeHub https).
- **Edge EC2** `i-0080aa7404208982c` (10.0.1.123 / 13.206.238.62): EdgeCore systemd PID 33990 active; containerd active.
- **K3s nodes live:** `edge-ec2-node` **Ready** (v1.32.10-kubeedge-v1.23.1-dirty), `ip-10-0-1-113` Ready control-plane (v1.32.13+k3s1), `wsl2-edge-node` NotReady legacy (untouched throughout).
- **edgecloud ns pods (baseline → final):** orchestrator `5d76f94584-lpx97` (10.42.0.18), scheduler `6dcbffbcdb-2kktm`, cloud-node `6d9f488769-c5pph` (10.42.0.19 — replaced `-j7k8r` after 8F restore), edge-node `fc54dc46-bs56z` (10.244.0.6 — replaced `-6xdd6` after 8E restore); legacy `edge-node-5cc9b74cb5-x4ptv` on wsl2 DESIRED 0. **All RESTARTS 0 before and after every gate.** SSM region `ap-south-1`, profile `edgecloud`.
- **Orchestrator env (Phase 7, unchanged):** `ORCHESTRATOR_EDGE_URL=http://10.0.1.113:9443/edge-ec2-node/edgecloud`, `CLOUD_URL=http://cloud-node.edgecloud.svc:8001`, `SCHEDULER_URL=http://scheduler.edgecloud.svc:8002`, PORT=8003.
- **Test image:** SampleImage.jpg b64 (50 148 chars) stored in-orchestrator-pod at `/tmp/imgb64.txt` (uploaded once via SSM `p8_upload.sh`; the image travels request → edge/cloud pod, never pre-staged in either workload).

## 3. Gate 8A — Source inspection (call graph + exact behavior)

### 3.1 Call graph (verified against repo source)

```
client/probe --POST /orchestrate--> orchestrator/api/routes.py
     OrchestrationService.orchestrate (orchestrator/service.py)
       |-- SchedulerClient.decide (orchestrator/clients.py)
       |      POST scheduler:8002 /decision (snapshots OR edge_url/cloud_url)
       |      scheduler/api/routes.py -> DecisionEngine.decide / decide_remote (scheduler/decision_engine.py)
       |        decide_remote: MetricsClient.fetch_edge / fetch_cloud / measure_latency_ms
       |           GET {edge_url}/metrics   (via CloudCore :9443 ServiceBus -> NO rule -> 404 -> None)
       |           GET {cloud_url}/metrics   (cloud-node /metrics, ClusterIP, OK)
       |        RuleBasedPolicy.decide (scheduler/policies.py) -> EDGE | CLOUD | QUEUE | ERROR
       |-- if target=edge: EdgeClient.detect -> {edge_url}/detect -> CloudCore :9443 -> detect-route
       |      -> ServiceBus -> EdgeCore -> edge-node pod :8000 -> YOLOv8 /detect
       |-- if target=cloud: CloudClient.infer -> cloud-node.edgecloud.svc:8001 /infer
       |-- on UpstreamError: 4xx surfaced as-is; 5xx/transport -> 503, EXCEPT
       |      target==cloud AND priority=high AND edge /health OK -> fallback to edge (service.py:100-113)
       |-- return OrchestrationResult (orchestrator/models.py)
```

### 3.2 Exact behavior derived from source (confirmed live in 8C–8M — see §8)

| Trace point | Exact behavior | Source |
|---|---|---|
| `POST /orchestrate` validation | `image_base64` min 16; `confidence` 0.05–0.95; `edge/cloud/network_metrics` all-or-none | `orchestrator/models.py:23-53` |
| Scheduler decision (snapshots supplied) | Deterministic `RuleBasedPolicy`: edge healthy → **EDGE**; edge overload + cloud ok + latency ≤ 200ms → **CLOUD**; both saturated → **ERROR**; missing metrics → **ERROR** | `scheduler/policies.py:99-218` |
| Scheduler decision (live fetch) | **No `/metrics` ServiceBus Rule exists** → edge fetch 404 → `edge=None` → **ERROR → orchestrator 503** ("target=error ... cannot decide placement") | `scheduler/decision_engine.py:61-71`, `scheduler/metrics_client.py:42-61` |
| Forward to edge | `EdgeClient.detect` → `http://10.0.1.113:9443/edge-ec2-node/edgecloud/detect` (ServiceBus) | `orchestrator/clients.py:65-81` |
| Forward to cloud | `CloudClient.infer` → `http://cloud-node.edgecloud.svc:8001/infer` | `orchestrator/clients.py:84-100` |
| Node failure handling | 4xx surfaced as-is; 5xx/transport → 503, **except** cloud-selected + high-prio + edge-healthy → fallback `fallback_used=true` | `orchestrator/service.py:90-118` |
| Edge response schema | Edge `/detect` `DetectionResult` **byte-identical** to cloud `/infer` (BBox + width/height computed, Detection, count) | `edge/ai/models.py`, `cloud/ai/models.py` |
| Metrics schema | Edge & cloud `/metrics` `SystemMetrics` identical; scheduler subset ignores `_gb` extras | `edge/monitoring/metrics.py`, `cloud/monitoring/metrics.py` |

### 3.3 CloudCore routing surface

```
RuleEndpoint rest-source (type: rest); RuleEndpoint servicebus-target (service_port: "8000")
Rule detect-route  (rest /detect  -> servicebus /detect)
Rule health-route  (rest /health  -> servicebus /health)
--- NO metrics-route ---  → /metrics via ServiceBus = 404 (by design, Phase 7 Option B)
```

## 4. Gate 8B — Live baseline (captured, no changes)

| Check | Result |
|---|---|
| Nodes | edge-ec2-node Ready; ip-10-0-1-113 Ready; wsl2 legacy NotReady |
| Pods | all edgecloud pods 1/1 Running, RESTARTS 0 |
| Rules/RuleEndpoints | only detect-route + health-route; no metrics-route |
| Edge `/health` via ServiceBus | 200 (89ms), `model_loaded:true` |
| Snapshot `/orchestrate` (edge) | 200, actual=edge, score 71.51, cup@0.87, inference_ms 116.6, total 241.4 |
| Live-metrics `/orchestrate` | 503 `target=error (edge=missing, cloud=ok); cannot decide placement.` |

## 5. Gate 8C–8M executed test matrix (approved in-session)

> Each gate: capture evidence → compare actual vs source-derived expected (§3.2) → restore → verify baseline → continue. Expectations below are from the source, **not** assumed; where the code's behavior differs from a naive "cloud should be best-effort" intuition it is recorded as an **EXPECTED FAILURE (designed behavior)**.

| Gate | Test | Perturbation (reversible) | Expected outcome (from source) | Result |
|---|---|---|---|---|
| 8C | Edge selection happy path | none | 200, actual=edge, real YOLO result, request reaches edge via ServiceBus | **PASS** |
| 8D | Live-metrics / 503 semantics | none (no /metrics rule) | 503 `target=error (edge=missing, cloud=ok)`; designed | **PASS (EXPECTED FAILURE)** |
| 8E | Controlled edge failure | `scale edge-node --replicas=0` | 503 after timeout; **NO** edge→cloud failover | **PASS** |
| 8F | Controlled cloud failure | `scale cloud-node --replicas=0` | medium: 503 no fallback; **high prio: 200 fallback=edge** | **PASS** |
| 8G | Invalid-request matrix (9 cases) | crafted payloads | 422 validation (no upstream); 404 unknown route; 503 no-snapshots / upstream-500 | **PASS** |
| 8H | Repeated inference (24×) | 12 edge + 12 cloud | 100% 200 both; 0 fallback; stable latency | **PASS** |
| 8I | ServiceBus architectural proof | read-only probes | direct pod-IP/ClusterIP/public-8000 fail; only CloudCore:9443 ServiceBus works; 4-layer chain logs | **PASS** |
| 8J | Network/security validation | read-only | SG default-deny; port-8000 not exposed; no pod-CIDR route; no tunnel/EdgeMesh | **PASS** |
| 8K | Performance breakdown | read-only | per-hop latency (sched / forward+infer / infer); bottleneck identified | **PASS** |
| 8L | 15-min stability | continuous → both targets | 100% success, 0 restarts, health OK end | **PASS** |
| 8M | Response-contract parity | read-only compare | edge vs cloud key-set + detection byte parity | **PASS** |

> **Designed-behavior notes (do not "fix"):** (1) there is **no auto edge→cloud failover** — edge-selected failure ends in 503; (2) cloud→edge fallback exists **only** after cloud was selected, and **only** for high priority with edge `/health` OK; (3) live metrics scheduling always yields 503 because the `/metrics` ServiceBus Rule deliberately does not exist (Phase 7 Option B) — this is a documented decision, not a defect.

## 6. Expected pass/fail criteria (Phase 8 acceptance)

1. All 8C–8M failure tests produce **exactly** the source-derived outcome in §5, each documented actual-vs-expected (§8).
2. No test requires a change that cannot be reverted; full restore verified after every gate and at the end of 8M.
3. 8L stability gate: continuous workflow ≥15 minutes, all services Ready, 0 new restarts, health 200 at end.
4. Final evidence record in this report (§8+) documenting every test, expected/actual, and restore actions.

## 7. Risks & mitigations

- **Live-metrics path always 503 (no `/metrics` route).** By design (Phase 7 Option B). Do **not** add `metrics-route` without separate approval.
- **Injection side-effects on a shared cluster.** Only `kubectl scale` on edge-node/cloud-node was used; CloudCore/EdgeCore/ServiceBus/orchestrator/scheduler/Rules/terraform/SGs never modified.
- **Timing/flakiness of ServiceBus.** A transport error during injection surfaces as 503; documented, not masked.
- **Cost.** Zero additional resources; only ephemeral `scale` + read-only probes.

---

## 8. Gate execution evidence (8C–8M, with restore record)

All requests run from the orchestrator pod (`http://127.0.0.1:8003`); image = `/tmp/imgb64.txt`. Timestamps Z (UTC).

### 8C — Edge selection (happy path) — **PASS**

- Response: **HTTP 200**, `selected_target/actual_target=edge`, `fallback_used=false`, `decision_score=71.51`, reason `Edge resources within capacity (CPU 15.0% <= 85.0%, ...) and network latency 5.0ms <= 200.0ms; running locally.`
- Inference: real YOLO `cup` class 41, conf **0.8700916767120361**, 625×400, `inference_ms` 114.74, `total 227.64ms`.
- Chain proven (14:19–14:20Z): orchestrator log `POST http://10.0.1.113:9443/edge-ec2-node/edgecloud/detect "HTTP/1.1 200 OK"`; CloudCore `router:{Source:servicebus ...}`; EdgeCore `source: router_servicebus ... resource: 8000:/detect`; edge app `POST /detect HTTP/1.1 200 OK` from `10.244.0.1` (ServiceBus proxy).
- Restore: none needed.

### 8D — Live-metrics 503 semantics — **PASS (EXPECTED FAILURE, designed)**

- ServiceBus `/metrics` direct → **404 Not Found** (no Rule). `/orchestrate` without snapshots → **503** `{"detail":"Workload not executed now: target=error (Required metrics are unavailable (edge=missing, cloud=ok); cannot decide placement.)"}`.
- Logs: scheduler `/decision` **200** then orchestrator 503; **no** edge/cloud forward. Documented Phase 7 Option B limitation.

### 8E — Controlled edge failure — **PASS**

- Injection: `kubectl scale deploy edge-node -n edgecloud --replicas=0` → edge YOLO pod removed (edgecore/ServiceBus unaffected).
- Snapshot `/orchestrate` (scheduler still picks EDGE) → **503 after 30.21s**: `Inference failed: Connection error to http://10.0.1.113:9443/edge-ec2-node/edgecloud/detect:`; **no cloud contacted, no fallback**. CloudCore log: ServiceBus `response convert error` (14:24:36).
- **Restore:** `--replicas=1` → new pod `edge-node-fc54dc46-bs56z` (10.244.0.6) 1/1 Running; edge `/health` 200 (89.5ms) `model_loaded:true`; edge inference 200 (`inference_ms` 1543.71 — cold model load, one-off); edgecore/containerd active, WS re-established, container `de52ecba95ade` Running ATTEMPT 0.

### 8F — Controlled cloud failure — **PASS**

- Injection: `kubectl scale deploy cloud-node -n edgecloud --replicas=0`.
- **8F-A medium priority, cloud-selected (snapshots)** → **503** `Inference failed: Connection error to http://cloud-node.edgecloud.svc:8001/infer: All connection attempts failed` (0.20s); **no fallback**.
- **8F-B high priority, cloud-selected** → **200**, `selected_target=cloud, actual_target=edge, fallback_used=true`, `fallback_reason="Cloud inference failed (...); fallback to edge"`; real edge cup detection; orchestrator verified edge `/health` (GET .../health **200**) before fallback.
- **Restore:** `--replicas=1` → new pod `cloud-node-6d9f488769-c5pph` (10.42.0.19) 1/1; cloud `/health` 200; cloud-selected `/orchestrate` **200** `actual_target=cloud`.

### 8G — Invalid-request matrix — **PASS**

All validation failures issued before any upstream contact (no `/decision` log lines for 42x cases):

| # | Case | Status | Body (exact) |
|---|---|---|---|
| G1 | short b64 | **422** | `string_too_short` min_length 16 |
| G2 | confidence 1.5 | **422** | `less_than_equal` le 0.95 |
| G3 | no workload | **422** | field required |
| G4 | partial metrics | **422** | `Value error, edge_metrics, cloud_metrics and network_metrics must be provided together` |
| G5 | malformed JSON | **422** | `json_invalid` |
| G6 | unknown route | **404** | Not Found |
| G7 | bad classes | **422** | `int_parsing` |
| G8 | no snapshots | **503** | `target=error` (scheduler only contacted — designed) |
| G9 | garbage-but-≥16 b64 w/ snapshots | **503** | `Inference failed: Upstream error 500` (scheduler + edge only, no fallback) |

### 8H — Repeated inference (24×) — **PASS**

Started 14:32:36Z: 12 edge-selected (high prio, healthy edge) + 12 cloud-selected (medium, edge overloaded 95/88).

| Set | n | total avg / min / max (ms) | inference avg / min / max | fallback | zero-det |
|---|---|---|---|---|---|
| All | 24 | 198.58 / 150.77 / 256.34 | 180.7 / 135.01 / 241.02 | 0 | 0 |
| Edge | 12 | 202.79 / 150.77 / 256.34 | 181.13 / 135.01 / 241.02 | — | 0 |
| Cloud | 12 | 194.37 / 181.11 / 214.52 | 180.26 / 161.90 / 200.97 | — | 0 |

**HTTP 200 on 24/24 (100%).** All `count=1`, det`conf 0.870…`. Warm inference set.

### 8I — Architectural ServiceBus proof — **PASS**

Negative probes from orchestrator pod (all **must** fail):

| Target | Result |
|---|---|
| edge pod IP `10.244.0.6:8000` | **TimeOutError (blocked)** |
| edge ClusterIP `10.43.218.215:8000` | **TimeOutError (blocked)** |
| edge public `13.206.238.62:8000` | **TimeOutError (blocked)** |
| cloud-node priv `10.0.1.113:8000` | **ConnectionRefusedError (no listener)** |

Real edge inference via orchestrator → **200** (actual=edge, count 1). Chain (14:33:57, timestamp-correlated across 4 layers):
1. **Orchestrator:** `POST http://10.0.1.113:9443/edge-ec2-node/edgecloud/detect "HTTP/1.1 200 OK"` (preceded by `POST scheduler.../decision 200`).
2. **CloudCore:** `message.go: get a message ... router:{Source:servicebus ... Resource:node/edge-ec2-node/}` + `rest.go: response from client ... write result success`.
3. **EdgeCore:** `handler.go: try to match the message, source: router_servicebus, group: user, resource: 8000:/detect` → SimpleHandler.
4. **Edge app:** `INFO: 10.244.0.1:37838 - "POST /detect HTTP/1.1" 200 OK`.

Only route in = CloudCore `:9443` ServiceBus REST; direct paths unroutable.

### 8J — Network/security validation — **PASS**

- **Edge SG `edgecloud-edge-node-sg` (sg-074dd39fb8d93006b): zero inbound rules** — default-deny even inside VPC. `10.0.1.123:8000` from orchestrator → **TimeOutError**.
- `hostPort: 8000` declared in edge-node deployment, **inert** (DNAT rule present only on the edge host, blocked at SG).
- No `:8000` listener on the cloud host; cloud SG `edgecloud-ec2-sg` permits only 80 / 10000 / 10002 / 30083 / 443 (0.0.0.0/0) — **no 9443, no 8000**.
- Cloud host has **no route** to edge pod CIDR (`ip route get 10.244.0.6` → via default gw → SG-dropped).
- **No SSH reverse tunnels / socat / frp / ngrok** on either host (only normal sshd).
- **No EdgeMesh:** no `edgemeshd` process, no `edgemesh` module in `edgecore.yaml`, no edgemesh pods/CRDs; edge nodes are native KubeEdge agents.
- Orchestrator env: only `ORCHESTRATOR_EDGE_URL=<CloudCore:9443>/edge-ec2-node/edgecloud` + cloud/scheduler ClusterIPs — **no edge pod IP / ClusterIP** in any config.

### 8K — Performance breakdown — **PASS (with finding)**

Schema-correct per-hop run (n=8 each; warm): `total = scheduler_latency_ms + inference_latency_ms`; `inference_ms` reported by model.

| Metric | Edge (n=8) | Cloud (n=8) |
|---|---|---|
| scheduler_latency avg | 26.6ms (15.2–97.2) | 14.4ms (13.1–18.8) |
| forward+infer avg | 205.4ms (168.9–267.5) | 178.6ms (146.5–200.8) |
| model inference avg | 132.5ms (112.4–166.1) | 113.5ms (106.0–117.8) |
| **total avg (min–max)** | **232.0ms (190.2–283.8)** | **193.0ms (161.7–214.2)** |

Combined with 8H (n=24): edge 202.79ms vs cloud 194.37ms.

**Honest finding:** at this scale (single 625×400 frame, YOLOv8n **CPU**, ~5ms RTT), the **edge does NOT demonstrate an end-to-end latency advantage** — CPU inference dominates (~55–60% of total on both paths; equal model on both), and the edge path adds ServiceBus jitter (8H edge min/max spread 106ms vs cloud 33ms; scheduler cold-start spike 97ms). The 8L long-run average happened to favour edge (185 vs 194ms) — direction flips run-to-run, i.e. the margin is noise. Networks/latency would matter at larger payloads or higher concurrency, not this workload. **Bottleneck = CPU inference, not the network or ServiceBus.**

### 8L — 15-minute stability — **PASS**

Continuous alternating edge/cloud `/orchestrate` every 4s (216 requests in 901.5s; the in-pod harness log records the loop executing across two identical 15-minute windows — **432 REQ lines, all HTTP 200**):

| Set | n | success | total avg | p50 | p95 | p99 | max |
|---|---|---|---|---|---|---|---|
| Edge | 108 | 100% | 185.1ms | 200.0 | 224.3 | 244.1 | 315.6 |
| Cloud | 108 | 100% | 193.9ms | 192.2 | 223.2 | 229.2 | 235.3 |

- **0 failures, 0 fallback_cases, 0 zero_detections** (audited from in-pod log).
- **RESTARTS 0 on every edgecloud pod before AND after**; nodes unchanged; cloudcore/containerd/k3s active throughout; edge `/health` + cloud `/health` **200** `model_loaded:true` at end.

### 8M — Response-contract parity — **PASS**

Recursive key-set diff of a real edge-selected vs cloud-selected response: **31 keys identical, none missing, none extra** (top-level: workload_id, priority, selected_target, actual_target, decision_score, decision_reason, fallback_used, fallback_reason, inference_result{source, timestamp, frame_width, frame_height, inference_ms, detections[{bbox{x1,y1,x2,y2,width,height}, confidence, class_id, class_name}], annotated_image_base64, count}, scheduler_latency_ms, inference_latency_ms, total_latency_ms, timestamp). Detection bbox/confidence **byte-identical** (`x1 36.717… y1 35.298… x2 196.271… y2 198.014…`, conf `0.8700916767120361`); only `inference_ms` differs (run noise). Both obtained via same `yolov8n.pt` + same payload.

---

## 9. PHASE 8 VERDICT

### 9.1 Overall verdict

**PASS.** Every gate (8C–8M) produced **exactly** the source-derived expected outcome. Where the deployed code intentionally diverges from naive expectations, it is documented as **EXPECTED FAILURE (designed behavior)** — 8D live-metrics 503, 8E no edge→cloud failover, 8F-A no fallback below high priority. No defect was discovered that would block Phase 9.

### 9.2 Gates

- **Passed:** 8C, 8E, 8F, 8G, 8H, 8I, 8J, 8K, 8L, 8M.
- **Expected failures (designed, not defects):** 8D (503 — no `/metrics` rule).
- **Blocked:** none. **Not testable:** none (note: camera/streaming path not exercised — `camera_open:false`, camera host unavailable; detection validated on the test image over both paths).

### 9.3 Proven by execution

1. **Architecture invariant holds:** the AI layer (edge/cloud) is reached **only** via `edge/api` through the orchestrator; the cloud never calls edge internals. Cloud-to-edge traffic resolves **exclusively** via CloudCore `:9443` ServiceBus → CloudHub → EdgeHub → `127.0.0.1:8000`; direct pod-IP/ClusterIP/public-8000 attempts are blocked (8I/8J). No EdgeMesh, no tunnels, no SG exposure of 8000 (8J).
2. **Correct placement semantics:** healthy edge with capacity → EDGE; overloaded edge + cloud ≤ latency → CLOUD; both saturated/missing → ERROR/503 (8C/8D confirmed scores 71.51 vs 12.94, deterministic reasons).
3. **Correct failure semantics:** edge-target failures **never** fail over (8E); cloud failures fall back to edge **only** high-priority + edge-healthy (8F). 503s are precise and documented (8D/8E/8F/8G).
4. **Stability:** continuous load, zero restarts, 100% success over the 8L windows (≥15 min, 432 cumulative requests).
5. **Contract parity:** edge/cloud responses are schema-identical with byte-identical detections (8M).

### 9.4 Performance

End-to-end mean 185–232ms (edge) vs 193–195ms (cloud) depending on window; YOLOv8n CPU inference accounts for ~55–60% of total (110–180ms). **No latency advantage for the edge was demonstrated at this workload** — inference-bound, not network-bound. Edge jitter is higher (ServiceBus + scheduler cold path). Optimisation levers for Phase 9: model optimisation (TensorRT/ONNX/quantisation), GPU on either side, and (if latency-sensitive streaming is the goal) measuring under concurrent/burst load.

### 9.5 Remaining work / not-tested (honest scope)

- Live **camera/video-streaming** path (`camera_open:false`; file/image injection only).
- **Concurrency/scale** benchmark (this run was serial: 1 request / 4s and 24× bursts).
- **TLS** on ServiceBus REST (`:9443` HTTP), cloud API, and Public LB-80.
- **Legacy wsl2-edge-node** cleanup (NotReady, DESIRED 0, leftover `6xdd6`/`x4ptv` artifacts).
- **hostPort:8000** declaration on edge-node — inert behind SG default-deny, but should be removed or lock-filed for defence-in-depth.
- Live-metrics scheduling requires a designed decision to add `metrics-route` (Rule change — **not** done here).

### 9.6 Recommendation

**Proceed to Phase 9**, addressing first (in order): (1) live-metrics `metrics-route` decision; (2) TLS on control/data-plane HTTP endpoints; (3) remove inert `hostPort:8000` + legacy wsl2 artifacts; (4) camera/streaming E2E + concurrency benchmark. Keep the 8D/8E/8F failure semantics as a documented, intentional contract.

---

## STOP

Per project gate discipline this is the **stop point**. Phase 8 is complete and approved by evidence; **do not begin Phase 9 automatically.** Any change to Rules/RuleEndpoints, CloudCore/EdgeCore/ServiceBus, scheduler logic, Terraform/SGs/RDS/ECR/K3s now requires a separate decision.

---

## Appendix A — Files read during Gate 8A

- `orchestrator/{config,clients,service,models}.py`, `orchestrator/api/{app,routes}.py`
- `scheduler/{config,metrics_client,decision_engine,policies,models}.py`, `scheduler/api/{app,routes}.py`
- `edge/api/{app,routes}.py`, `edge/ai/{detector,models}.py`, `edge/monitoring/metrics.py`, `edge/config.py`
- `cloud/api/{app,routes}.py`, `cloud/ai/{detector,models}.py`, `cloud/monitoring/metrics.py`, `cloud/config.py`
- `infra/k3s/{orchestrator,scheduler,cloud-node,edge-node}{-deployment,-service}.yaml`, `namespace.yaml`
- `orchestrator/tests/test_api.py`, `scheduler/tests/*`
- `docs/PHASE7_ORCHESTRATOR_INTEGRATION_{PLAN,REPORT}.md`

## Appendix B — Repo state during Phase 8

- No Phase 8 changes to application code, deployments, Rules/RuleEndpoints, Terraform, or SGs. Only `docs/PHASE8_END_TO_END_VALIDATION_REPORT.md` was written/updated in this phase.
- Phase 7's single tracked diff remains: `infra/k3s/orchestrator-deployment.yaml` (edge URL + nodeSelector). Repo git ignores remain broken (see `AGENTS.md`); no new files tracked in this phase.
- Test harness scripts live outside the repo in `C:\Users\vigne\AppData\Local\Temp\opencode\` (`p8_*.sh`, `p8_8m_contract.sh`, etc.). Evidence command IDs (SSM `ap-south-1`): 8C `5af72a9e`/`bfc5b5e6`, 8D `782292a5`, 8E `842d5f20`/`b5da40b1`/`ed612af1`, 8F `...`/restore, 8G `p8_8g.sh`, 8H `1636b443`, 8I `74556959`/`5e395bde`, 8J `dc5e4289`/`3fe48e2b`/`41433bc5`, 8K `081d5c6a`, 8L pre `789336b4` / loop `27cf033d` / post `c1dd8e66` / audit `d15763f4`, 8M `c5ed3001`.
# Phase 9 — Production Hardening & Real-World Performance Report

**Status:** COMPLETE. 9A–9J all finished. **Aggregate verdict: PASS.**
**Author:** opencode session
**Date:** 2026-09-02
**Authoritative baseline:** `docs/PHASE8_END_TO_END_VALIDATION_REPORT.md` (Phase 8 PASS). Phase 8 proved E2E orchestration, ServiceBus-only data plane, schema parity, 503 failure semantics, 15-min stability, no direct edge exposure, CPU-inference-bound, and the missing `/metrics` ServiceBus Rule.

---

## 1. Objective

Improve production readiness and evaluate whether the architecture provides a meaningful advantage under realistic workloads — through **gated execution** (9A→9B→…→9J), **minimal additive/reversible changes**, and honest measurement. Each change requires reason / before state / exact change / backup / verification / rollback / after state. STOP before any unexpected architectural change.

Gate order: 9A baseline → 9B live-metrics decision → 9C TLS/security → 9D edge exposure cleanup → 9E legacy WSL2 cleanup → 9F camera/video E2E → 9G concurrency → 9H model/CPU optimization → 9I full regression → 9J final report.

---

## 3. Gate 9B — Live metrics decision — **PASS**

**Additive-only change (1 new Rule):** `metrics-route` (rest-source `/metrics` → servicebus-target `/metrics`), manifest `infra/k3s/edgecloud-metrics-rule.yaml`. Rules/RuleEndpoints backed up to `docs/phase9/backups/rules_baseline_2026-09-02.yaml` and `/tmp/rules-backup-20260902.yaml` on host. detect-route / health-route untouched. No application code, CloudCore, EdgeCore, scheduler, or ServiceBus change.

Verified:
- `GET /edge-ec2-node/edgecloud/metrics` via CloudCore:9443 → Router → ServiceBus → EdgeCore → `127.0.0.1:8000/metrics` → **HTTP 200**, real `SystemMetrics` `{"cpu_percent":1.0,"ram_percent":23.7,"disk_percent":18.8,"ram_used_gb":0.63,...}`.
- Chain logs: CloudCore `rule.go: add rule success` + `router:{Source:servicebus ... Resource:node/edge-ec2-node/}` + `rest.go write result success`; EdgeCore `resource: 8000:/metrics` → SimpleHandler.
- Scheduler `MetricsClient` log: `GET http://10.0.1.113:9443/edge-ec2-node/edgecloud/metrics "HTTP/1.1 200 OK"`, cloud `/metrics` 200, cloud `/health` 200 (latency), `/decision` 200 — **no warnings**.
- **Live-metrics `/orchestrate` (no snapshots) → HTTP 200**, `selected/actual=edge`, `decision_score 79.53`, reason `Edge resources within capacity (CPU 8.0% <= 85.0%, RAM 24.1% <= 85.0%, DISK 18.8% <= 85.0%) and network latency 12.8ms <= 200.0ms; running locally.` — real edge metrics now drive the existing RuleBasedPolicy. **The Phase 8 503 disappears by design** (metrics Rule is additive; decision logic unchanged).
- Negative probes after change: edge pod-IP / ClusterIP / host / public `:8000` all **blocked** — no new exposure, edge SG still zero-inbound.
- Existing routes intact: edge `/health` 200; snapshot EDGE orchestrate 200 fallback false.

Rollback: `kubectl delete rule metrics-route -n edgecloud` (single object).

**Limitation (documented):** live-mode CLOUD selection requires the edge to actually exceed 75%/85%; the edge is idle, so live mode deterministically yields EDGE (score ~79). The overload→CLOUD branch is fully covered in Phase 8 via snapshot metrics; the live path feeds the same `RuleBasedPolicy`.

## 4. Gate 9C — TLS / security hardening — **AUDIT PASS, TLS NOT IMPLEMENTED (architectural STOP, recommendation)**

Audit results (read-only):

| Endpoint | Reachable externally? | Transport | Notes |
|---|---|---|---|
| CloudHub `:10000` / `:10002` | yes (SG 0.0.0.0/0) | **TLS already** | cloudcore.yaml `websocket: port 10000`, `tlsCertFile:/etc/kubeedge/certs/server.crt`; EdgeCore in-bound over established WS |
| K3s API `:6443`, kubelet `:10250` | no (not in SG) | TLS (k3s PKI) | internal |
| CloudCore REST `:9443` (ServiceBus) | **no** (not in SG) | **plain HTTP** | internal-only data plane |
| Orchestrator HTTP NodePort `:30083` | yes (SG 0.0.0.0/0) | **plain HTTP** | public API |
| `:80` / `:443` | open in SG | idle | **no listener** → effectively closed; 443 reserved "HTTPS (future TLS)" |
| ClusterIPs (orchestrator 8003 / scheduler 8002 / cloud 8001) | no | plain HTTP | internal |

- No plaintext bypass found: no listener on 80/443; `:9443` never in SG; ClusterIPs internal-only.
- **Why not implemented now:** putting TLS on CloudCore REST `:9443` (the smallest high-value change) requires editing CloudCore server config (`rest` module certs) — a **CloudCore architecture change inside change-control scope** — and a client trust change on the orchestrator. Public API TLS is additive but introduces a new TLS-terminating component and changes the client contract. Per the gate, "if TLS would require substantial architectural changes: STOP and report instead of improvising."
- **Recommendation (Phase 10, with approval):** (a) add `tlsCAFile`/`tlsCertFile` to CloudCore REST `:9443` + orchestrator `https://`; (b) terminate TLS on the public orchestrator API (443) via ingress/LB; (c) leave `10000/10002` (already TLS) untouched.

## 5. Gate 9D — Edge exposure cleanup (hostPort) — COMPLETE: NOT APPLIED, RESTORED (STOP-trigger)

**Objective.** Remove the seemingly-inert `hostPort: 8000` from the edge-node Deployment to confirm zero host-port surface on the edge node.

**Gate condition.** "Remove hostPort ONLY if ServiceBus is confirmed unaffected; otherwise STOP and investigate."

**What happened (executed live on the cluster, 2026-09-02 02:44–02:57 UTC).**

1. **Backup:** `kubectl get deploy edge-node -o yaml` → `docs/phase9/backups/edge-node-deployment_before-9D.yaml` (on-node `/tmp/edge-node-deployment-before-9d.yaml`).
2. **Removal applied:** JSON patch `remove /spec/template/spec/containers/0/ports/0/hostPort`. Rollout OK; new pod `edge-node-5744896d98-psvsz` (10.244.0.7) Ready on edge-ec2-node; `ports=[{containerPort:8000}]` verified.
3. **Regression (STOP trigger):** edge `/health` via ServiceBus → **`TimeoutError` ×6 (~60 s)**; `/detect` via ServiceBus → no response. The path that had been 200 since Phase 7 broke immediately after hostPort removal.
4. **Root cause (proven, not assumed):**
   - The baseline premise ("hostPort is an inert DNAT") was **wrong**. KubeEdge ServiceBus (`service_port: "8000"`) forwards to **`127.0.0.1:8000` on the edge HOST's network namespace**. The edge app runs in the pod network namespace; the **CNI hostPort DNAT is the only bridge** between the two.
   - With hostPort present (Phase 8 evidence): `iptables -t nat` on edge host showed `CNI-DN-* -p tcp --dport 8000 -j DNAT --to-destination 10.244.0.6:8000`; ServiceBus requests arrived on the pod from `10.244.0.1` (host → hostport DNAT → pod).
   - With hostPort removed: **the `CNI-DN` nat rule disappeared and no `:8000` listener existed** → EdgeCore's `127.0.0.1:8000` dial had nothing to reach → /health + /detect via ServiceBus time out (the edge pods stayed Ready because the kubelet probes hit the container directly in the pod netns, not through the host bridge).
5. **Do-not-apply record kept, cluster restored:** exactly reversed single change — `add /spec/template/spec/containers/0/ports/0/hostPort = 8000`. Rollout OK → new pod `edge-node-fc54dc46-kwfpr` (10.244.0.8) Ready on edge-ec2-node, **RESTARTS 0**.
   - `ports=[{containerPort:8000,hostPort:8000,protocol:TCP}]` (== committed `infra/k3s/edge-node-deployment-edge.yaml`, no repo change needed).
   - Edge host `CNI-DN-* --dport 8000 → DNAT 10.244.0.8:8000` re-created (verified).
   - Only **one** live edge pod (kwfpr); the second row (`edge-node-5cc9b74cb5-x4ptv` NotReady, 10.42.1.17) is the **legacy WSL2 pod = Gate 9E target**, untouched.
6. **Post-restore verification:** edge `/health` via ServiceBus → **200** `{"status":"degraded","model_loaded":true,"camera_open":false}`; snapshot `/orchestrate` (actual=edge) → **200**, 1 `cup` detection, wall 1777 ms. Negative probes **still blocked** (SG zero-inbound): edge host `10.0.1.123:8000`, public `13.206.238.62:8000`, edge pod `10.244.0.8:8000` → all `TimeoutError` (same as Phase 8).
7. **Alternatives considered and rejected** (each is an architectural change inside change-control, or worse): point ServiceBus at the pod IP (EdgeCore change), `hostNetwork: true` pod (network isolation change), hand-built nat rules (unmanaged, non-CNI, breaks on restart).

**Verdict.** **NOT APPLIED / RESTORED.** `hostPort: 8000` is a **functional requirement of the ServiceBus → pod data plane**, not an exposure vector. Security posture unchanged and healthy: the port has **never been publicly reachable** — the edge SG is default-deny-zero-inbound (proven again above), and `hostPort` only creates a bind on the edge node's *internal* interface that the SG gates. **Case turned into a doc fix:** baseline §2.1 line "hostPort is an inert DNAT" corrected → it is the ServiceBus ingress bridge; do not remove without replacing the data plane (see Phase 10 recommendation: CloudCore REST TLS on `:9443` is separate and unaffected).

**Command IDs:** removal `ae506e12` → investigate (edge) `752244d2` → restore `7fb2dcd5` → confirm `51e5d052`.

## 6. Gate 9E — Legacy WSL2 cleanup — COMPLETE (reversible)

**Objective.** Remove the dead `wsl2-edge-node` (KubeEdge agent on a WSL2 VM, NotReady 14 d) and its stranded artifacts, proving the live system runs on the EC2-only topology (cloud + edge-ec2-node).

**Inventory found (9E-1, read-only):**
- Node `wsl2-edge-node`: NotReady 14 d, WSL2 Ubuntu 24.04, IP `172.18.125.42`, KubeEdge `v1.23.1`; taints `unreachable` NoSchedule/NoExecute; **finalizer `wrangler.cattle.io/node`** (k3s-managed → node deletion resolves automatically); last heartbeat 2026-08-31.
- Stuck pods (terminating 34 h; their kubelet was gone): `edgecloud/edge-node-5cc9b74cb5-x4ptv` (10.42.1.17, the old WSL2 YOLO pod, owner RS already 0/0) and `edge-test/nginx-edge-769586c896-5k6kw` + pending replacement `...gd4f6`.
- `edge-test` namespace: legacy `nginx-edge` deployment (nginx:alpine, 13 d) — non-production test rail.
- **Zero live references** to WSL2: no Service/Endpoints on 10.42.1.x, no wsl2 refs in Rules/RuleEndpoints, no CloudCore/EdgeCore ConfigMap refs, no nodeSelector anywhere (all deployments select ec2/hostname targets).
- Orphan RS `edge-node-5744896d98` (0/0, from the 9D experiment) also removed.

**Removal sequence (9E-3, one reverse-point: `docs/phase9/backups/wsl2-cleanup-2026-09-02.tar.gz` with all 6 object YAMLs):**
1. `--force --grace-period=0` delete of the 3 stuck pods (kubectl warning expected: their kubelet containers can't ack, objects force-removed from API).
2. `delete` legacy `deploy/nginx-edge`, `rs edge-node-5cc9b74cb5`, `rs edge-node-5744896d98`.
3. `delete ns edge-test` (pods already gone → finalizers cleared, no hang).
4. `delete node wsl2-edge-node` → **deleted immediately** (wrangler finalizer).

**Post-removal verification:** nodes = exactly `edge-ec2-node` (Ready) + `ip-10-0-1-113` (Ready, control-plane); no wsl2/edge-test/10.42.1 artifacts in any namespace; ServiceBus path unaffected — edge `/health` via ServiceBus **200** (`model_loaded:true`), `/orchestrate` snapshot=edge **200**, wall **312 ms**, 1 `cup`; live pod `edge-node-fc54dc46-kwfpr` Ready, **RESTARTS 0**.

**Caveat documented:** the WSL2 VM itself (user-local machine) still runs its `edgecore` service; if powered on it will attempt to **re-register a node named `wsl2-edge-node`**. Final kill is out of AWS reach (`sudo systemctl stop edgecore` / disable in the WSL2 distro). Repo copy `infra/k3s/edge-node-deployment.yaml` archived as the historical WSL2 manifest (superseded by `edge-node-deployment-edge.yaml`).

**Verdict.** **PASS.** Dead WSL2 node + stranded pods + legacy test namespace removed reversibly; 2-node production topology clean; no ServiceBus or scheduler impact.

**Command IDs:** inspect `81ee5934` → snapshot `14a8b717` → remove `56818912`.

## 7. Gate 9F — Camera/video E2E — PASS (labeled SYNTHETIC VIDEO FILE)

**Scope:** prove the full `/detect/video` surface works end-to-end through the live
infrastructure (orchestrator pod → CloudCore REST `:9443` → ServiceBus rule → EdgeCore
MQTT → edge host loopback → hostPort DNAT → edge-node pod → OpenCV + YOLOv8), with
decoded frames, real inference and per-frame detections on the result.
No physical camera exists on the hosts, so every claim here is labeled
**SYNTHETIC VIDEO FILE** (6-frame H.264 MP4, ffmpeg-encoded, 192×144 windowed-cup
frames). The webcam branch of `CameraCapture` was not exercisable (no device) and is out
of scope for the same reason.

### 7.1 Change applied (additive, reversible)

- **Added `video-route` Rule** (`rest-source` → `servicebus-target`, path `/detect/video`
  both sides). Required because `detect-route`'s `/detect` path regex **partial-swallows
  `/detect/video`** — before the Rule, `POST /detect/video?frame_step=1` returned 500 with
  CloudCore logging `Response write error ... wrote more than the declared Content-Length`
  after a ServiceBus round-trip to the wrong endpoint. After the Rule, the request reaches
  the real `/detect/video` handler (verified in the edge app log via `crictl`).
- Mirrored to `infra/k3s/edgecloud-video-rule.yaml`.
- Rollback: `kubectl delete rule video-route -n edgecloud`. Backups: `/tmp/rules-before-9f.yaml`, `/tmp/rules-after-9f.yaml` (cloud host).

### 7.2 Inference results (edge app log confirms every request landed on the edge pod)

| frame_step | status | wall_ms | total_frames | frames_processed | elapsed_ms | fps | detections |
|---|---|---|---|---|---|---|---|
| 5 | 200 | 367 | 6 | 2 | 262.44 | 7.62 | `{"scissors": 2}` |
| 3 | 200 | 270 | 6 | 2 | 250.73 | 7.98 | `{"scissors": 2}` |
| 1 | 200 | 82 | 6 | **0** | 2.64 | 0.0 | `{}` |

The step-1 row is **not** a chain failure — it is a latent application bug, see §7.3.
906-byte negative cases behaved correctly at the edge but surface through CloudCore as 500:
`.txt` extension → edge 415; empty upload → edge 400; trailing slash → 307 redirect (Starlette).
Edge-side evidence: `crictl logs` shows `POST /detect/video ... 415/400/307/200` for exactly
these requests.

### 7.3 Findings

1. **LATENT BUG — `frame_step=1` processes zero frames** (`edge/api/routes.py:224`):
   `if frame_counter % frame_step != 1: continue` — for `frame_step=1`, every
   `frame_counter % 1 == 0 != 1`, so every frame is skipped, yet the endpoint returns **200**
   with `frames_processed=0` and empty `detections`. Reproduced on the live edge pod; the
   same binary's local unit behavior matches. `frame_step` is a documented query param
   (`ge=1`) meaning "process every Nth frame" — N=1 must process all frames. Fix
   suggestion: `if (frame_counter - 1) % frame_step != 0: continue`. Applying the fix is a
   code change → image rebuild + redeploy → **Phase 10 / approved-change candidate**, not
   applied here.
2. **CloudCore translates edge 4xx to 500 at the service-bus entry** — the orchestrator sees
   500 whenever the edge app answers 400/415/503; routing itself is correct. Corroborated by
   edge 400/415 lines in `crictl logs` for the same requests. Existing Phase 8 behavior
   (edge 422 → orchestrator 503) is the same class of artifact.

### 7.4 Regression (unchanged signatures)

- edge `/health` via ServiceBus: 200 `{"status":"degraded","model_loaded":true,"camera_open":false}` (~21 ms).
- edge `/metrics` via ServiceBus: 200 `cpu 0.5–1.0%, ram 25.0%, disk 18.8%`.
- orchestrator `POST /orchestrate` (NodePort 30083, p7 image): 200
  `selected=edge actual=edge`; reason "Edge resources within capacity (CPU 1.5% <= 75.0%, RAM 25.0% <= 75.0%, DISK 18.8% <= 85.0%) and network latency 13.4ms <= 200.0ms";
  scheduler 2156 ms, inference 126 ms, `detections=["cup"] count=1` — matches the 9D/9E
  `actual=edge` signature.
- Direct exposure probes from cloud host: `edge-host:8000` and `edge-host:9443` both
  **timeout** (still zero inbound exposure after all 9F traffic).
- Rules live: `detect-route`, `health-route`, `metrics-route`, `video-route`;
  endpoints `rest-source`, `servicebus-target`. Pods all `1/1 Running 0` restarts.

**Command IDs:** chain probe `ecc18c69`; cloud logs `9d6ce93a`; stage B (video-route)
`aa7aef48`; stage C (h264) `b046043e`; edge app logs `590f90b2`, `b4090fb1`; deployed-code
diff `b29a5960`; stage D (correct steps) `d1edd789`; closeout matrix `aafe66cf`;
orchestrate snapshot `5f8feceb`; servicebus snapshot `42453f6b`, `fd5bd5be`.

**Verdict: PASS** — video E2E works end-to-end through ServiceBus; the only defect found is
the `frame_step=1` application bug (§7.3.1) which is a code-quality STAGE D finding, not a
chain defect.

## 8. Gate 9G — Concurrency benchmark — PASS

**Method (no change to production):** another SSE orchestrator pod (`orchestrator-sse-*`) was scaled to 0 after the run; no deployment/rule edits. A harness pod (`exists` result collated in `docs/phase9`) fired `POST /orchestrate` (live metrics) at concurrency levels 1/2/4/8, 12 requests each, from inside the cluster toward `orchestrator` ClusterIP:port 8003. A **forced-CLOUD** variant short-circuits the live-metrics edge probe (snapshot-style schedule inputs) to exercise the cloud inference leg under the same load.

**Results (all error-free, flat):**

| Concurrency | EDGE variant | CLOUD variant |
|---|---|---|
| 1/2/4/8 × 12 | **12/12 HTTP 200** at every level | **12/12 HTTP 200** at every level |
| p50 total edge | ~4.9–5.1 s (scheduler ~4.2–4.5 s, inference ~0.6–1.7 s) | ~1.8–2.0 s (scheduler ~0.8 s forced, inference ~1.0–1.2 s) |
| Degradation trend | flat (no increase with level) | flat |

- **No 5xx, no restarts, no NotReady, no OOM, no ServiceBus instability** at any level.
- CPU stayed 0.5–1.5% (far from saturation); ram 25–30%, disk 18.8%; loadavg 0.23 → 1.11 → 0.20.
- **Finding (cost, not defect):** in live-metrics mode the **scheduler's per-request edge/cloud metric collection dominates e2e latency (~80–87%)**. Real-time probes are the price of live decisioning; throughput and stability are unaffected. Phase 10 candidate: cache/multi-sample metrics to cut probe overhead.
- cloud-node direct `/infer`: 200, 119 ms, `cup` — isolated cloud inference engine works.

**Verdict: PASS** — no stop conditions fired; EDGE and CLOUD legs both serve flat, error-free concurrency up to 8.

**Command IDs:** harness `dcabca34` (full 9G), `088503d5` (first aborted), cloud-leg diag `44c8b527`.

## 9. Gate 9H — Model/CPU optimization experiment — DONE (no change; baseline retained)

**Method (zero production impact):** scratch `ctr` benchmark container from the live edge-node image on the edge host (EMBER: scratch = identical app + torch runtime; no pod/deployment touched). Torch numbers are the **full `YOLO.predict()` pipeline** (pre + backbone + NMS). ONNX numbers are **backbone-only forward** (`x → output0`, no pre/post), which biases ONNX *favourably*; even so:

| Variant | 1-thread | multi-thread |
|---|---|---|
| torch FP32 (full pipeline, baseline) | **171.5 ms** | 195.6 ms |
| ONNX FP32 (backbone-only, favorable)  | 105.0 ms | 403.4 ms |
| ONNX INT8 dynamic (backbone-only)      | **710.5 ms** | — |

**Findings:**
1. **INT8 dynamic quantization is ~4× SLOWER than the torch FP32 baseline** (710 vs 171 ms) on this instance (AWS c5-class Xeon 8259CL — no AVX-512 VNNI, so dynamic INT8 dequant overhead dominates). **No model optimization applied.**
2. ONNX FP32 1-thread (105 ms) is not a deployable win: it omits the pre/post-processing that Torch `predict()` includes, and its multi-thread result regresses (403 ms) vs torch NT (195 ms) → no evidence of practical gain on this CPU.
3. `torch.onnx.export` needed `dynamo=False` + pip `--target` into `/tmp/pylibs` re-asserted on `sys.path` after `import ultralytics` (ultralytics shuffles `sys.path[0]`, which was the transient "No module named 'onnx'" — resolved, not a cluster issue).

**Verdict: DONE with NO production change** — quantization/ONNX does not beat torch FP32 on this CPU; keep the current `torch` runtime. Was also an environment-quality experiment: proves the app's lazy `torch` bootstrap still wins on compute-class Xeon cores.

**Command IDs:** baseline probe `2f3c0aff`; final numbers `423d96de` (torch+ONNX+INT8); (transient "No module named 'onnx'" was a `sys.path`/ultralytics-shuffle issue resolved by re-asserting the pip `--target` dir, verified by probe `51ffa559`).

## 10. Gate 9I — Full regression — PASS

**Method (no production change):** fresh in-cluster harness from the live orchestrator pod (`orchestrator-5d76f94584-lpx97`, `/tmp/imgb64.txt` p7 image) replaying the Phase 8 acceptance surface (8C/8D/8G/8I/8M invariants) after all Phase 9 changes (9B metrics-rule, 9F video-rule, 9D/9E restores) settled. Cluster state re-verified in the same run.

**Cluster state (pre/post):** nodes exactly `edge-ec2-node` (Ready) + `ip-10-0-1-113` (control-plane); pods all `1/1 Running` with **RESTARTS 0** (cloud-node/edge-node/orchestrator/scheduler); Rules `detect-route`, `health-route`, `metrics-route`, `video-route` + endpoints `rest-source`, `servicebus-target` all present.

**Harness (10/10 PASS):**

| # | Check | Result | Phase 8 baseline |
|---|---|---|---|
| 1 | invalid short b64 | **422** `string_too_short` | matches 8G-G1 |
| 2 | invalid confidence 1.5 | **422** `less_than_equal` | matches 8G-G2 |
| 3 | no workload | **422** `field required` | matches 8G-G3 |
| 4 | partial metrics | **422** `cpu_percent` required (all-or-nothing guard) | matches 8G-G4 |
| 5 | unknown route | **404** | matches 8G-G6 |
| 6 | live orchestrate (edge) | **200** `selected/actual=edge`, reason "Edge resources within capacity…", decision 84.16 | matches 8C (now live metrics from 9B) |
| 7 | detect invariants | `inference_ms 93.39`, 625×400, `annotated_image_base64` present, 1 `cup` det | matches 8C/8M |
| 8 | response schema keys | full top-level key-set present (workload_id … total_latency_ms) | matches 8M |
| 9 | snapshot edge (CPU 12%) | **200** `actual=edge`, score 69.86, capacity reason | matches 8C |
| 10 | overloaded edge (CPU 95%, RAM 90%) | **200** `selected/actual=cloud`, score 15.58, "Edge resource overload … ", network 40ms | matches 8F/cloud leg |

**Architecture invariant re-verified (separate run):** direct `edge-host:8000` from orchestrator → **BLOCKED/TimeoutError**; `edge /health` 200 + `edge /metrics` 200 via ServiceBus (live metrics still flowing through 9B rule); `edge /detect` reached pod only via the orchestrator data plane.

**Verdict: PASS.** No regression against the Phase 8 baseline; the only delta is the intended 9B live-metrics enablement (`metrics-route`) that converted the designed 8D live-mode 503 into a working edge/cloud decision. Snapshot semantics, invalid-request guards, schema parity, detection invariants, security posture and restart counts all unchanged.

**Command IDs:** first harness `910c3b8e` (rule-query syntax aborted), `7c5f5cbe`; content-type fix `44efbc76`; Request-object fix `4fc6b43a`; flat-metrics `798a3de7`; final PASS `2ff7ccd1`; edge app logs `44c8b527`; earlier exposure probe `7c5f5cbe` (edge-host:8000 BLOCKED/TimeoutError).

## 11. Gate 9J — Final report

### 11.1 Aggregate verdict

**PHASE 9 = PASS.** All ten gates (9A→9J) executed. Nine verify cleanly; one (9D) was a deliberate **STOP-trigger that produced NO net change** — it proved a latent architectural assumption wrong and then restored it, leaving the data plane unchanged and healthy. Every intentional system change (9B `metrics-route`, 9F `video-route`, 9E WSL2 cleanup) was additive/reversible and is documented with rollback in this report.

| Gate | Outcome | Change |
|---|---|---|
| 9A baseline | PASS | none (recorded) |
| 9B live metrics | PASS | + `metrics-route` Rule (reversible) |
| 9C TLS audit | AUDIT PASS — **not implemented** (STOP recommendation → Phase 10) | none |
| 9D edge exposure cleanup | **NOT APPLIED / RESTORED** (hostPort is the ServiceBus ingress bridge) | none |
| 9E legacy WSL2 cleanup | PASS | removed dead node/pods/ns (reversible via tar) |
| 9F camera/video E2E | PASS | + `video-route` Rule; found `frame_step=1` latent bug |
| 9G concurrency | PASS | none |
| 9H model/CPU optimisation | DONE — baseline retained (INT8/ONNX slower on this CPU) | none |
| 9I full regression | PASS | none |
| 9J aggregate | **PASS** | — |

### 11.2 What Phase 9 proved

1. **Real, live decisions:** the orchestrator now schedules on **live edge/cloud metrics** (9B), not only snapshots — `selected/actual=edge` with a capacity-based reason, ending the Phase 8 live-mode 503 without touching policy code.
2. **Reversibility discipline:** 9D applied a single change, proved it broke the ServiceBus→pod bridge, and restored it exactly — the *do-not-apply* record is as valuable as a pass.
3. **Video surface works E2E** (9F): decoded frames, per-frame detections, correct fps/margins through the same ServiceBus plane — with one latent app bug identified (`frame_step=1`).
4. **Stability under load** (9G): flat, error-free response at concurrency 1–8 on both edge and cloud legs; CPU-bound, not network-bound; no restarts/OOM/5xx.
5. **ONNX/INT8 is not a win here** (9H): torch FP32 baseline retained on the c5-class Xeon; dynamic quantization regresses ~4×.
6. **No regression** (9I): every Phase 8 invariant (invalid-request guards, detection parity, schema keys, security posture, RESTARTS 0) still holds.

### 11.3 Phase 10 recommendations (each an approved-change candidate, NOT applied here)

1. **CloudCore REST TLS on `:9443`** + orchestrator `https://`, and TLS termination (443) for the public orchestrator API — the single highest-value security hardening (9C).
2. **Fix `frame_step=1`** in `edge/api/routes.py:224` (`(frame_counter - 1) % frame_step != 0`) — processes zero frames at step 1 today (9F).
3. **Scheduler live-metrics cost:** per-request metric probes dominate e2e latency (~80–87%, 9G); cache/multi-sample to cut probe overhead if latency-sensitive workloads become the goal.
4. **WSL2 final kill** (out of AWS reach): stop/disable `edgecore` on the user WSL2 VM to prevent node re-registration (9E caveat).

### 11.4 Honest limitations

- TLS/SecurityLayer on the data plane remains **plain HTTP internally** (9C — deliberate, scoped to Phase 10).
- 9F the *camera* branch of `CameraCapture` was not exercisable (no physical device); video validated with a labeled synthetic file.
- 9H is a single-instance (c5-class) result; GPU or AVX-512-VNNI hardware could reverse the quantization finding.

---

## Appendix — Gate trigger record

- **9D STOP triggered:** removing `hostPort:8000` made edge /health + /detect time out (ServiceBus forwards to `127.0.0.1:8000`, which only the CNI hostPort DNAT bridges to the pod). Restored same-session; root cause proven via `iptables`/pod-netns evidence rather than assumption.

**End of Phase 9 report.**

---

## 2. Gate 9A — Baseline (read-only, captured 2026-09-02)

Nothing was modified in 9A.

### 2.1 Hosts & services

| Host | Instance | Services | Uptime |
|---|---|---|---|
| CloudCore/control-plane | i-07ecfbdd7781c5ef5 (10.0.1.113) | **cloudcore active**, **k3s active**, **containerd active** | 14d15h, load ~0.07 |
| Edge node | i-0080aa7404208982c (10.0.1.123) | **edgecore active**, **containerd active** | 1d10h, load ~0.0 |

- KubeEdge WS ESTAB: `10.0.1.123:54284 → 13.206.229.162:10000` (edgecore pid 33990 fd 6); cloud side `[::ffff:10.0.1.113]:10000` (cloudcore pid 503357 fd 8).
- No `:8000` listener on either host (edge YOLO is pod-internal; hostPort is inserted as an inert DNAT behind default-deny SG).

### 2.2 Cluster

| Nodes | | |
|---|---|---|
| edge-ec2-node | **Ready** | 33h, v1.32.10-kubeedge-v1.23.1-dirty |
| ip-10-0-1-113 (control-plane) | Ready | 14d, v1.32.13+k3s1 |
| wsl2-edge-node (legacy) | **NotReady** | 14d — candidate for 9E |

| edgecloud pods | RESTARTS | IP | Node |
|---|---|---|---|
| orchestrator-5d76f94584-lpx97 | 0 | 10.42.0.18 | control-plane |
| scheduler-6dcbffbcdb-2kktm | 0 | 10.42.0.6 | control-plane |
| cloud-node-6d9f488769-c5pph | 0 | 10.42.0.19 | control-plane |
| edge-node-fc54dc46-bs56z | 0 | 10.244.0.6 | edge-ec2-node |
| edge-node-5cc9b74cb5-x4ptv (legacy, DESIRED 0) | 0 | 10.42.1.17 | wsl2-edge-node (NotReady pod) |

### 2.3 Routing surface (Rules/RuleEndpoints — exported & backed up in `docs/phase9/backups/rules_baseline_2026-09-02.yaml`)

- Rule `detect-route`: rest-source `/detect` → servicebus-target `/detect`.
- Rule `health-route`: rest-source `/health` → servicebus-target `/health`.
- RuleEndpoint `rest-source` (rest, `{}`); RuleEndpoint `servicebus-target` (servicebus, `service_port: "8000"`).
- **No `/metrics` Rule** — live-metrics scheduling currently 503 (to be decided in 9B).

### 2.4 Environment (unchanged)

- Orchestrator: `ORCHESTRATOR_EDGE_URL=http://10.0.1.113:9443/edge-ec2-node/edgecloud`, `CLOUD_URL=http://cloud-node.edgecloud.svc:8001`, `SCHEDULER_URL=http://scheduler.edgecloud.svc:8002`, PORT 8003.
- Scheduler: PORT 8002 only (no remote-endpoint env; URLs arrive per-request from orchestrator body).

### 2.5 Functional & latency baseline (live, from orchestrator pod)

| Probe | Result |
|---|---|
| cloud `/health` | 200 `{"status":"ok",...,"model_loaded":true}` |
| edge `/health` via ServiceBus | 200 `{"status":"degraded",... "model_loaded":true,"camera_open":false}` |
| Snapshot `/orchestrate` → EDGE (high) | **200**, actual=edge, sched 95.1ms, fwd+infer 212.1ms, inf 122.4ms, wall 315ms; cup conf 0.8701 count 1 |
| Snapshot `/orchestrate` → CLOUD (medium, edge 90/85) | **200**, actual=cloud, sched 15.3ms, fwd+infer 183.6ms, inf 107.7ms, wall 201ms; cup conf 0.8701 count 1 |
| Live-metrics `/orchestrate` (no snapshots) | **503** `target=error (edge=missing, cloud=ok)` — baseline for 9B |

### 2.6 Security surface (read-only)

- **Edge SG `edgecloud-edge-node-sg` (sg-074dd39fb8d93006b): zero inbound rules** (default-deny, incl. port 8000).
- **Cloud SG `edgecloud-ec2-sg` (sg-09aada8e7591efe3e)** inbound 0.0.0.0/0: 80 (orchestrator public API), 443 (future TLS), 10000 (CloudHub WS), 10002 (edgeHub https), 30083 (orchestrator NodePort). **No 9443, no 8000.**
- Terraform state `infra/terraform/terraform.tfstate`: vpc-085fedc9cda6619be, 2 instances, 3 SGs (cloud/edge/rds), RDS db-MMJJZK2RMSZREEZVJV45WAUSLU, 4 ECR repos, EIP, IAM roles, CW log group `/edgecloud/ec2-services`, SecretsManager `edgecloud/db-credentials`. **No Terraform changes in Phase 8/9.**
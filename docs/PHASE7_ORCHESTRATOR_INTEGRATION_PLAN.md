# Phase 7 — Orchestrator ↔ KubeEdge ServiceBus Integration Plan

**Status:** PLAN ONLY — investigation (Gates 7A/7B/7C) complete. **No source, scheduler, edge, Terraform, Security-Group, CloudCore/EdgeCore, Rule/RuleEndpoint, or pod-redeploy changes have been made.** Do not execute §9 until this plan is explicitly approved.
**Author:** opencode session
**Date:** 2026-09-01
**Type:** Integration of the existing `orchestrator`/`scheduler` with the proven Phase 6 CloudCore → KubeEdge ServiceBus → edge-YOLO path.

---

## 1. Objective

Turn the orchestrator's otherwise-working control loop (scheduler decision → forward image → return `DetectionResult`) into one that can actually reach the **real edge YOLO node** over the proven CloudCore ServiceBus tunnel. Today the edge leg is broken by configuration only: `ORCHESTRATOR_EDGE_URL` points at an **unroutable ClusterIP**, so every edge-targeted run fails with a 503. The cloud leg already works end-to-end.

Deliverable: this integration plan plus a baseline evidence record that pinpoints the exact 1-line config change and the one schema/routing gap that must be decided before going live. **Stop and wait for approval** before touching anything.

## 2. Verified baseline (Gates 7A/7B/7C — live evidence)

All tests run from inside the orchestrator pod (`orchestrator-696dc775d-8fckr`, 10.42.0.7) via `kubectl exec ... python3`, on the CloudCore host (i-07ecfbdd7781c5ef5).

| # | Test | Result |
|---|------|--------|
| A | orchestrator `/health` (own) | HTTP 200, `{"status":"ok","service":"orchestrator","version":"0.1.0"}` |
| B | `/orchestrate` (current `edge_url`, metrics omitted) | **HTTP 503** `Workload not executed now: target=error (Required metrics are unavailable (edge=missing, cloud=ok); cannot decide placement.)` |
| C | ServiceBus `/detect` via node IP `http://10.0.1.113:9443/edge-ec2-node/edgecloud/detect` (real image, 50 148-char b64) | **HTTP 200**, e2e 0.15s, `Server: uvicorn`, `frame 625x400`, `inference_ms 128.63`, detection `cup` class_id 41 conf 0.87, `count 1` |
| D | ServiceBus `/health` via node IP | HTTP 200, 0.013s, `{"status":"degraded",...,"model_loaded":true,"camera_open":false}` |
| E | ServiceBus `/metrics` via node IP | **HTTP 404** — no Rule routes `/metrics` |
| F2 | `/orchestrate` with explicit edge/cloud/network metrics (edge healthy, high prio → scheduler picks EDGE) | **HTTP 503** `Inference failed: Connection error to http://edge-node.edgecloud.svc:8000/detect:` |
| K | `/orchestrate` explicit metrics favoring CLOUD (edge cpu 95%, cloud 10%) | **HTTP 200** — scheduler offloads to cloud, orchestrator forwards to `cloud-node` `/infer`, full real `cup` detection, `total_latency_ms 2726.05` |

### 2.1 Root cause of the broken edge leg
- `ORCHESTRATOR_EDGE_URL=http://edge-node.edgecloud.svc:8000` (deployment, §6). The `edge-node` Service endpoint is `10.244.0.4:8000` — KubeEdge pod CIDR `10.244.0.0/24`, **not routable from cloud pods** (confirmed in `KUBEEDGE_NETWORKING_ANALYSIS.md`). Hence:
  - metrics omitted → scheduler's live fetch of `edge_url/metrics` fails → `edge=missing` → `target=error` → 503 (B).
  - metrics supplied → scheduler picks EDGE → `EdgeClient.detect` POST to the ClusterIP → transport error → 503 (F2).

### 2.2 The proven working edge path (Phase 6 → this plan's target)
```
orchestrator pod --HTTP--> CloudCore REST router *:9443 (0.0.0.0, restTimeout 60)
   -> Rule detect-route (source rest-source: /detect, target servicebus-target, path /detect)
   -> KubeEdge ServiceBus -> edge-ec2-node EdgeCore -> edge-node pod (:8000) -> YOLOv8
```
Verified live: C (detect → 200 real detection) and D (health → 200).

## 3. The single required change (config-only)

Set the orchestrator's edge URL to the node-scoped ServiceBus REST path **in `infra/k3s/orchestrator-deployment.yaml` only**:

```
ORCHESTRATOR_EDGE_URL: "http://edge-node.edgecloud.svc:8000"
  -> "http://10.0.1.113:9443/edge-ec2-node/edgecloud"
```

Rationale:
- CloudCore REST is **HTTP on `:9443`**, not HTTPS (the older migration plan's `https://13.206.229.162:9443` was wrong; Phase 6 and test C both used `http://127.0.0.1:9443`/`http://10.0.1.113:9443`).
- Node path is **`/edge-ec2-node/edgecloud`** (node name + CloudCore namespace), and the Rule extends it (`/detect`, `/health`). `_BaseClient._url()` joins `{base}/{path}` with no double-slash, so `http://10.0.1.113:9443/edge-ec2-node/edgecloud` + `/detect` = the exact working URL in test C.
- `edge_url` feeds both the scheduler `decide(edge_url=...)` remote-metrics fetch and the `EdgeClient` forward, so one env change covers both.

## 4. Critical gaps that gate a clean "live metrics" path (must be decided)

Changing `ORCHESTRATOR_EDGE_URL` to the ServiceBus path **fixes /detect and /health** but **not the scheduler's live-metrics fetch**, because:

1. **No `/metrics` ServiceBus Rule** (confirmed, §2.1/E, §5). `scheduler/metrics_client.py::fetch_edge` calls `{base}/metrics`; via ServiceBus that 404s → `None` → `edge=missing` → `target=error` (the policy hard-fails when edge metrics are absent, `scheduler/policies.py`). So an un-supplied-metrics `/orchestrate` would still 503 after the config change.

   Decision point — pick one:
   - **(A) Add a `metrics`-route** (a second Rule in the pattern of `health-route`: `sourceResource.path /metrics`, `targetResource.path /metrics`) to the existing CloudCore rule set. Then live edge metrics flow and the user can omit snapshot metrics (demo-friendly, matches the design intent). This IS a Rule/RuleEndpoint change, currently forbidden until approval.
   - **(B) Keep routing as-is (no `/metrics` Rule); always supply metrics snapshots** in `/orchestrate` requests (deterministic decision path). Zero infra change; requires the client to carry live-ish `edge_metrics`. Safe; recommend as Phase 7 default if we want a no-infra-change go-live.
   - **(C) Both** — add the Rule AND support supplied snapshots.

2. **Timeout, `timeout_sec` vs CloudCore `restTimeout`.** Orchestrator client timeout default `30.0s` (`orchestrator/config.py`); CloudCore router `restTimeout 60s`. First-run YOLO model load / cold camera + ServiceBus image transfer can push edge inference near 2.5s+ (test K cloud inference was 2516ms on a loaded CPU node; edge C was 128ms). 30s ≪ 60s, so the orchestrator client is the tighter bound but is still comfortable for the observed ~0.1–3 s edge/cloud inferences. No change required; note it.

3. **`/health` returns `status:"degraded"`** (camera closed on headless edge) with `model_loaded:true`. `EdgeClient.detect` sends `{"image_base64","confidence","annotated","classes"}` — the `null` fields are accepted; `inference_result` is an opaque dict to the orchestrator (test K already returned one). No parsing dependency. No change.

## 5. CloudCore routing surface (live, to be referenced)

```
edgecloud ns:
  RuleEndpoint  rest-source         (ruleEndpointType: rest,   properties:{})
  RuleEndpoint  servicebus-target   (ruleEndpointType: servicebus, properties:{service_port:"8000"})
  Rule          detect-route        source rest-source /detect -> target servicebus-target /detect
  Rule          health-route        source rest-source /health -> target servicebus-target /health
  (NO metrics-route -> /metrics 404)
```
Both Rules/Endpoints are 11d old, generation 1, untouched. CloudCore binds `*:9443` router (addr 0.0.0.0, enable true). Targets the live edge pod on `edge-ec2-node` (10.244.0.4:8000).

## 6. Files involved

- `infra/k3s/orchestrator-deployment.yaml` — **the only file** that changes for the config-only fix (§3, line 26-27). Optionally also the edit referenced in `docs/edge_ec2_migration_plan.md` where the SAME stale `edge_url` is documented (doc-only, no runtime effect).
- `infra/k3s/edge-node-deployment-edge.yaml` — the live edge-node deployment (nodeSelector `edge-ec2-node`); do NOT change.
- `infra/k3s/{cloud-node,scheduler}-deployment.yaml`, `namespace.yaml`, Services — do NOT change.
- `orchestrator/{config,clients,service,models}.py` — read-only evidence; no code change needed.
- `scheduler/{config,metrics_client,decision_engine,policies}.py` — read-only evidence; no code change needed for option (A) or (B).
- `infra/terraform/*.tf` — SG/TF context only; no changes planned (CloudCore `:9443` is already open; rest was proven reachable from the pod).
- `docs/KUBEEDGE_NETWORKING_ANALYSIS.md` — documents the ClusterIP non-routability that motivates this change.

## 7. Rules / RuleEndpoint changes (deferred — only after approval & only for option A)

If option (A) in §4.1 is approved, add **one** additive Rule mirroring `health-route`:
```
apiVersion: rules.kubeedge.io/v1
kind: Rule
metadata: {name: metrics-route, namespace: edgecloud}
spec:
  source: rest-source
  sourceResource: {path: /metrics}
  target: servicebus-target
  targetResource: {path: /metrics}
```
No changes to existing Rules/Endpoints. Additive-only; rollback = `kubectl delete rule metrics-route -n edgecloud`.

## 8. Scheduler interfaces (no change; for reference)

- `/decision` accepts optional `workload` + full metrics snapshot (deterministic) OR `edge_url`/`cloud_url` (live fetch). `RuleBasedPolicy` → EDGE when edge healthy & latency within budget; CLOUD on edge overload; ERROR when required metrics missing. Thresholds observed: edge CPU `> 85.0%` → offload; network latency `<= 200ms` for edge retain.
- The orchestrator already passes `settings.edge_url`/`cloud_url` into `decide(...)` and forwards to the selected node. With §3's env change, the live-fetch (A) or snapshot (B) both feed the SAME ServiceBus `/health` and `/detect` correctly.

## 9. Implementation sequence (EXECUTE ONLY AFTER APPROVAL)

Config-only fix:
1. Verify the CloudCore REST path once more from the cloud host (`curl/socket` or existing evidence C/D).
2. Edit `infra/k3s/orchestrator-deployment.yaml` `ORCHESTRATOR_EDGE_URL` → `http://10.0.1.113:9443/edge-ec2-node/edgecloud`.
3. `kubectl apply -f infra/k3s/orchestrator-deployment.yaml`, wait for rollout (`kubectl rollout status`), confirm new pod env.

Validation:
4. `/orchestrate` with explicit healthy edge metrics (deterministic EDGE) → expect HTTP 200 + real edge `DetectionResult` (cup), `actual_target: edge`.
5. `/orchestrate` with high edge load metrics → offload to cloud → 200 (regression vs test K).
6. `/orchestrate` metrics omitted → depends on §4 decision: with (A) live-edge works; with (B) provably still needs supplied snapshots (document as limitation).
7. If (A) approved: apply the `metrics-route` Rule, then repeat step 6 → expect 200 with scheduler deciding on live edge metrics.
8. Capture orchestrator/scheduler logs + a live ServiceBus detect for the evidence record.

## 10. Verification / acceptance criteria

- `GET /health` orchestrator → 200 (unchanged).
- `/orchestrate` targeting edge (deterministic OR live metrics) → **HTTP 200 with `actual_target:"edge"`** and a valid `DetectionResult` (non-null `count>0`, real `detections`), via the ServiceBus path (orchestrator pod logs show `POST http://10.0.1.113:9443/edge-ec2-node/edgecloud/detect ... 200 OK`).
- Cloud fallback still works (240 regressed against test K).
- No CloudCore/EdgeCore/RuleEndpoint/SG/Terraform/pod-redeploy of edge changes beyond the orchestrator deployment + (if approved) the additive `metrics-route`.

## 11. Rollback

- Config change: revert `ORCHESTRATOR_EDGE_URL` to `http://edge-node.edgecloud.svc:8000`, re-apply deployment. Instant, additive.
- If (A) metrics-route deployed: `kubectl delete rule metrics-route -n edgecloud`.
- Nothing else touched; previous cloud/orchestrator behavior (test B/F2 = 503 on edge) is the original state.

## 12. Costs

- Zero incremental: no new instances, EIPs, volumes, or SG changes. Reuses existing CloudCore `:9443`, edge-ec2-node, and the existing orchestrator pod/svc.

## 13. Risks

- **Live-metrics path still 503 after config change** if option (B) chosen and callers omit snapshots — mitigated by documenting the snapshot requirement or choosing (A).
- **`/metrics` 404 → `edge=missing`** — the root of the above; only (A) removes it.
- **Node-name/namespace path drift** (`edge-ec2-node`/`edgecloud`) if the edge node is ever rebuilt under a different name — CloudCore path would need updating in `ORCHESTRATOR_EDGE_URL`.
- **restTimeout 60s vs client 30s** — client is the tighter bound; acceptable for observed latencies but noted for heavy loads.
- **Public-node-IP instability** if the cloud EC2 restarts without a static IP — CloudCore `:9443` is private `10.0.1.113`, stable within the VPC; unaffected.

## 14. Open questions for approval

1. **Option A or B for the live-metrics path** (§4.1) — add a `metrics-route`, or rely on supplied snapshots (no infra change)?
2. Confirm the orchestrator deployment **may be re-applied/rolled** (it already runs `latest` and is the integration point; no manual reuse of the old pod needed).
3. Confirm we may treat test C/D/E/K and §2.1 records as the Phase 7 baseline evidence file.

## 15. Baseline evidence summary (raw, live)

- ServiceBus `/detect` (pod→node IP): `HTTP 200 time=0.15s Server uvicorn {"source":"yolov8n.pt","timestamp":"2026-09-01T11:25:44Z","frame_width":625,"frame_height":400,"inference_ms":128.63,"detections":[{"bbox":{...},"confidence":0.8700916767120361,"class_id":41,"class_name":"cup"}],"annotated_image_base64":null,"count":1}`.
- ServiceBus `/health`: `HTTP 200 time=0.013s {"status":"degraded",...,"model_loaded":true,"camera_open":false}`.
- ServiceBus `/metrics`: `HTTP 404`.
- `/orchestrate` edge-forward current: `503 Connection error to http://edge-node.edgecloud.svc:8000/detect:`.
- `/orchestrate` metrics-omitted current: `503 target=error (edge=missing, cloud=ok)`.
- `/orchestrate` cloud-favored: `HTTP 200`, `selected_target/actual_target=cloud`, `decision_reason="Edge resource overload (CPU 95.0% > 85.0%)...offloading to cloud."`, `total_latency_ms 2726.05`, real cup detection.

## 16. Commands that WOULD run at implementation time (after approval)

From repo root (CloudCore host via SSM; `ssm-run.ps1 -ScriptPath <local.sh> -InstanceId i-07ecfbdd7781c5ef5`):
```bash
# 1. config-only edge-url fix
kubectl apply -k/kubectl apply -f infra/k3s/orchestrator-deployment.yaml
kubectl rollout status deployment/orchestrator -n edgecloud
kubectl get pod orchestrator-... -n edgecloud -o yaml | grep -i ORCHESTRATOR_EDGE_URL
# 2. validate edge-targeted orchestrate (deterministic healthy edge metrics) -> expect 200 actual_target=edge
kubectl exec -n edgecloud orchestrator-... -- python3 -c "..."   # real image b64
# 3. (option A only) additive metrics-route
kubectl apply -f infra/k3s/rule-metrics-route.yaml
kubectl get rules -n edgecloud
```
Exact inline payloads are in the session's evidence scripts; frozen at implementation time.

## 17. File-creation summary (this deliverable)

- `docs/PHASE7_ORCHESTRATOR_INTEGRATION_PLAN.md` — this plan.
- (Option A, if approved) `infra/k3s/rule-metrics-route.yaml` — additive Rule.
- No other files.

## 18. STOP — approval gate

Phase 7 investigation is complete. The map to a working edge leg is a **one-line config change** (§3) plus an explicit decision on the live-metrics path (§4.1). Per project gate discipline, **no modifications to orchestrator/scheduler/edge source, CloudCore/EdgeCore, Rules/RuleEndpoints, Terraform, SGs, or pod redeploys have been made and none will be until this plan is approved.**

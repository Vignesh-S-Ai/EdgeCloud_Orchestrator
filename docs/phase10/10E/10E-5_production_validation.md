# Gate 10E-5 — Production Deployment & Validation: CACHE DEPLOYED & VALIDATED (with limitation)

**Date:** 2026-09-02
**Gate:** 10E-5 = controlled production deployment of the 10E metrics cache at `SCHEDULER_METRICS_TTL_SEC=1.0`, then benchmark vs the 10E-2 baseline.
**Result: PASS (functional + regression) — WITH LIMITATION.** The cache image+env were applied, verified, placement-constrained to the cloud control-plane node, all functional-gate steps passed, and the production benchmark matched the 10E-2 methodology. **However, the cache did NOT deliver an observable, reproducible latency reduction** at the configured `1.0 s` TTL in this topology (noise-level, mixed-sign deltas). This is reported honestly — no fabricated improvement is claimed.

This report **supersedes** the previous STOP reports. It documents: the two failed attempts (A), the placement remediation (B), the successful deployment + verification (C–E), the functional gate (F), the cache-behavior evidence (G), the benchmark and comparison (H/K), `/decision` vs `/orchestrate` (L), regression (M), and the verdict (N).

---

## A. Previous attempts (context, per gate: distinctly documented)

1. **Attempt 1 — ROLLED BACK.** Pushing the rollout, the new pod landed on the re-registered `wsl2-edge-node`, whose kubelet returned **ECR 403** → `ImagePullBackOff`, stuck rollout. Rolled back cleanly to `scheduler:latest` (`sha256:a3d9079d…cc9d25`), no TTL. Optimization not deployed.
2. **Attempt 2 — STOPPED (functional failure, not performance).** The rollout completed (`:10e-4` + TTL=1.0) and `RESTARTS=0`, **but** the scheduler Deployment (unconstrained) landed on the KubeEdge **`edge-ec2-node`** (10.244.0.10). Cloud-side `10.42.x` cannot route to the edge `10.244.x` pod network, so the ClusterIP endpoint (10.244.0.10:8002) and the direct pod IP both timed out from the orchestrator → **production `/decision` down**. Root cause = **topology/placement**, NOT the cache (the same `:latest` image fails identically on an edge node with no L3 route). No benchmark, no performance claim (previous report documented failure and STOP).

## B. Placement remediation (pre-deploy, done + verified)

The two failed attempts proved the scheduler/cloud-node **must** be pinned to the cloud control-plane node. Authorized remediation (documented in `10E-5_placement_remediation.md`):

- Pin `scheduler` and `cloud-node` to `nodeSelector: {kubernetes.io/hostname: ip-10-0-1-113.ap-south-1.compute.internal}` (cloud CP).
- Orchestrator already pinned to the same cloud CP; `edge-node` pinned to `edge-ec2-node`.
- `wsl2-edge-node` remains **cordoned** (`unschedulable=true`); not uncordoned.

Post-remediation verification pass: scheduler `/health` 200, `/decision` 200 (target=edge, score 82), cloud `/health` 200, edge `/metrics`+`/health` via ServiceBus 200, edge access via pod IP/ClusterIP still blocked (ServiceBus-only). Report at `docs/phase10/10E/10E-5_placement_remediation.md`.

## C. Pre-deploy snapshot (this successful run, before any further change)

State already healthy — no redundant re-deploy was performed. Verified at STEP 1:

- Scheduler pod `scheduler-796d7db85d-4wx77` (10.42.0.20) **on cloud CP**, image `…:10e-4`, digest `sha256:a3aa6fbc…8340c`, env `SCHEDULER_METRICS_TTL_SEC=1.0`, Ready, RESTARTS=0; `/health` 200, `/decision` 200.
- `cloud-node` (10.42.0.21) on cloud CP `:latest`, Ready RESTARTS=0; `orchestrator` (10.42.0.18) unchanged; `edge-node` (10.244.0.9) unchanged.
- All 4 Ready RESTARTS=0; wsl2 `unschedulable=true`; nodeSelectors present on all 4 deployments.

## D. New image digest (unchanged target — do not rebuild)

- **Optimized image:** `325580898273.dkr.ecr.ap-south-1.amazonaws.com/edgecloud/scheduler:10e-4`
- **Digest:** `sha256:a3aa6fbc7703f96c73a201c900c8d7f14e8a873025680e8361e2eea273b8340c`
- Rollback image `:latest` digest: `sha256:a3d9079d6386fdc5ccc4e1e036951cd1d39a103c85b90cc9944f05fa44cc9d25`. `:latest` was **not** overwritten.

## E. Production changes applied / verified

The cache image + `SCHEDULER_METRICS_TTL_SEC=1.0` were already applied during the earlier retry; this run **verified in place** rather than re-deploying (no churn):

1. `kubectl set image deploy/scheduler scheduler=…:10e-4` — confirmed: `image=…:10e-4`, running digest `sha256:a3aa6fbc…8340c` (**exact**).
2. `kubectl set env deploy/scheduler SCHEDULER_METRICS_TTL_SEC=1.0` — confirmed in the running pod environment (`SCHEDULER_METRICS_TTL_SEC=1.0`).
3. Placement: pod on cloud CP (`ip-10-0-1-113`), nodeSelector preserved, 1/1 Ready, `RESTARTS=0`, no CLBO/OOM, no new rollout executed.

Cache config confirmed wired end-to-end from the running pod: `scheduler/config.py` `metrics_ttl_sec: float = 0.0` is read from env; `scheduler/metrics_client.py` implements a per-URL TTL cache (`_cache[url] = (now + ttl, payload)`), clamps TTL to `MAX_METRICS_TTL_SEC = 60.0`, single-flight via `anyio.Event`, and **always fetches `/health` latency live with `use_cache=False`** (non-cachable). Only successful metric payloads are cached (failures are not cached; failing to cache a failure means a bad fetch never poisons the cache — 62 unit tests pass, including the failure-not-poisoning case).

## F. Functional gate (STEP 4) — ALL PASS (14/14)

Run from the orchestrator pod (the real consumer) against scheduler Service, cloud node, and edge via ServiceBus. (Check 11, edge video path, initially reported a 500 because the test sent a JSON `video_base64` body, which the endpoint does not accept; re-run with the endpoint's required **multipart file upload** returned 200 — the failure was a test-payload issue, not a regression.)

| # | Check | Result | Detail |
|---|-------|--------|--------|
| 1 | scheduler `/health` | PASS | 200, ~90 ms |
| 2 | scheduler `/decision` live | PASS | 200, target=edge |
| 3 | `/orchestrate` snapshot | PASS | 200, sel=edge |
| 4 | `/orchestrate` live | PASS | 200, sel=edge |
| 5 | edge target selectable | PASS | target=edge, score 80.8 |
| 6 | cloud target selectable | PASS | target=cloud |
| 7 | edge `/metrics` via ServiceBus | PASS | 200, ~1008 ms |
| 8 | cloud `/metrics` | PASS | 200, ~1004 ms |
| 9 | cloud `/health` | PASS | 200, ~3 ms |
| 10 | edge detect path | PASS | 200, 1 detection |
| 11 | edge video path (multipart) | PASS | 200, tiny_h264.mp4 6 frames / 2 processed, detections scissors=2 |
| 12 | `/decision` + `/orchestrate` schema | PASS | keys unchanged (see below) |
| 13 | direct edge pod `:8000` | PASS (blocked) | URLError |
| 14 | edge via ClusterIP `:8000` | PASS (blocked) | URLError |

Decision schema (unchanged): `workload_id,target,score,reason,priority,timestamp`. Orchestrate schema (unchanged): `actual_target,decision_reason,decision_score,fallback_reason,fallback_used,inference_latency_ms,inference_result,priority,scheduler_latency_ms,selected_target,timestamp,total_latency_ms,workload_id`.

## G. Cache-behavior evidence (STEP 5) — honest result

Configured `SCHEDULER_METRICS_TTL_SEC=1.0`. Cache hit/miss counters are **debug-level** and the running scheduler logs at **INFO**, and we did **not** alter instrumentation — so hits are observed behaviorally via decision timing (cold vs within-TTL vs after-expiry), not claimed from counters.

Sequential live `/decision` (from orchestrator pod, edge_url+cloud_url supplied):

| Step | Timing |
|------|--------|
| R1 cold (after >1 s idle) | 2070 ms |
| R2 immediate | 2056 ms |
| R3 immediate | 2165 ms |
| R4 immediate | 2080 ms |
| R5 after 4 s idle (>TTL) | 2052 ms |

**No observable within-TTL speedup.** R2–R4 ≈ R1 ≈ R5. **Explanation:** each live `/decision` performs serial metric fetches — edge `/metrics` ~1 s (via ServiceBus) + cloud `/metrics` ~1 s + live `/health` — totaling ~2 s per decision. Because the configured TTL (1.0 s) is **shorter than the metrics fetch latency**, every decision's metric entries expire before the next decision, so every decision effectively does a full live refetch. `/health` latency is by design always measured live (`use_cache=False`), so it is unaffected by the cache. The cache image+env are verified deployed and correct (exact digest, env wired, unit-tested), but at `TTL=1.0 s` under these fetch latencies it yields **no reproducible cross-request latency reduction**. This is reported as-is; no hit/miss or speedup claim is made beyond what timing directly shows.

## H. Cache / TTL evidence summary

- Deploy verified: exact `:10e-4` digest, `SCHEDULER_METRICS_TTL_SEC=1.0` in the pod env, config/code wired (TTL clamp ≤ 60 s, single-flight, failures-not-cached, `/health` always live).
- Behavioral timing: no within-TTL versus after-expiry speedup observed (rationale in G).
- No debug hit/miss counters exposed at INFO; instrumentation intentionally not altered; no hit/miss numbers asserted.

## I. Benchmark (STEP 6) — exact 10E-2 methodology

Same method as the 10E-2 baseline: concurrency **1/2/4/8 × 12 requests each**, body `{"workload":{"workload_id":"bench10e","latency_requirement_ms":100.0,"priority":"medium"}, "edge_url", "cloud_url"}` → `POST http://scheduler.edgecloud.svc:8002/decision`, from the orchestrator pod. All responses HTTP 200 (0 failures).

| Concurrency | Requests | 10E-5 mean ms | 10E-5 p95 ms | 10E-5 median |
|-------------|----------|---------------|--------------|--------------|
| 1 | 12 | 2081.7 | 2144.5 | 2056.6 |
| 2 | 24 | 2188.0 | 2205.2 | 2188.8 |
| 4 | 48 | 2378.6 | 2475.9 | 2385.8 |
| 8 | 96 | 2757.9 | 2964.4 | 2772.4 |

Decision behavior recorded: all target=`edge` (edge score ~80–82), no cloud fallback, no errors — matches 10E-2 behavior; no behavioral change introduced by the cache.

## J. Comparison against 10E-2 baseline

Baseline (10E-2) means 2100.9 / 2201.1 / 2305.8 / 3128.3; p95 2153.1 / 2306.3 / 2446.5 / 3667.9.

| Concurrency | Δ mean (ms) | Δ mean (%) | Δ p95 (ms) | Δ p95 (%) |
|-------------|-------------|------------|-------------|------------|
| 1 | −19.2 | −0.91% | −8.6 | −0.40% |
| 2 | −13.1 | −0.60% | −101.1 | −4.38% |
| 4 | **+72.8** | **+3.16%** | **+29.4** | **+1.20%** |
| 8 | −370.4 | −11.84% | −703.5 | −19.18% |

## K. Mean / p95 percentage differences — interpretation

The deltas are **mixed-sign and mostly within run-to-run noise** (±3–4% typical), and concurrency 4 went the **opposite** direction (+3%). Only concurrency 8 shows a larger negative delta (−11.8% mean, −19.2% p95) — plausible as an artifact of cross-run environment variance (edge/cloud fetch jitter over ServiceBus, host load) rather than a cache effect, because (a) the behavioral test (G) shows no caching speedup, and (b) a cache benefit would appear consistently across all concurrency levels, not only at 8. **No systematic or reproducible improvement is demonstrated.** We therefore do **not** claim a performance gain.

## L. `/decision` vs `/orchestrate` analysis

Consistent with 10E-2/10E-3: `/decision` = scheduler metric-collection + policy (the path the cache could affect); `/orchestrate` = scheduler decision + forwarding + inference (adds the fixed ~2 s forwarding/inference cost and is dominated by it). This run benchmarked the `/decision` path (the cache-relevant one); `/orchestrate` was exercised only in the functional gate (snapshot + live, both 200, sel=edge). A cache gain, if the TTL made it observable, would appear only on `/decision`, which is where we measured; none materialized.

## M. Regression results (post-validate, STEP 7) — clean

- Nodes: `ip-10-0-1-113` (cloud CP) Ready, `edge-ec2-node` Ready, `wsl2-edge-node` Ready,**SchedulingDisabled** (cordon preserved).
- Pods: all 4 (`scheduler`, `cloud-node`, `orchestrator`, `edge-node`) `Running`/`Ready`, `RESTARTS=0`; no OOMKilled/CrashLoopBackOff/lastState reasons.
- Placement: `scheduler` → cloud CP, `cloud-node` → cloud CP, `orchestrator` → cloud CP, `edge-node` → `edge-ec2-node`; nodeSelectors confirmed on all 4 deployments.
- Scheduler image: `…:10e-4` (exact digest confirmed).
- KubeEdge Rules (`detect-route`, `health-route`, `metrics-route`, `video-route`), RuleEndpoints (`rest-source`, `servicebus-target`), Services (`cloud-node`, `edge-node`, `orchestrator` NodePort 30083, `scheduler`) — unchanged, present.
- Edge access contract preserved: direct edge pod `:8000` blocked, edge ClusterIP `:8000` blocked, ServiceBus `http://10.0.1.113:9443/edge-ec2-node/edgecloud/health` 200.

## N. Final 10E-5 verdict

**PASS WITH LIMITATION.**

- **PASS:** controlled cache deployment is verified correct and stable in production — exact `:10e-4` digest, `SCHEDULER_METRICS_TTL_SEC=1.0`, pinned to the cloud CP node (reachable), all 14 functional-gate steps pass, benchmark runs at 100% success with unchanged decision behavior, and the full regression (nodes/pods/restarts/OOM, placement/nodeSelectors, Rules/RuleEndpoints/Services, edge-access ServiceBus-only contract) is clean.
- **LIMITATION (honest):** at the configured `TTL = 1.0 s`, the cache produces **no observable or reproducible `/decision` latency reduction** in this topology, because the ~2 s serial metric-fetch path exceeds the 1 s TTL, so every decision does a full live refetch. Mixed-sign, noise-level benchmark deltas confirm this (concurrency 4 moved opposite; only concurrency 8 showed a large delta, not reproducible across runs). **No performance improvement is claimed.** Producing a measurable cache benefit would require a TTL longer than the metric-fetch latency (e.g., several seconds) — a config decision that is out of this gate's scope and would need its own approval, and would trade freshness for speed.

---

## Required status line

10E-5 CACHE: DEPLOYED & VALIDATED (PASS WITH LIMITATION — functional + regression clean; no reproducible performance gain at TTL=1.0 s, reported honestly)
File: docs/phase10/10E/10E-5_production_validation.md
Production changes: SCHEDULER `:10e-4` + `SCHEDULER_METRICS_TTL_SEC=1.0` (verified in place, no re-deploy churn) with placement remediation (scheduler+cloud-node pinned to cloud CP)
Benchmark: /decision 1/2/4/8 ×12, all 200; means 2081.7/2188.0/2378.6/2757.9, p95 2144.5/2205.2/2475.9/2964.4 — vs 10E-2: mixed-sign/noise-level deltas, no systematic gain; cache effect not observable at TTL=1.0 s
No fabricated performance improvement claimed.
Next gate: 10E-6

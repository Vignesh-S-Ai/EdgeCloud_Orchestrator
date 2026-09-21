# Gate 10E-3 — Live-Metrics Scheduling: Source/Config Investigation

**Date:** 2026-09-02
**Gate:** 10E-3 = READ-ONLY source/code/config investigation of the scheduler metric-collection path.
**Scope:** determine exactly what causes the `/decision` live-metrics latency; identify cacheability; recommend one optimization for 10E-4.
**Result:** 10E-3 COMPLETE. **No production change was made.**

---

## A. Current `/decision` execution flow

Production path (matched against deployed image `…/scheduler:latest` and baseline):

```
orchestrator POST /orchestrate                      (orchestrator/api/routes.py → service.py:46)
  ├─ no metrics snapshot supplied for live path
  └─ SchedulerClient.decide(... edge_url, cloud_url) (orchestrator/clients.py:106-133)
     └─ POST http://scheduler.edgecloud.svc:8002/decision
        body {workload, edge_url, cloud_url}
        └─ api/routes.py:72 decision()
           └─ edge_url present → engine.decide_remote()   (routes.py:87)
              └─ decision_engine.py:62 decide_remote()
                 ├─ await fetch_edge(edge_url)             (decision_engine.py:66)
                 ├─ await fetch_cloud(cloud_url)           (decision_engine.py:67)
                 ├─ await measure_latency_ms(cloud_url)    (decision_engine.py:68)
                 └─ RuleBasedPolicy.decide(edge, cloud, network)  (policies.py:99)
```

The `/decision` endpoint is the exact instrument used by the 10E-2 baseline (`p10_10e_bench.py` posts `{workload, edge_url, cloud_url}` with no metrics → live path).

**Edge path detail:** `edge_url = http://10.0.1.113:9443/edge-ec2-node/edgecloud` → CloudCore Router REST `:9443` → ServiceBus Rule (`service_port: "8000"`) → EdgeCore → edge host `127.0.0.1:8000` (hostPort DNAT bridge) → edge-node pod `/metrics` endpoint. This is the slow hop.

**Cloud path detail:** `cloud_url = http://cloud-node.edgecloud.svc:8001` → ClusterIP service → cloud-node pod.

---

## B. Exact metric calls made per decision

`decide_remote` makes **exactly 3 HTTP GETs, fully sequential**, per live `/decision`:

| # | Call | Function | URL built | Purpose |
|---|------|----------|-----------|---------|
| 1 | `fetch_edge` | metrics_client.py:63 | `<edge_url>/metrics` | Edge `/metrics` via ServiceBus |
| 2 | `fetch_cloud` | metrics_client.py:73 | `<cloud_url>/metrics` | Cloud `/metrics` (ClusterIP) |
| 3 | `measure_latency_ms` | metrics_client.py:83 | `<cloud_url>/health` | Network RTT for policy (latency_ms) |

After that the policy computes the decision from the two metric snapshots + latency. **No Kubernetes API, Prometheus, or node-endpoint calls** — only the two services' own `/metrics` and `/health` REST endpoints. No retries are performed on failure (fail → return `None`).

---

## C. Sequential vs parallel behavior

**Fully sequential.** `decision_engine.py:66-68` awaits each of the three calls in order:

```python
edge = await self._metrics.fetch_edge(edge_url)      # 1 (slowest)
cloud = await self._metrics.fetch_cloud(cloud_url)   # 2
latency_ms = await self._metrics.measure_latency_ms(cloud_url)  # 3
```

There is **no `asyncio.gather`**. Total live-metrics latency ≈ `fetch_edge` + `fetch_cloud` + `measure_latency` (i.e., the ServiceBus edge hop is added whole, serially, before anything else).

Each call opens a **new `httpx.AsyncClient`** (`metrics_client.py:50-52`), so there is no connection reuse/pooling across the three calls either.

---

## D. Connection / retry / timeout behavior

- **Connection management:** `MetricsClient` holds **no persistent client**. Every `_get_json` does `async with httpx.AsyncClient(timeout=…) as client: await client.get(url)` — a fresh connection (TLS/TCP + HTTP) per call, closed on exit. Production passes `transport=None` (test-only injection), so real TCP/TLS per request. This affects call 1 (ServiceBus hop) and calls 2/3 (ClusterIP) alike, but is marginal vs. the ~1 s ServiceBus RTT.
- **Retries:** **none.** On `httpx.HTTPError`/`ValueError`, the call logs a warning and returns `None` (`metrics_client.py:56-58`). No backoff, no retry loop.
- **Timeout:** `MetricsClient(timeout_sec=settings.metrics_timeout_sec)` where `metrics_timeout_sec` default = **2.0 s** (`config.py:68`), clamped to `max(0.5, …)` in `__init__` (`metrics_client.py:36`). Default production has no `SCHEDULER_METRICS_TIMEOUT_SEC` override in `infra/k3s/scheduler-deployment.yaml` (env only sets PORT + LOG_LEVEL), so the default 2.0 s applies.
- **Response handling:** `raise_for_status()` + `resp.json()`; non-JSON/non-2xx → caught → `None`.

---

## E. Measured or established latency contribution (actual measurements vs source inference)

**Actual measurements (from 10E-2 baseline and Phase 9, not inferred):**
- 10E-2 `/decision` live-metrics baseline on deployed `:latest`: **mean 2100.9 / 2201.1 / 2305.8 / 3128.3 ms** (p95 2153.1 / 2306.3 / 2446.5 / 3667.9 ms) at concurrency 1/2/4/8, all HTTP 200.
- Phase 9 §8 (9G): in live-metrics `/orchestrate`, the scheduler's per-request edge/cloud metric collection dominates **≈80–87%** of e2e latency; scheduler ~4.2–4.5 s of the ~5 s total at concurrency in that run (9G used orchestrate-level wall, which includes scheduler decision + inference).

**Phase 9 §5/§6 measurements relevant to the edge hop:**
- edge `/health` via ServiceBus ≈ **21 ms** (9F); edge `/metrics` via ServiceBus ≈ **200 OK** with cpu/ram/disk (9F). Edge `/metrics` similarly flows over the same ServiceBus route.
- Cloud `/metrics` + `/health` hit the ClusterIP service locally → tens-of-ms, far cheaper than the ServiceBus hop.

**Source inference (clearly labeled as inference):**
- Call 1 (edge `/metrics` via ServiceBus) is the dominant term: it traverses orchestrator-process → CloudCore REST `:9443` → ServiceBus → EdgeCore → edge host loopback → pod, and back. Given edge `/health` via the same bus measured ~21 ms at low load, the ~2.1 s baseline cannot be pure latency on a healthy chain — the dominant cost is **very likely the per-request ServiceBus/CloudCore router handling + connection establishment serialization under repeated sequential hits**, not a single sub-50 ms RTT. This is inferred, not individually profiled (no per-call timers in the deployed image). The strength of the 10E-3 conclusion does not depend on this sub-split: the fix (cache) removes most of the repeated edge hop regardless.

**Key established fact (measurement):** the baseline is ~2.1 s at concurrency 1 and rises to ~3.1 s at concurrency 8 — dominated by repeated, sequential, uncached, per-request metric collection, with the ServiceBus edge hop being the largest and most expensive leg.

---

## F. Root-cause hypothesis

The `/decision` live-metrics latency is dominated by **repeated, sequential, uncached metric fetching — primarily the edge `/metrics` ServiceBus round-trip** — plus a fresh HTTP connection per call. Concretely:

1. **Dominant term — edge ServiceBus hop (call 1):** every decision re-fetches edge `/metrics` through the full CloudCore Router REST→ServiceBus→EdgeCore→host→pod chain. It is fetched **first**, serially, so every decision pays the full edge RTT before cloud/latency are even attempted.
2. **No caching:** `MetricsClient` has no cache in the deployed `:latest` image → identical `/metrics` payloads are re-fetched on back-to-back decisions. This is the single cheapest, highest-leverage reduction: edge/cloud resource snapshots change little in ≤1–2 s.
3. **No connection reuse:** a new `httpx.AsyncClient` per call adds setup overhead to each of the 3 calls.
4. **Sequentialization:** the 3 calls run one-after-another (no `gather`), so the edge hop is added whole to every decision.

The policy (`RuleBasedPolicy`, `policies.py`) itself is trivially fast (pure arithmetic on the snapshots) and is **not** a latency factor. Metrics unavailability already yields `ERROR` deterministically — see J below; the fix must not turn healthy decisions into stale/unsafe ones.

---

## G. Candidate optimization options (ranked)

Ranked by expected latency reduction (primary), then implementation complexity / correctness risk / observability / rollback.

### OPTION A — Short-TTL in-memory metrics cache (RECOMMENDED)
- Cache successful edge/cloud `/metrics` payloads keyed by URL with a short TTL (e.g. 1–2 s); **never cache `/health` latency** (always live so the policy's network measurement stays honest).
- **Latency reduction:** high — within the TTL window, repeated decisions skip the dominant edge ServiceBus hop entirely, collapsing `/decision` from ~2.1 s toward ~cloud+latency cost (tens of ms) for back-to-back requests.
- **Complexity:** low — ~15 lines in `MetricsClient._get_json` + one config knob.
- **Correctness risk:** low — caches only **successful** payloads; failed fetches return `None` as today (→ `ERROR` unchanged). Stale-but-fresh (≤TTL) snapshots are equivalent to the scheduler receiving that snapshot. Latency is never cached. Selecting a target from a ≤1–2 s old valid snapshot is safe and is precisely the semantics the policy already accepts (it trusts whatever snapshot is passed).
- **Observability:** add an `age` field / log on cache hit so staleness is visible; bounded dict + expiry naturally caps memory.
- **Rollback:** set `SCHEDULER_METRICS_TTL_SEC=0` (default) → cached disabled, behavior identical to `:latest`. Trivial.

### OPTION B — Concurrent edge/cloud/latency fetch (`asyncio.gather`)
- Fire call 1 (edge) and calls 2+3 (cloud metrics + latency) concurrently instead of serially.
- **Latency reduction:** medium — overlaps the (fast) cloud/latency calls underneath the (slow) edge hop instead of adding them serially; saves the cloud+latency term (~50–100 ms) not the edge term. The edge hop still dominates.
- **Complexity:** low–medium. **Correctness risk:** unchanged (same data, same input to policy). **Observability:** unchanged. **Rollback:** revert to sequential. On its own it leaves the dominant edge hop intact → smaller win than A.

### OPTION C — HTTP connection reuse (persistent `AsyncClient` on `MetricsClient`)
- Keep a single `httpx.AsyncClient` alive so the 3 calls (and repeated decisions) reuse pooled connections to the same hosts.
- **Latency reduction:** low–medium — removes per-call connection setup; helps the ClusterIP calls most; the ServiceBus hop's router+edge work is not removed (still one edge round-trip per decision).
- **Complexity:** low. **Correctness risk:** low. **Observability:** unchanged. **Rollback:** trivial. Compatible with both A and B as an additive complement, but alone gives the least reduction.

### OPTION D — Request coalescing / shared inflight de-duplication
- While a fetch for URL X is in flight, concurrent requests for X await the same in-flight future instead of duplicating the call.
- **Latency reduction:** medium at high concurrency (removes redundant parallel edge hops) but **zero at concurrency 1** — the baseline's concurrency-1 worst case is untouched. Raises complexity substantially (task registry, cancellation, error propagation).
- **Complexity:** high. **Correctness risk:** medium. **Observability:** low. **Rollback:** revert. Not worthwhile vs A given A also helps at concurrency 1.

### OPTION E — Reduce metric samples / relax probing
- E.g. skip one of the 3 calls or loosen the timeout. **Rejected:** removing `measure_latency_ms` would change policy inputs (latency drives the CLOUD-offload branch and the "poor network" reason); removing `fetch_cloud` would break the both-saturated/`cloud is None` checks. This changes scheduling correctness — prohibited by the 10E mandate ("Do NOT change scheduling semantics"). Not considered.

---

## H. Recommended optimization for 10E-4

**OPTION A — short-TTL, bounded, in-memory metrics cache, metrics-only, latency always live.**

- Cache edge `/metrics` and cloud `/metrics` successful payloads by URL for a short TTL (start **1 s**, upper bound 2 s), driven by a single config knob `SCHEDULER_METRICS_TTL_SEC` (0 = disabled, matching default).
- **Never** cache `/health` latency (`measure_latency_ms` always `use_cache=False`) so the policy's network measurement and the offload/poor-network branches stay honest.
- Cache **only non-None payloads**; a failed fetch still returns `None` → policy `ERROR` path unchanged (no stale-metric-as-available hazard).
- TTL is short and finite → no infinite stale reuse; entry expires and is refetched; bounded dict (one entry per URL) → bounded memory; deterministic.
- Does **not** modify `RuleBasedPolicy` thresholds or any scheduling semantics — it only supplies fresher/same input snapshots to the unchanged policy.
- Rollback = `SCHEDULER_METRICS_TTL_SEC=0` (the default) → behavior identical to `:latest`.

This yields the biggest reduction for the lowest risk and the cleanest rollback, and it addresses the concurrency-1 worst case (unlike D).

(Note: OPTION A is already implemented locally in `scheduler/metrics_client.py` (ttl_sec / `_cache` / `use_cache`), `scheduler/config.py` (`metrics_ttl_sec`), and `scheduler/decision_engine.py` (passes `ttl_sec=settings.metrics_ttl_sec`), with 4 unit tests in `scheduler/tests/test_metrics_client.py` passing (54 total). This is the **candidate** to validate+deploy in 10E-4 onward — it is NOT yet deployed; the cluster still runs `:latest`.)

---

## I. Exact files/functions that would need modification (for OPTION A)

1. `scheduler/metrics_client.py`
   - `MetricsClient.__init__` — add `ttl_sec: float = 0.0` ctor param; init `self._cache: dict[str, tuple[float, Optional[dict]]]` and `self._ttl`.
   - `_get_json(url, use_cache=True)` — serve repeats within TTL; cache only non-None payloads. [Locally done]
   - `fetch_edge` / `fetch_cloud` — use the cache (default `use_cache=True`). [Locally done]
   - `measure_latency_ms` — call `_get_json(..., use_cache=False)` (latency always live). [Locally done]
2. `scheduler/config.py` — add `metrics_ttl_sec: float = 0.0` (env `SCHEDULER_METRICS_TTL_SEC`). [Locally done]
3. `scheduler/decision_engine.py` — pass `ttl_sec=settings.metrics_ttl_sec` when constructing `MetricsClient` (`decision_engine.py:35-38`). [Locally done]
4. `scheduler/tests/test_metrics_client.py` — TTL unit tests (repeat-serve, ttl=0 always-fetch, latency-not-cached, expiry). [Locally done]

No change needed to: `scheduler/policies.py` (thresholds untouched), `scheduler/api/routes.py`, `scheduler/models.py`, `orchestrator/*`, `infra/k3s/*` (deployment/manifests — except adding the new env var `SCHEDULER_METRICS_TTL_SEC` at deploy time via `kubectl set env`/patch, which is a deploy-time config, not an app-code/semantics change).

---

## J. Explicit statement

**No production change was made during 10E-3.**

- Nothing was deployed, built, pushed, or restarted.
- Kubernetes (Deployment / Services / Rules / RuleEndpoints), CloudCore, EdgeCore, orchestrator code, scheduler production config, Terraform, IAM, Security Groups, ECR, and hostPort were **NOT modified**.
- No cache was introduced into the running scheduler; no measurements were invented — all numbers are from the recorded 10E-2 baseline (measured) and the Phase 9 report (measured).
- The candidate OPTION A code exists **only locally** (uncommitted, untracked; the repo's git ignores are broken so the whole tree is untracked) and is **not deployed** — the cluster still runs `…/scheduler:latest`, consistent with the baseline.

10E-3 STATUS: COMPLETE
File: docs/phase10/10E/10E-3_investigation.md
Production changes: NONE
Next gate: 10E-4

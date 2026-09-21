# Gate 10E-6 — Scheduler Metrics-Collection Investigation (READ-ONLY)

**Date:** 2026-09-02
**Gate:** 10E-6 = investigate the scheduler metrics-collection architecture and identify the NEXT evidence-backed optimization. **Do NOT implement, deploy, or change production.**
**Result:** INVESTIGATION COMPLETE. **NO production change made; NO implementation started; NO benchmark of a new image run.** All findings are from the deployed code in this repo and controlled **read-only** timing probes from the orchestrator pod.

---

## A. 10E-5 result summary

10E-5 deployed the 10E-4 metrics-only short-TTL cache (`scheduler:10e-4`, `SCHEDULER_METRICS_TTL_SEC=1.0`), pinned to the cloud control-plane node after placement remediation. Functional gate **14/14 PASS**; regression clean; benchmark (1/2/4/8 × 12, all HTTP 200, exact 10E-2 methodology):

| Concurrency | 10E-5 mean | 10E-5 p95 | 10E-2 mean | 10E-2 p95 |
|-------------|-----------|-----------|-----------|-----------|
| 1 | 2081.7 | 2144.5 | 2100.9 | 2153.1 |
| 2 | 2188.0 | 2205.2 | 2201.1 | 2306.3 |
| 4 | 2378.6 | 2475.9 | 2305.8 | 2446.5 |
| 8 | 2757.9 | 2964.4 | 3128.3 | 3667.9 |

**Verdict: PASS WITH LIMITATION.** No systematic, reproducible performance improvement. Sequential cache probe: cold ~2070 ms, immediate ~2056/2165/2080 ms, after-4s-idle ~2052 ms — no within-TTL speedup. Stated reason at the time: TTL (1 s) shorter than the ~2 s serial collection path, so entries expire before reuse. **This 10E-6 investigation identifies a deeper, previously-unmeasured cause (section C/D).** 10E-5 is NOT reinterpreted as a performance success.

---

## B. Current scheduler metrics-collection flow

Two scheduler entry points (`scheduler/api/routes.py`):

- `POST /decision` with `edge_metrics`/`cloud_metrics`/`network_metrics` → **offline/deterministic** (`engine.decide`, no network).
- `POST /decision` with `edge_url`/`cloud_url` → **live path** (`engine.decide_remote`): the scheduler itself fetches live metrics + latency, then applies the policy. This is the 10E instrument (10E-2/10E-5 both exercised it).

Live path (`scheduler/decision_engine.py:62-72`) is **fully sequential** — three awaited awaits, each opening a **fresh `httpx.AsyncClient`**:

```
decide_remote(workload, edge_url, cloud_url)
  1  edge    = await metrics.fetch_edge(edge_url)         # GET <edge>/metrics
  2  cloud   = await metrics.fetch_cloud(cloud_url)       # GET <cloud>/metrics
  3  latency = await metrics.measure_latency_ms(cloud_url)# GET <cloud>/health
  → RuleBasedPolicy.decide(edge, cloud, network(latency))
```

`decision_engine.py:66-68` (no `asyncio.gather`):
```python
edge = await self._metrics.fetch_edge(edge_url)
cloud = await self._metrics.fetch_cloud(cloud_url)
latency_ms = await self._metrics.measure_latency_ms(cloud_url)
```

Edge hop is via ServiceBus (`http://10.0.1.113:9443/edge-ec2-node/edgecloud/metrics`); cloud hop via ClusterIP (`http://cloud-node.edgecloud.svc:8001/metrics`); `<cloud>/health` via ClusterIP.

---

## C. Exact metric/health calls

| # | Call | Function | URL | purpose |
|---|------|----------|-----|---------|
| 1 | `fetch_edge` | metrics_client.py:125 | `<edge>/metrics` | edge snapshot |
| 2 | `fetch_cloud` | metrics_client.py:135 | `<cloud>/metrics` | cloud snapshot |
| 3 | `measure_latency_ms` | metrics_client.py:145 | `<cloud>/health` | network RTT for policy latency_ms |

Policy (`scheduler/policies.py:99`) consumes all three: `edge`/`cloud` snapshots (required, else ERROR) and `network.latency_ms` (drives the CLOUD-offload and poor-network branches; `latency_ok = latency_ms <= max_latency_ms`; default 200 ms). Each `_get_json` opens a fresh `httpx.AsyncClient` (`metrics_client.py:75-77`); no persistent pool; timeout 2.0 s (`metrics_timeout_sec`); no retries.

---

## D. Timing contribution of each call — **measured (read-only) and decisive**

Controlled probes from the orchestrator pod (8 rounds, warmed), same consumer path as 10E-5:

| Call | mean | median | p95 |
|------|------|--------|-----|
| edge `/metrics` (ServiceBus) | **1008.4 ms** | 1008.2 | 1008.8 |
| cloud `/metrics` (ClusterIP) | **1004.9 ms** | 1004.3 | 1005.2 |
| cloud `/health` (ClusterIP) | **2.5 ms** | 2.5 | 2.6 |
| scheduler `/decision` total | **2078.5 ms** | 2054.5 | 2062.0 |

`/decision` ≈ edge(1008) + cloud(1005) + health(2.5) + policy/overhead ≈ 2078 ms.

**Key discovery — the ~1 s per `/metrics` is SERVER-SIDE CPU sampling, not network.** Both edge and cloud `/metrics` handlers call `MetricsCollector.collect()` (`edge/monitoring/metrics.py:39`, `cloud/monitoring/metrics.py:40`):

```python
cpu = psutil.cpu_percent(interval=self._interval)   # _interval defaults to 1.0 s
```

`psutil.cpu_percent(interval=1.0)` **blocks ~1 s** by design (it samples a CPU delta). `MetricsCollector` is constructed as `MetricsCollector(settings.monitor_interval_sec)` (`cloud/api/app.py`, `edge/api/app.py`), and `monitor_interval_sec` defaults to **1.0** with **no env override set on the deployed pods** (verified: `cloud-node` env has no MONITOR override → default 1.0). Evidence it is sampling, not latency:

- **cloud `/metrics` via ClusterIP is ~1005 ms** — ClusterIP in the same pod network has near-zero RTT, yet still ~1 s, so the 1 s cannot be network.
- **cloud `/health` via ClusterIP is only 2.5 ms** — a genuine network RTT with no psutil sampling is fast, proving the network path is NOT the bottleneck.
- edge `/metrics` (~1008 ms) matches the same ~1 s sample + small overhead.

**Implication:** the ~2 s `/decision` is dominated by **two forced ~1 s server-side CPU samples** (edge + cloud). A client-side cache/connection/ordering change cannot remove the first ~1 s + ~1 s that every metrics refetch pays at the server. This is why the 10E-4/10E-5 TTL cache produced no measurable gain — it was attacking the wrong layer (repeat-client fetch) when the dominant cost is a fresh, serial, ~1 s sample on each side.

**Measurement limitation (declared):** the deployed scheduler has **no per-call timing instrumentation**. Rather than add it (a source change, prohibited this gate), I attributed timing via external read-only probes + source inspection. This limitation does not affect the conclusion (the ~1 s server sample is proven by near-zero network yet ~1 s total on the ClusterIP cloud `/metrics`, plus direct source inspection).

---

## E. Sequential/parallel dependency analysis

- Are the calls truly sequential? **Yes** — `decide_remote` awaits edge, then cloud, then health in order (no `gather`).
- Which depend on which? **None.** `edge`, `cloud`, and `health` are three independent HTTP GETs with no data flow between them. They are consumed together only by the policy at the end.
- Can edge `/metrics` and cloud `/metrics` run concurrently? **Yes, safely** — different URLs, independent results, both feed the final policy formula (commutative inputs). Under `asyncio.gather` on the single uvicorn event loop, the two ~1 s server samples overlap → collection ~1 s instead of ~2 s (a measured ~47% reduction).
- Can cloud `/health` run concurrently? **Yes** — it is independent (`use_cache=False`, its own URL/measurement); overlapping it underneath the metrics is safe and saves its ~2.5 ms.
- Does policy require the health result before metrics collection? **No.** The policy is a pure function of the three collected inputs (policies.py:99); it is only evaluated after all are fetched. No branch depends on arrival order.
- Would parallelization change scheduling semantics? **No.** Same inputs, same snapshot values, same deterministic rule output. Only the *order/when* of arrival changes, not the values or the decision.
- Shared mutable state making parallelization unsafe? **No.** `_cache` and `_inflight` dicts are read/written synchronously before the first `await` in `_get_json` (marker placed before `_do_fetch`'s first await); under a single event loop there is no torn state. The three calls use different URLs, and single-flight coalesces same-URL misses regardless of caller concurrency. Already proven by 10E-4 unit tests (8 concurrent misses → 1 network call; latency never coalesced).

**Conclusion:** parallelizing the three independent calls is safe and would overlap the two dominant ~1 s samples.

---

## F. HTTP connection lifecycle analysis

- Why a fresh `httpx.AsyncClient` per request? `_get_json`/`_do_fetch` do `async with httpx.AsyncClient(timeout=…) as c: c.get(url)` (`metrics_client.py:75-78`) — a new client (new TCP/TLS + HTTP) per call, closed on exit. Orchestrator clients do the same (`orchestrator/clients.py:48`).
- Can a persistent client be reused? **Technically yes**, but **it is NOT the bottleneck here.** Measured network RTT (cloud `/health`) is 2.5 ms; the ~1 s is server-side sampling. Connection setup would save a few ms per call at most (order 0.1–0.3% of the 2 s path) — see section J ranking.
- Connection pooling / keep-alive: irrelevant to the dominant cost. ServiceBus/CloudCore is HTTP without TLS (`:9443`); CloudCore/EdgeCore reuse is safe but saves little.
- Timeouts: `metrics_timeout_sec=2.0` (> the ~1 s sample, so no spurious timeouts). Connection limits: none configured (fresh client each call). Keep-alive: no persistent client to keep alive.
- **Conclusion:** connection reuse is a real but negligible lever; it does not address the ~1 s samples.

---

## G. `/health` necessity analysis

- Why called on every decision? It provides the **network-latency input** to the policy (the `latency_ms` that drives the CLOUD-offload eligibility and poor-network branches; also reported in the decision reason).
- Does its result affect the decision? **Yes, materially** — `latency_ok` gates the `cloud_ok and latency_ok → CLOUD` branch (policies.py:181) and feeds the poor-network HIGH/medium(-queued) branches. Example from 9B/9F reasons: "…and network latency 12–13 ms ≤ 200 ms".
- Does it duplicate `/metrics`? **No** — `/metrics` returns CPU/RAM/disk; `/health` returns liveness + (implicitly) is timed as an RTT. They are different signals.
- Would reducing its frequency alter correctness? **Yes, if cached** — a stale latency could mis-gate the offload branch. It is correctly **never cached** (`use_cache=False`, metrics_client.py:149, test `test_latency_measurement_never_coalesced`).
- Is it safe to cache separately? **No** for decision correctness — latency is the one input that MUST be fresh for the network-gated branch. Keep it live.
- Is it the bottleneck? **No** — it is 2.5 ms. **Do not remove it** (mandate: "Do NOT remove it"); it is cheap and semantically required. No `gather`-style change should cache or skip it, only overlap it under the metrics.

**Conclusion:** `/health` must remain a live per-decision measurement; at 2.5 ms it is negligible and is not a lever to reduce.

---

## H. Cache freshness analysis

Reviewing the 10E-4/10E-5 cache (`metrics_only` TTL, by URL):

- Current behavior: `ttl=1.0`, caches successful `/metrics` payloads (<edge>/metrics, <cloud>/metrics) by URL; hits within TTL skip the network; latency always live; failures not cached; `MAX_METRICS_TTL_SEC=60.0`.
- Would a longer TTL help? **Mathematically, a longer TTL does help repeated/back-to-back decisions** — a TTL ≥ the ~1 s sample latency (e.g. 5–10 s) would let a second decision within the window skip the refetch and drop toward cloud+health (~10 ms). **But:** (1) it does NOT help the concurrency-1 cold/expired case, which is the baseline's worst case and is unaffected regardless of TTL; (2) it increases staleness and the freshness/staleness trade-off; (3) 10E-5 already demonstrated the 1 s TTL is ineffective, and the mandate says do NOT recommend raising TTL merely because 1 s failed.
- What freshness is required? The policy trusts whatever snapshot is passed (it has no age gate). Stale risk: serving an old snapshot that understates edge pressure could pick EDGE when the edge is actually overloaded (a bad placement). The current design bounds this with finite TTL.
- Is 1 s unnecessarily short? Relative to the fetch latency, yes (it's shorter than one fetch, so it can't even serve a single miss). But the deeper issue — that each fetch itself costs ~1 s server-side — is untouched by TTL.
- Engineering justification for 2 s/5 s/…: A longer TTL would make back-to-back decisions fast and is internally safe (payloads are monotonic-ish resource snapshots; MaxTTL 60 s caps staleness). It is a *valid* tuning lever **for repeated requests**, but it does not address the *cold-path* serial sampling cost. The recommendation below targets the cold path too.

**Conclusion:** TTL tuning is legitimate for repeat-hit workloads but is not the primary fix; the same cold-path ~1 s + ~1 s serial sampling cost remains.

---

## I. Single-flight effectiveness analysis

- Current mechanism: `_Inflight` anyio.Event coalesces concurrent cache **misses for the SAME URL**; first caller fetches, others await the shared payload (`metrics_client.py:57-120`). Unit-tested: 8 concurrent cold callers → exactly 1 network call (`test_concurrent_misses_are_coalesced_single_flight`).
- Is it useful under realistic concurrency? **Yes** — under concurrent `/decision` load, same-URL misses (edge, or cloud) each collapse to one fetch. It directly reduces ServiceBus/CloudCore load (fewer duplicate edge hops) and call-fanout. This is complementary to parallelization: `gather` overlaps edge+cloud within a decision; single-flight coalesces edge-vs-edge and cloud-vs-cloud across decisions.
- Does it change correctness? **No** — every waiter still receives the same fresh-or-cached payload the owner resolved; latency is never coalesced.
- Race safety: the marker is placed synchronously before the first `await`; under one event loop there is no torn state (verified by 10E-4 cross-backend tests).
- Caveat: combined with a short TTL, single-flight only aids overlapping misses; it does not remove the underlying ~1 s server sample. It remains correct and desirable to keep.

**Conclusion:** single-flight is sound, useful under concurrency, and safe to keep; it is orthogonal to the bottleneck.

---

## J. Candidate optimizations (ranked)

Scores: latency reduction (L), implementation complexity (C, lower=better), correctness risk (R, lower=better), scheduler-policy impact (P, lower=better), observability impact (O, lower=better), rollback simplicity (Rb, lower=better). 1=best.

### 1. Option PA — Parallelize the 3 independent metric/health fetches (`asyncio.gather`)
- **L: HIGH (best)** — overlaps edge+cloud ~1 s samples → collection ~2 s → ~1 s (~47% of `/decision`). Reduces EVERY decision, including the concurrency-1 cold case.
- **C: LOW** — wrap the three awaits in `asyncio.gather` in `decide_remote`; ~5 lines + tests.
- **R: LOW** — independent calls, no shared mutable state, same policy inputs, no semantics change.
- **P: NONE** — identical snapshots & latency to the unchanged policy.
- **O: NONE** — no schema/log change.
- **Rb: TRIVIAL** — revert to sequential awaits.
- Evidence: measured 1008 + 1005 ms independent calls (D); dependency analysis (E) shows safety.

### 2. Option SR — Reduce server-side metric sampling interval (`monitor_interval_sec`, `psutil.cpu_percent(interval=…)`)
- **L: HIGH (best ceiling)** — cuts each `/metrics` server block from ~1 s toward ~0.05 s; combined with serial flow → ~0.1–0.2 s collection.
- **C: MEDIUM-HIGH** — touches `cloud/node` and `edge/node` images (rebuild + redeploy), not just the scheduler; `MetricsCollector` already accepts the interval but the *metric semantics* (CPU sample accuracy) change, and response representation of `cpu_percent` becomes a short-interval estimate.
- **R: MEDIUM** — changes what `/metrics` reports on both nodes (monitoring/dashboard semantics); must confirm CPU readings stay meaningful at small intervals (psutil supports ≥ 0.05).
- **P: NONE** (same policy inputs; just fresher/faster snapshots).
- **O: MEDIUM** — affects node monitoring semantics cluster-wide.
- **Rb: MEDIUM** — requires image rollback on two services.
- Evidence: root-cause is the ~1 s psutil sample (D + source). **Explicit scope note:** this is a *cloud/edge-node* change, outside the scheduler-optimization lever the 10E phase targets, and is flagged as a follow-up to evaluate separately.

### 3. Option TTL — Increase `SCHEDULER_METRICS_TTL_SEC` (e.g. 5–10 s)
- **L: LOW-MEDIUM** — helps only back-to-back/repeat decisions; zero help on the concurrency-1 cold/expired path (the baseline's worst case); 10E-5 already showed 1 s is ineffective.
- **C: LOW** (env-only). **R: LOW-MEDIUM** (staleness). **P: LOW** (stale snapshot could mask edge overload). **O: NONE. Rb: TRIVIAL.**
- Evidence: 10E-5 mixed-sign/noise deltas; H analysis. Mandate says do not choose solely because 1 s failed.

### 4. Option CR — Persistent `httpx.AsyncClient` connection reuse
- **L: LOW** — measured network RTT is 2.5 ms; saves only setup overhead (≤ a few ms), ~0.1–0.3% of the path.
- **C: LOW. R: LOW. P: NONE. O: NONE. Rb: TRIVIAL.**
- Evidence: F measurement (network is not the bottleneck).

### 5. Option OH — Reduce/remove `/health` frequency
- **L: NEGLIGIBLE** (2.5 ms) and **correctness-risky** (latency gates the offload branch). **Rejected** — must stay live (G; mandate "do NOT remove").

### 6. Option SF — Rework single-flight
- No change warranted — it is already correct and useful under concurrency (I).

---

## K. Recommended optimization for the next implementation gate

**Option PA — parallelize the three independent metric/latency fetches in the live decision path with `asyncio.gather`.**

Concretely, in `scheduler/decision_engine.py`, `decide_remote` would collect the three dependent-but-independent calls concurrently:

```python
async def decide_remote(self, workload, edge_url, cloud_url):
    edge, cloud, latency_ms = await asyncio.gather(
        self._metrics.fetch_edge(edge_url),
        self._metrics.fetch_cloud(cloud_url),
        self._metrics.measure_latency_ms(cloud_url),
    )
    network = NetworkMetrics(latency_ms=latency_ms) if latency_ms is not None else None
    return self.decide(workload, edge, cloud, network)
```

Rationale (evidence-backed): the live `/decision` path is dominated by **two independent ~1 s server-side CPU samples** (edge `/metrics` 1008 ms + cloud `/metrics` 1005 ms, measured D). They are provably independent (E), so running them concurrently overlaps the two ~1 s samples, cutting the collection path from ~2 s to ~1 s (≈ **~47%** of `/decision`) on *every* decision — including concurrency 1, the case the 10E-4/10E-5 TTL cache could not improve. It changes only *when* the same inputs arrive, not what the policy sees (P=unaffected). It is a pure scheduler change (no cloud/edge rebuild), ~5 lines + tests, trivially reversible.

---

## L. Why parallelization is preferable to simply increasing TTL

1. **It attacks the measured bottleneck, not the symptom.** The bottleneck is the serial ~1 s + ~1 s server sampling (D). Parallelization reduces that *serial path itself* for every decision. Raising TTL only avoids *repeating* refresh; it still pays the full serial ~2 s on the cold/expired path and does nothing for concurrency 1.
2. **It helps the worst case.** 10E-5's cache could not touch the concurrency-1 cold decision. Parallelization gives a real, reproducible ~47% cut there (mixed-sign noise becomes a systematic reduction).
3. **No staleness trade-off.** A higher TTL trades freshness for speed (H). Parallelization keeps identical fresh snapshots and the always-live latency — zero staleness cost, zero scheduling-semantics change.
4. **No impact overlap / same mechanism.** It composes with the existing cache, single-flight, and always-live latency rather than depending on any one of them.
5. **Clean, low-risk, reversible.** A small, pure-scheduler change vs. an env change that (alone) demonstrably did not move the needle in 10E-5.

---

## M. Exact source files/functions that would change (for Option PA)

1. `scheduler/decision_engine.py`
   - `DecisionEngine.decide_remote(...)` — replace the three sequential awaits (lines 66–68) with `asyncio.gather(...)` on the same three calls; add `import asyncio`. **No signature/schema change.**
2. `scheduler/tests/test_decision_engine.py`
   - Add/update a test asserting `decide_remote` fetches edge+cloud+latency concurrently (all three complete, policy unchanged). A dedicated `MetricsClient` with a `MockTransport` recording call overlap proves concurrency.
3. **No change** to `scheduler/metrics_client.py` (fetch methods already independent and thread/loop-safe via single-flight + cache), `scheduler/policies.py`, `scheduler/models.py`, `scheduler/api/routes.py`, `scheduler/config.py`, `orchestrator/*`, or any `cloud/`/`edge/` file.

(The deeper server-side lever, `monitor_interval_sec`/`psutil.cpu_percent(interval=…)` in `edge/monitoring/metrics.py` and `cloud/monitoring/metrics.py` + their app wiring, is a **separate, explicitly out-of-scope-for-this-recommendation** cloud/edge change to consider in a later gate.)

---

## N. Test plan that would prove the optimization works

1. **Unit (local, no cluster):** new `test_decision_engine.py` case — `MetricsClient` with `httpx.MockTransport` whose handler sleeps ~50 ms and tags the active URL; assert that during a single `decide_remote`, edge and cloud fetches overlap in wall time (i.e. total ≈ one sleep, not two) — proving concurrency. Reuse the existing `asyncio`/`anyio` backends.
2. **Unit correctness:** with overlapping fetches, `decide_remote` still returns the same `Decision` (target/score/reason) as the sequential version for identical snapshots (edge-healthy→EDGE, edge-overload+latency-ok→CLOUD, poor-network medium→QUEUE, both-saturated→ERROR). No regression.
3. **Unit single-flight/cache interplay:** concurrent `decide_remote` calls still coalesce same-URL misses to one network call; health latency never cached/coalesced. (Existing `test_metrics_client.py` covers the client; add an engine-level concurrency check.)
4. **Integration (dev image, not production):** run scheduler `:10e-4` (or a locally built PA variant) against the same fake-detector harness as the existing scheduler tests to confirm `/decision` 200 + unchanged schema keys.
5. **Functional gate (if/when production-approved, per later gate discipline):** re-run the 14-check 10E-5 functional gate unchanged — must still 14/14 PASS.

---

## O. Production benchmark plan (for the implementation gate, NOT run here)

Methodology identical to 10E-2/10E-5 for an apples-to-apples comparison (from orchestration pod → `POST http://scheduler.edgecloud.svc:8002/decision`, body `{"workload":{"workload_id":"bench10e","latency_requirement_ms":100.0,"priority":"medium"}, "edge_url", "cloud_url"}`, concurrency 1/2/4/8 × 12, httpx AsyncClient with Semaphore):

- Primary instrument: **`/decision`** (the cache/collection-relevant path), mean/median/min/max/p95 per concurrency.
- Compare **PA-parallel vs the 10E-5 (parallel-serial, TTL=1) numbers**: expect mean c1 ≈ ~1050–1300 ms vs the 2081.7 ms serial, i.e. a clear, reproducible reduction at every level (not mixed-sign noise).
- Separately record **`/orchestrate`** end-to-end (decision + forwarding + inference) to confirm the ~1 s decision cut is visible end-to-end without regressing inference.
- Record decision behavior (target/edge/cloud/fallback/errors) — must be identical to serial.
- A **cold-vs-warm** probe: PA helps cold decisions too (the key differentiator versus TTL).
- Keep `/decision` and `/orchestrate` results separate in the report; benchmark a new image **only** in a dedicated production-approved gate (10E-7+), not here.

---

## P. No production changes made

**Strictly READ-ONLY during 10E-6.** I did NOT modify/patch/apply/set-image/change-env any Kubernetes object (Deployments incl. scheduler/cloud-node/orchestrator/edge-node, Services, Rules, RuleEndpoints, nodeSelectors, taints/cordon), did NOT restart any pod, did NOT modify or deploy any image (scheduler/cloud/edge remain at their 10E-5 state — scheduler `:10e-4`, `SCHEDULER_METRICS_TTL_SEC=1.0`), did NOT modify CloudCore/EdgeCore/ServiceBus, Terraform, IAM, Security Groups, or ECR, and did NOT uncordon wsl2. All cluster operations were `kubectl get`-style reads plus the same read-only HTTP timing probes used in prior gates (from the orchestrator pod). The scheduler `:10e-4` TTL cache image is still deployed (unchanged) — no new image was built, pushed, or benchmarked. **No benchmark of a new production image was run.**

---

10E-6 INVESTIGATION STATUS: COMPLETE
File: docs/phase10/10E/10E-6_investigation.md
Production changes: NONE
Implementation: NOT STARTED
Deployment: NOT STARTED
Benchmark: NOT RUN
Next action: REVIEW 10E-6 INVESTIGATION

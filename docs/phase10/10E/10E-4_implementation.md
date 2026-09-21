# Gate 10E-4 — Live-Metrics Scheduling: Implementation & Local Validation

**Date:** 2026-09-02
**Gate:** 10E-4 = implement + locally validate the recommended bounded short-TTL metrics-only cache.
**Result:** 10E-4 COMPLETE. **No production change / deployment made.**

---

## A. Exact files modified

| File | Change |
|------|--------|
| `scheduler/metrics_client.py` | Added bounded TTL cache + single-flight coalescing in `MetricsClient`; extracted `_do_fetch`; added `_Inflight` helper; module constant `MAX_METRICS_TTL_SEC`. |
| `scheduler/tests/test_metrics_client.py` | Added 4 focused tests (failure-not-poisoning, concurrent-single-flight, TTL-bound, latency-never-coalesced). |

`config.py` and `decision_engine.py` already carried the cache wiring from the earlier local candidate (`config.py:73` `metrics_ttl_sec: float = 0.0` with env `SCHEDULER_METRICS_TTL_SEC`; `decision_engine.py:35-38` constructs `MetricsClient(ttl_sec=settings.metrics_ttl_sec)`). Their content was confirmed unchanged and consistent; no further edits were required.

---

## B. Exact cache behavior

Keyed by **URL** (per endpoint), in-memory, process-local, single metrics snapshot per URL.

- **Hit:** within TTL window → return cached payload, no network call (debug log `metrics cache hit`).
- **Miss / expired (with cache enabled):** single-flight coalescing — the first concurrent caller performs the fetch; any other concurrent callers for the same URL `await` a shared `anyio.Event` and read the same resolved payload (debug log `metrics cache wait (in-flight)` / `store`).
- **Stored:** only on successful fetch (payload not `None`), with expiry timestamp `now + effective_ttl`.
- **Failure:** payload `None` → **not stored**; callers receive `None` (scheduler's existing "metrics unavailable" → policy `ERROR` path), and a subsequent request performs a fresh fetch (debug log `metrics cache failure (not stored)`).
- **Expiry:** `time.monotonic()` compared against the stored expiry; expired entries are not returned and trigger a refetch. Dict is bounded to one entry per URL (2 URLs: edge metrics, cloud metrics) and entries are naturally replaced/expired, so memory is bounded.
- **Default / disabled:** `ttl_sec == 0.0` (or `SCHEDULER_METRICS_TTL_SEC=0`) → cache and coalescing are skipped entirely; behavior is byte-for-byte the original `async with httpx.AsyncClient(...) ... get(url)` path.

---

## C. Configuration

- Env var: **`SCHEDULER_METRICS_TTL_SEC`** (via `SchedulerSettings.metrics_ttl_sec`, `config.py`).
- **Default:** `0.0` (metrics `metrics_ttl_sec: float = 0.0`).
- **Disabled behavior (`0`):** cache disabled → every `/metrics` fetch is live; single-flight also bypassed; identical behavior to the pre-change `:latest` scheduler. Latency is always live regardless.

---

## D. What is cached

- **Edge `/metrics`** payload (via ServiceBus), keyed `<edge_url>/metrics`.
- **Cloud `/metrics`** payload, keyed `<cloud_url>/metrics`.

Only the parsed JSON metric snapshots consumed by `fetch_edge`/`fetch_cloud` are cached. TTL operating range: `(0, 60.0]` seconds (see F bound); intended/live config for 10E-6 will be small (2.0 s per the project plan).

---

## E. What remains live

- **Latency measurement:** `measure_latency_ms` always calls `_get_json(..., use_cache=False)` (`metrics_client.py:149`) → `GET <cloud_url>/health` is **never cached and never coalesced**; it is a genuine fresh network round-trip every decision, so the policy's network-latency input (and the CLOUD-offload / poor-network branches) stays honest.

---

## F. Concurrency-safety mechanism

- **Single-flight coalescing** via a backend-agnostic `_Inflight` marker (anyio `Event` + shared `payload`). On a miss, `self._inflight[url]` is set **synchronously before the fetch's first `await`**, so concurrent callers observe the marker and await the same in-flight fetch instead of firing one request each → **no uncontrolled request stampede**. Verified by test: 8 concurrent cold callers → exactly 1 network call.
- **Cache dict** (`self._cache`) is read/written only around synchronous dict ops and the network `await` happens after the marker is placed; under a single event loop (asyncio/trio) the check-and-mark is atomic, so no torn state. Memory bounded (one entry per URL).
- **Latency** is deliberately excluded from coalescing so concurrent latency probes each produce their own measurement (verified by test: 4 concurrent latency probes → 4 network calls).

---

## G. Failure / expiry behavior

- **Fetch failure:** `_do_fetch` catches `httpx.HTTPError`/`ValueError` → returns `None`; the cache is **not** poisoned; in-flight waiters receive `None`; the `_inflight` marker is released; the next caller does a fresh fetch. A failure therefore never blocks a fresh request and never serves a stale value as if fresh.
- **Expiry:** entries older than the effective TTL are treated as misses and refetched. `time.monotonic()` guarantees monotonic expiry even across clock adjustments.
- **TTL bound:** `self._ttl = min(MAX_METRICS_TTL_SEC, max(0.0, float(ttl_sec)))` with `MAX_METRICS_TTL_SEC = 60.0` — explicitly bounded both below (≥0) and above (≤60 s), so a misconfiguration cannot create negative or unbounded staleness.
- **No infinite stale reuse:** expiry is always finite (≤60 s); a cached value is never served past its TTL.

---

## H. Tests executed and exact results

Command: `python -m pytest scheduler/tests -q` from repo root.

**Result: `62 passed, 1 warning in ~1.7s`** (warning is the unrelated pre-existing Starlette `httpx` deprecation; no failures).

Existing 50 + new tests, per the 10E-4 focused checklist:

| # | Requirement | Test(s) | Result |
|---|-------------|---------|--------|
| 1 | TTL=0 disables caching | `test_ttl_disabled_fetches_every_time` | PASS |
| 2 | First request is a cache miss | `test_ttl_cache_serves_repeated_metrics_fetches` (n→1 on first) | PASS |
| 3 | Second request within TTL uses cached metrics | `test_ttl_cache_serves_repeated_metrics_fetches` (still 1 call) | PASS |
| 4 | After TTL expiry refreshes | `test_ttl_cache_expires_after_window` | PASS |
| 5 | Latency still performed live | `test_health_latency_not_cached` + `test_latency_measurement_never_coalesced` | PASS |
| 6 | Fetch failure does not poison cache | `test_fetch_failure_does_not_poison_cache` | PASS |
| 7 | No uncontrolled request stampede | `test_concurrent_misses_are_coalesced_single_flight` (8 callers → 1 call) | PASS |
| 8 | Scheduling decision unchanged | existing `test_decision_engine.py` / `test_policies.py` | PASS (all green) |
| 9 | Response schema unchanged | existing `test_api.py` / `test_models.py` | PASS (all green) |

Additional: `test_ttl_is_explicitly_bounded` (TTL clamped to `MAX_METRICS_TTL_SEC`). All `@pytest.mark.anyio` tests pass on **both** the asyncio and trio backends (cross-backend-safe single-flight).

---

## I. Before / after request-flow diagram

**BEFORE (deployed `:latest`, baseline):**
```
/decision
  └─ decide_remote
     ├─ fetch_edge   → [no cache] GET <edge_url>/metrics  (ServiceBus, live every time)
     ├─ fetch_cloud  → [no cache] GET <cloud_url>/metrics
     └─ measure_latency → [no cache, live] GET <cloud_url>/health
     └─ RuleBasedPolicy.decide(edge, cloud, network)
```

**AFTER (with cache enabled, `SCHEDULER_METRICS_TTL_SEC>0`):**
```
/decision
  └─ decide_remote
     ├─ fetch_edge   → [cache HIT within TTL] return cached  OR  [MISS] single-flight GET, store
     ├─ fetch_cloud  → [cache HIT within TTL] return cached  OR  [MISS] single-flight GET, store
     └─ measure_latency → [ALWAYS live, never cached/coalesced] GET <cloud_url>/health
     └─ RuleBasedPolicy.decide(edge, cloud, network)   (inputs unchanged shape/semantics)
```
With `SCHEDULER_METRICS_TTL_SEC=0`, AFTER ≡ BEFORE (cache + single-flight fully bypassed).

---

## J. Scheduling policy and routing were UNCHANGED

- `scheduler/policies.py` (`RuleBasedPolicy`) — **untouched**; no thresholds, weights, bias, or decision branches changed.
- `scheduler/api/routes.py`, `scheduler/models.py`, `orchestrator/*` — **untouched**; response schema and decision semantics identical.
- The cache supplies the same `EdgeMetrics`/`CloudMetrics` shapes (fresh ≤ TTL) to the unchanged policy; only the *frequency* of the underlying `/metrics` network fetch changes. Latency input remains live.

---

## K. Kubernetes / CloudCore / EdgeCore / ServiceBus / orchestrator production config NOT changed

- No `kubectl set image`, `kubectl apply`, scheduler restart, or deployment env change.
- No image built or pushed; ECR production tags untouched.
- No Terraform, IAM, Security Group, CloudCore (EdgeCore) or ServiceBus (Rules/RuleEndpoints) changes.
- No deployment manifest edit. The production cluster still runs `…/scheduler:latest`.

**Note:** this gate is implementation + local validation only. The candidate image for these changes is NOT built or deployed here; deployment env var `SCHEDULER_METRICS_TTL_SEC` at deploy time is deferred to 10E-6/10E-7 (not this gate).

---

## Explicit statement

**10E-4 implemented and locally validated. No production change was made.** All scheduler tests pass (62). If an unexpected failure persists, none did — the only first-attempt test gap was the trio-backend incompatibility of `asyncio.create_task`, fixed by switching single-flight to backend-agnostic `anyio` primitives; no architectural change was required.

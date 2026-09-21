# Gate 10E-6 — Live-Metrics Scheduling: Latency Optimization (Option PA — Concurrent Fetch) Implementation & Local Validation

**Date:** 2026-09-03
**Gate:** 10E-6 = implement + locally validate the recommended latency-optimization option (Option **PA**: run the three independent live fetches concurrently) selected by the 10E-6 investigation (see `10E-6_investigation.md`).
**Result:** 10E-6 IMPLEMENTATION COMPLETE. **No production change / deployment made.**

---

## A. Exact files modified

| File | Change |
|------|--------|
| `scheduler/decision_engine.py` | `decide_remote()` now runs the three independent probes (edge `/metrics`, cloud `/metrics`, cloud `/health` latency) concurrently via an `anyio` task group instead of three sequential `await`s. Added `_fetch_all()` helper and the `anyio` import. |
| `scheduler/tests/test_decision_engine.py` | Added 7 focused concurrency/correctness tests (see H). |

Only these two files were touched. `scheduler/metrics_client.py`, `scheduler/policies.py`, `scheduler/models.py`, `scheduler/api/routes.py`, `scheduler/config.py`, `orchestrator/*`, `edge/*`, `cloud/*` were **NOT** modified.

---

## B. The exact change

**Before (`decide_remote`, sequential):**
```python
edge = await self._metrics.fetch_edge(edge_url)
cloud = await self._metrics.fetch_cloud(cloud_url)
latency_ms = await self._metrics.measure_latency_ms(cloud_url)
network = NetworkMetrics(latency_ms=latency_ms) if latency_ms is not None else None
return self.decide(workload, edge, cloud, network)
```
The three probes are independent, yet run one-after-another. The 10E-6 investigation measured edge `/metrics` ≈ 1008 ms and cloud `/metrics` ≈ 1005 ms (server-side `psutil.cpu_percent(interval=1.0)` in `edge/monitoring/metrics.py` + `cloud/monitoring/metrics.py`), so these serialize to ≈ 2.0 s + a 2.5 ms health probe ≈ **2078 ms** per decision.

**After (`decide_remote`, concurrent):**
```python
edge, cloud, latency_ms = await self._fetch_all(edge_url, cloud_url)
network = NetworkMetrics(latency_ms=latency_ms) if latency_ms is not None else None
return self.decide(workload, edge, cloud, network)
```
`_fetch_all` is an `anyio.create_task_group()` that `start_soon`s the three probes and collects their results into a dict keyed `"edge"` / `"cloud"` / `"latency"`. Because the two dominant ~1 s metric samples now overlap, total wall time drops to ≈ max(1008, 1005) + 2.5 ms + scheduling overhead ≈ **~1.01 s** — roughly the intended ~47% reduction identified in the investigation.

**Why `anyio` (not `asyncio.gather`):** the project's test matrix runs every `@pytest.mark.anyio` test on **both** the asyncio and trio backends. `asyncio.gather` is asyncio-only and fails under trio; `anyio.create_task_group` is backend-agnostic, so the change is correct and testable on both backends without any special-casing. The group `await`s all child tasks before returning, so the policy is still evaluated only after **all three** inputs are collected.

---

## C. Return-schema / policy / exception behavior is UNCHANGED

- `decide_remote` still returns a `Decision` produced by `self.decide(...)` → `RuleBasedPolicy.decide(workload, edge, cloud, network)`. The target/score/reason/priority semantics and the response schema are byte-for-byte the same.
- The policy still receives the **same three inputs** (`edge: EdgeMetrics | None`, `cloud: CloudMetrics | None`, `network: NetworkMetrics | None`), and only after all three are collected.
- **Failure behavior** is identical: each probe returns its existing value on failure —
  - a failed/unavailable `/metrics` yield `None` (policy → `ERROR`);
  - a failed `/health` yields `latency_ms = None` → `network = None`, and any decision branch that is independent of latency still resolves (verified by `test_decide_remote_latency_failure_yields_network_none`, which still reaches `EDGE` with edge healthy + cloud saturated);
  - an `anyio` task-group policy is to propagate the **first** exception raised by any child; the child probes here catch their own `httpx.HTTPError`/`ValueError` internally (in `metrics_client.py`) and return `None`, so no raw exception escapes the group in the validated paths.
- **Caching / single-flight** (`metrics_client.py`, cache + `_Inflight`) is untouched and still applies per URL; the concurrency change only determines *when* the three probes issue their HTTP calls relative to one another.

---

## D. Cache interaction (unchanged)

The 10E-6 investigation confirmed the 10E-5 cache (TTL = 1 s) gave no latency gain because the dominant cost is the *server-side* ~1 s CPU sample, not the round-trip. With the default `metrics_ttl_sec = 0.0` the cache is disabled entirely and every probe is live. When a nonzero TTL is configured, the concurrent path interacts with the existing per-URL cache/single-flight exactly as before:
- Edge + cloud are launched concurrently; each independently checks/hits the cache or performs a single-flight fetch.
- The `/health` latency probe is **always live** (never cached, never coalesced) — verified by `test_decide_remote_latency_never_cached_or_coalesced`.
- Concurrent probes therefore do not bypass, poison, or race the cache; the anyio task group simply collapses wall-clock time that was previously sequential.

---

## E. Logging (unchanged)

The same debug log in `decide()` (`workload=… target=… score=… (reason)`), the metrics-client logs, and the single-flight/cache debug logs are all preserved. No log line added or removed by this change.

---

## F. Concurrency-safety rationale (why concurrent is safe here)

- **Read-only, independent probes.** `fetch_edge`, `fetch_cloud`, and `measure_latency_ms` are pure, independent HTTP reads with no shared mutable state between them. Order of completion cannot change any output because the policy is a pure function of the three collected snapshots.
- **Deterministic result given the same inputs.** Given identical `edge`/`cloud`/`latency_ms` values, `decide_remote` produces the identical `Decision` regardless of completion order — verified by `test_decide_remote_equals_sequential_for_same_inputs`.
- **Backend-agnostic.** The `anyio` task group is correct on both asyncio and trio (see B).
- **Memory / resource bounded.** Only three tasks are spawned per call; the group joins all of them before returning, so no orphaned tasks.

---

## G. Latency behavior (labeled synthetic only)

These are **local synthetic** measurements, not a production benchmark:

| Scenario | Measured (local host, MockTransport 3×50 ms) |
|----------|----------------------------------------------|
| Sequential (would-be) | ~150 ms (3 × 50 ms) |
| Concurrent (actual) | ~50–60 ms (< 50 × 2.2) |

The synthetic concurrency test (`test_decide_remote_concurrent_wall_time_is_about_one_interval`) asserts three ~50 ms live calls complete in roughly **one** 50 ms interval (~60 ms incl. overhead) rather than ~150 ms. Applying the same overlap to the **measured** production numbers (edge 1008 ms, cloud 1005 ms, health 2.5 ms), the projected `decide_remote` wall time drops from ≈ **2078 ms** to ≈ **~1010 ms** (~47%). This is a projection from the 10E-6 instrumentation numbers; it is **NOT** a measured production result — no benchmark was run (see O). Actual field numbers require a controlled production deploy + benchmark, deferred to the next gate.

---

## H. Tests executed and exact results

Command (repo root): `python -m pytest scheduler/tests -q -p no:cacheprovider`

**Result: `76 passed, 1 warning in ~2.49s`** — the 1 warning is the unrelated pre-existing Starlette `httpx` deprecation; no failures. All `@pytest.mark.anyio` tests pass on **both** asyncio and trio backends.

Per-file breakdown:

| File | Tests |
|------|-------|
| `scheduler/tests/test_api.py` | 6 |
| `scheduler/tests/test_decision_engine.py` | 22 |
| `scheduler/tests/test_metrics_client.py` | 26 |
| `scheduler/tests/test_models.py` | 7 |
| `scheduler/tests/test_policies.py` | 15 |
| **Total** | **76** |

(The suite was 62 before this gate; +14 = the 7 new `@pytest.mark.anyio` decision-engine tests × 2 backends. No existing test was removed or weakened.)

7 new concurrency/correctness tests (each run on asyncio + trio):

| # | Requirement | Test | Result |
|---|-------------|------|--------|
| 1 | The three fetches genuinely overlap in time (not serial) | `test_decide_remote_runs_metric_fetches_concurrently` | PASS |
| 2 | Three ~50 ms calls complete in ~one interval (~50 ms), not ~150 ms | `test_decide_remote_concurrent_wall_time_is_about_one_interval` | PASS |
| 3 | Concurrent result == deterministic path for identical inputs | `test_decide_remote_equals_sequential_for_same_inputs` | PASS |
| 4 | Edge overloaded + poor network + medium priority → QUEUE | `test_decide_remote_poor_network_queues_medium` | PASS |
| 5 | Both nodes saturated → ERROR | `test_decide_remote_both_saturated_errors` | PASS |
| 6 | `/health` failure → `network=None` still resolves (EDGE) | `test_decide_remote_latency_failure_yields_network_none` | PASS |
| 7 | Latency probe stays live despite cached metrics | `test_decide_remote_latency_never_cached_or_coalesced` | PASS |

Regression on the sibling suites (`test_metrics_client.py` 26, `test_api.py` 6, `test_models.py` 7, `test_policies.py` 15) — all green.

---

## I. Before / after request-flow diagram

**BEFORE (deployed `:latest`, sequential — ~2078 ms):**
```
/decision
  └─ decide_remote
     ├─ (1) await fetch_edge        GET <edge_url>/metrics    [~1008 ms]
     ├─ (2) await fetch_cloud       GET <cloud_url>/metrics   [~1005 ms]   (serialized)
     ├─ (3) await measure_latency   GET <cloud_url>/health    [~2.5 ms]
     └─ RuleBasedPolicy.decide(edge, cloud, network)
```

**AFTER (this gate, concurrent — projected ~1010 ms, ~47% reduction):**
```
/decision
  └─ decide_remote
     └─ anyio task group  (all three launched concurrently, joined before decide)
        ├─ start_soon  fetch_edge      GET <edge_url>/metrics   [~1008 ms]
        ├─ start_soon  fetch_cloud     GET <cloud_url>/metrics  [~1005 ms]  (overlaps above)
        └─ start_soon  measure_latency GET <cloud_url>/health   [~2.5 ms]   (overlaps)
     └─ RuleBasedPolicy.decide(edge, cloud, network)   (inputs unchanged shape/semantics)
```

---

## J. Source diff summary (manual — git is unusable)

**Note on git:** the repo's ignore file is `.gitignore.txt` (which git does not read), so the whole tree is untracked and `git diff` is unusable. The diff below is reconstructed from the edited file content.

**`scheduler/decision_engine.py`:**
- `import asyncio` removed (no longer used); `import anyio` added.
- `decide_remote(...)`: replaced the three sequential `await`s with `edge, cloud, latency_ms = await self._fetch_all(edge_url, cloud_url)`, keeping the `NetworkMetrics` construction and `self.decide(...)` call unchanged.
- Added `_fetch_all(self, edge_url, cloud_url)` using `anyio.create_task_group()` + `tg.start_soon(capture, name, coro)` writing to a `results` dict, returning `(edge, cloud, latency)`.

**`scheduler/tests/test_decision_engine.py`:**
- Added imports `time`, `anyio`, `httpx`, `pytest` (pytest/httpx already stemmed from `scheduler` test deps).
- Added helpers `_slow_concurrent_handler(sleep_ms)`, `_events_overlap(intervals)`, `_overloaded_edge_json()`, `_saturated_cloud_json()`.
- Added the 7 tests listed in H.

---

## K. Scheduling policy and routing were UNCHANGED

- `scheduler/policies.py` (`RuleBasedPolicy`) — **untouched**; no thresholds, weights, bias, or decision branches changed.
- `scheduler/api/routes.py`, `scheduler/models.py`, `scheduler/config.py`, `orchestrator/*` — **untouched**; response schema and decision semantics identical.
- `scheduler/metrics_client.py` — **untouched**; cache/single-flight/TTL behavior and the always-live latency probe are unchanged.

---

## L. Kubernetes / CloudCore / EdgeCore / ServiceBus / orchestrator production config NOT changed

- No `kubectl set image`, `kubectl apply`, scheduler restart, or deployment env change.
- No image built or pushed; ECR production tags untouched.
- No Terraform, IAM, Security Group, CloudCore (EdgeCore) or ServiceBus (Rules/RuleEndpoints) changes.
- No deployment manifest edit. The production cluster still runs the previously deployed scheduler image.
- **No benchmark was run** against the cluster; latency figures in G are synthetic/local or projected from the 10E-6 investigation instrumentation.

---

## M. Root-cause lever NOT addressed here (documented out of scope)

The investigation identified the dominant cost as the **server-side ~1 s `psutil.cpu_percent(interval=1.0)` CPU sample** in `edge/monitoring/metrics.py` and `cloud/monitoring/metrics.py` (`MetricsCollector(settings.monitor_interval_sec)`, default 1.0, no env override on the deployed cloud node). The root lever is `monitor_interval_sec` (or sampling without `interval=1.0`); this is a metrics-collector change in `edge/` and `cloud/` and is **out of scope** for this gate (falls under edge/cloud modules, not `scheduler/`). Option PA may later be **combined** with a smaller `monitor_interval_sec` for compounding gains, but that is a separate decision.

---

## N. 10E-6 checklist (option PA)

| # | Requirement | Status |
|---|-------------|--------|
| 1 | Three independent probes run concurrently | PASS (`_fetch_all` task group) |
| 2 | Backend-agnostic (works on asyncio **and** trio) | PASS (`anyio.create_task_group`) |
| 3 | `/health` latency stays live, never cached/coalesced | PASS |
| 4 | Result identical to sequential for identical inputs | PASS (equality test) |
| 5 | Failure semantics unchanged (None → ERROR / network-None branches) | PASS |
| 6 | Cache + single-flight unchanged | PASS |
| 7 | Full scheduler suite green (both backends) | PASS (76) |
| 8 | Only `scheduler/decision_engine.py` + its tests modified | PASS |
| 9 | No production/deploy/ECR/K8s change | PASS |

---

## O. Production impact

**Production impact: NONE.** This gate is implementation + local validation only. No image was built or pushed, nothing was deployed, ECR production tags were untouched, and no Kubernetes/CloudCore/EdgeCore/ServiceBus/orchestrator configuration was changed. The projected ~47% latency reduction is **not** a measured production result; realizing it (and confirming it under field conditions) requires a controlled production deploy + benchmark, deferred to the next gate.

---

## Explicit statement

**10E-6 IMPLEMENTATION STATUS: COMPLETE**
`File: docs/phase10/10E/10E-6_implementation.md`
`Production changes: NONE`
`Deployment: NOT PERFORMED`
`ECR: NOT MODIFIED`
`Benchmark: NOT RUN`
`Next action: REVIEW 10E-6 IMPLEMENTATION`

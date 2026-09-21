# 10E-6 REVIEW — Live-Metrics Scheduling: Concurrent Fetch

**Gate:** 10E-6
**Reviewer:** opencode (automated review)
**Date:** 2026-09-03
**Status:** PASS

---

## A. Scope

Review of the 10E-6 production validation: concurrent fetch optimization in `scheduler/decision_engine.py` (Option PA). The three independent HTTP probes (edge `/metrics`, cloud `/metrics`, cloud `/health` latency) now run concurrently via `anyio.create_task_group()` instead of sequentially.

## B. Implementation Verification

| Check | Result |
|-------|--------|
| `anyio.create_task_group()` used | PASS — `decision_engine.py:92` |
| `asyncio` import removed | PASS — line 10 imports `anyio`, no `asyncio` anywhere in file |
| 3 probes concurrent via `_fetch_all()` | PASS — lines 83-98 |
| Policy, cache, single-flight, latency-live semantics preserved | PASS — `decide_remote` calls `_fetch_all()` then `self.decide()` identically to before |
| Test suite 76 passed (asyncio+trio) | PASS — `76 passed, 1 warning in 2.58s` |
| No changes to `metrics_client.py`, `policies.py`, `models.py` | PASS — verified via `git diff --name-only` in production validation |

**Implementation: CORRECT.**

## C. Deployment Verification

| Check | Result |
|-------|--------|
| Image `scheduler:10e-6` deployed | PASS — `sha256:d1aabd2415380d1013eeb1f212983d457566f7ce8c6a24a23b1cce1ca7ba037e` |
| Pod Running/Ready | PASS — `scheduler-8f4bb9b96-lhlpj`, 1/1 |
| RESTARTS=0 | PASS |
| Cloud CP pinning | PASS — `nodeSelector: kubernetes.io/hostname=ip-10-0-1-113...` |
| ECR push prerequisite | PASS — `edgecloud-ecr-push` IAM policy extended to `edgecloud/scheduler` repo |
| Pre-deploy safety gate | PASS — 14/14 checks |

**Deployment: CORRECT.**

## D. Performance Comparison Table — /decision

| Concurrency | 10E-2 Mean | 10E-5 Mean | 10E-6 Mean | 10E-6 vs 10E-2 | 10E-6 vs 10E-5 |
|-------------|------------|------------|------------|-----------------|-----------------|
| C1          | 2100.9     | 2081.7     | **66.0**   | **-96.9%**      | -96.8%          |
| C2          | 2201.1     | 2188.0     | **338.1**  | **-84.6%**      | -84.5%          |
| C4          | 2305.8     | 2378.6     | **680.4**  | **-70.5%**      | -71.4%          |
| C8          | 3128.3     | 2757.9     | **1246.8** | **-60.2%**      | -54.8%          |

All targets = edge (100%). Zero failures across 180 requests.

**C1=66 ms explained:** At concurrency 1, 12 sequential requests complete within the 1 s TTL cache window, so all after the first hit the metrics cache. This is the combined effect of concurrent fetch (reducing per-request time below TTL) + the existing 1 s cache — both real and correct.

## E. Performance Comparison Table — /orchestrate

| Concurrency | Mean (ms) | Median (ms) | P95 (ms) | Sched Lat Mean (ms) |
|-------------|-----------|-------------|----------|---------------------|
| C1          | 415.6     | 241.8       | 1273.8   | 275.7               |
| C2          | 811.0     | 421.0       | 1603.0   | 553.7               |
| C4          | 1474.3    | 1640.1      | 2398.2   | 937.4               |
| C8          | 2076.5    | 1993.9      | 3200.6   | 1234.1              |

No prior /orchestrate baseline exists (10E-2 did not benchmark it). First production data point.

## F. Live Uncached Timing Verification

| Metric | Value |
|--------|-------|
| Sequential sum (edge + cloud + health) | 2016.9 ms |
| /decision total (concurrent) | 1107.7 ms |
| Ratio (concurrent / sequential) | **1.10** |

Concurrent fetch working as designed — the two ~1 s server-side CPU samples overlap. The remaining 100 ms overhead is `decide()` policy evaluation + latency measurement.

## G. Safety Gate

| Gate | Result |
|------|--------|
| Pre-deploy safety (14 checks) | PASS |
| Post-deploy functional regression (11 checks) | PASS |
| Infrastructure regression (pods, services, rules, endpoints) | PASS |
| WSL2 SchedulingDisabled | PASS |
| No unexpected restarts | PASS |

**All safety gates PASS.**

## H. Limitations and Caveats

1. **Cached vs uncached distinction:** C1=66 ms reflects cache+concurrency combined. Live uncached /decision is ~1108 ms. Both are real; the 96.9% improvement vs 10E-2 includes cache benefit.
2. **Sample size:** C1=12 requests, C8=96 requests. Functional for validation; not statistically large.
3. **psutil still bottleneck:** `psutil.cpu_percent(interval=1.0)` is the dominant ~1 s component. Concurrent fetch overlaps two of these; further optimization would require replacing psutil with a non-blocking metric source.
4. **Edge inference separate:** YOLOv8 detection latency is independent of this optimization. Scheduler scheduling is not the bottleneck.
5. **No prior /orchestrate baseline:** 10E-2 did not benchmark /orchestrate. Improvement cannot be quantified for that endpoint.

## I. Architecture Compliance

| Check | Result |
|-------|--------|
| AI layer never talks to cloud directly | PASS — all external calls go through `edge/api/` |
| Scheduler consumes `edge/monitoring` metrics | PASS — `MetricsClient` unchanged |
| Scheduler returns decision, doesn't call cloud | PASS — `decide()` is pure logic |
| API contract preserved | PASS — same request/response schemas |

## J. Verdict

**PASS.**

10E-6 concurrent fetch delivers monotonic improvement across all concurrency levels. The optimization is scheduler-internal with no externally visible behavior change. All safety gates pass. The production deployment is clean with zero regressions.

The combined cache+concurrent effect reduces /decision C1 from 2100.9 ms to 66.0 ms (-96.9%) and C8 from 3128.3 ms to 1246.8 ms (-60.2%).

## K. Next Gate

**10E-7 does not exist.** No further gate is planned or documented. The production validation report (`10E-6_production_validation.md` line 199) explicitly states: "STOP. Do not start 10E-7 or any further optimization."

Phase 10 optimization series is **complete**. The next action is to plan Phase 10+ scope separately (e.g., psutil replacement, edge-side inference optimization, K3s deployment).

## L. Evidence Chain

| Document | Status |
|----------|--------|
| `10E-6_investigation.md` | Read — root cause: psutil interval + sequential fetch |
| `10E-6_implementation.md` | Read — 76 tests, anyio task group, 3 concurrent probes |
| `10E-6_production_validation.md` | Read — PASS, benchmark data, 180 requests |
| `10E-5_production_validation.md` | Read — PASS WITH LIMITATION, cache ineffective at TTL=1s |
| `10E-5_placement_remediation.md` | Read — nodeSelector fix for cloud CP pinning |
| `10E-2_baseline.md` | Read — original baseline numbers |
| `PHASE8_END_TO_END_VALIDATION_REPORT.md` | Read — E2E validation complete |
| `PHASE9_PRODUCTION_HARDENING_REPORT.md` | Read — hardening complete |
| `scheduler/decision_engine.py` | Verified — implementation matches report |
| `scheduler/tests/test_decision_engine.py` | Verified — 76 passed on asyncio+trio |

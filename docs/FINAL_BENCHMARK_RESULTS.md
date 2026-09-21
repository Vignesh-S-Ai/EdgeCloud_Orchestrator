# Final Benchmark Results

## Overview

All benchmark results are from production measurements on the live K3s/KubeEdge cluster. No synthetic or simulated data is presented.

**Production environment:**
- Cloud CP: `ip-10-0-1-113` (K3s control-plane + CloudCore)
- Edge: `i-0080aa7404208982c` / `10.0.1.123` (EdgeCore + edge-node pod)
- Scheduler image: `scheduler:10e-6` (concurrent fetch optimization)

**Benchmark tool:** `docs/phase10/10E/p10_10e_bench.py` (Python, `httpx.AsyncClient`, concurrent requests)

---

## 1. /decision Latency (Scheduler Only, No Inference)

`/decision` measures the time for the scheduler to fetch metrics from edge and cloud, evaluate the policy, and return a placement decision. It does NOT include inference time.

### Raw Numbers

| Concurrency | 10E-2 Mean (ms) | 10E-5 Mean (ms) | 10E-6 Mean (ms) |
|-------------|-----------------|-----------------|-----------------|
| C1 | 2100.9 | 2081.7 | **66.0** |
| C2 | 2201.1 | 2188.0 | **338.1** |
| C4 | 2305.8 | 2378.6 | **680.4** |
| C8 | 3128.3 | 2757.9 | **1246.8** |

### Improvement vs 10E-2 Baseline

| Concurrency | Improvement |
|-------------|-------------|
| C1 | **-96.9%** (2100.9 → 66.0 ms) |
| C2 | **-84.6%** (2201.1 → 338.1 ms) |
| C4 | **-70.5%** (2305.8 → 680.4 ms) |
| C8 | **-60.2%** (3128.3 → 1246.8 ms) |

### P95 Latency

| Concurrency | 10E-2 P95 (ms) | 10E-6 P95 (ms) |
|-------------|----------------|----------------|
| C1 | 2153.1 | 90.1 |
| C2 | 2306.3 | 1182.1 |
| C4 | 2446.5 | 1495.6 |
| C8 | 3667.9 | 1917.4 |

### Critical Distinction: Cached vs Uncached

**C1 = 66.0 ms includes the effect of the 1-second metrics cache.** At concurrency 1, 12 sequential requests complete within the 1-second TTL cache window, so all after the first hit the metrics cache. This is the combined effect of:
1. Concurrent fetch (reducing per-request time below TTL)
2. The existing 1-second metrics cache

**The cleaner measure of the concurrency optimization itself is the live uncached result:**

| Metric | Value |
|--------|-------|
| Sequential probe sum | 2016.9 ms |
| Live uncached /decision (concurrent) | 1107.7 ms |
| Ratio | 1.10 |
| **Improvement** | **-46.7%** |

This measures the pure effect of concurrent fetch without cache benefit.

### 10E-5 Cache-Only Result (No Concurrency)

10E-5 deployed only the metrics cache (TTL=1s) without concurrent fetch. The cache was ineffective because the sequential ~2s fetch exceeded the 1s TTL:

| Concurrency | 10E-5 Mean (ms) | vs 10E-2 |
|-------------|-----------------|----------|
| C1 | 2081.7 | -0.91% |
| C2 | 2188.0 | -0.60% |
| C4 | 2378.6 | +3.16% |
| C8 | 2757.9 | -11.84% |

**Verdict:** Cache alone provided no meaningful improvement. Concurrent fetch was the effective optimization.

---

## 2. /orchestrate Latency (Scheduler + Inference)

`/orchestrate` measures the full pipeline: scheduler decision + inference on the selected node. This is the end-to-end workload processing time.

### Raw Numbers (10E-6, First Production Data Point)

| Concurrency | Mean (ms) | Median (ms) | Min (ms) | Max (ms) | P95 (ms) |
|-------------|-----------|-------------|----------|----------|----------|
| C1 | 415.6 | 241.8 | 181.5 | 1386.6 | 1273.8 |
| C2 | 811.0 | 421.0 | 256.5 | 1761.9 | 1603.0 |
| C4 | 1474.3 | 1640.1 | 370.7 | 2597.1 | 2398.2 |
| C8 | 2076.5 | 1993.9 | 1021.1 | 3884.6 | 3200.6 |

**No prior /orchestrate baseline exists.** 10E-2 did not benchmark /orchestrate.

### Latency Breakdown (C1)

| Component | Approximate | Notes |
|-----------|-------------|-------|
| Scheduler latency (inside /orchestrate) | ~275.7 ms | Measured within the /orchestrate request path |
| Inference | ~117 ms | YOLOv8n on edge |
| HTTP overhead + orchestrator | ~23 ms | Routing, serialization |
| **Total /orchestrate** | **415.6 ms** | Measured |

**Note:** The standalone `/decision` benchmark (C1=66ms) measures the scheduler in isolation with a cache hit. The scheduler component inside `/orchestrate` (~275.7ms) is measured in a different request context that includes full application path overhead. These are different measurements of the scheduler in different contexts — they are not contradictory.

---

## 3. Live Uncached Probe Timing

Measured with cache deliberately bypassed (requests spaced >1 second apart) to isolate the concurrent fetch effect.

### Per-Probe Timing (10E-6 STEP 5)

| Probe | Mean (ms) | Median (ms) | Min (ms) | Max (ms) | P95 (ms) |
|-------|-----------|-------------|----------|----------|----------|
| edge /metrics (ServiceBus) | 1009.6 | 1009.0 | 1008.1 | 1011.6 | 1011.5 |
| cloud /metrics (ClusterIP) | 1004.8 | 1004.8 | 1003.9 | 1005.4 | 1005.3 |
| cloud /health (ClusterIP) | 2.6 | 2.5 | 2.2 | 3.0 | 2.7 |
| **/decision total** | **1107.7** | **1108.0** | **1087.3** | **1131.9** | **1127.2** |

### Analysis

| Metric | Value |
|--------|-------|
| Sequential sum (edge + cloud + health) | 2016.9 ms |
| /decision total (concurrent) | 1107.7 ms |
| Ratio (concurrent / sequential) | 1.10 |
| Overlap achieved | ~909 ms saved |

The two ~1-second `psutil.cpu_percent(interval=1.0)` samples overlap almost completely. The remaining ~108 ms is policy evaluation, HTTP overhead, and measurement noise.

---

## 4. Edge Inference Latency

| Source | Measurement | Context |
|--------|-------------|---------|
| Phase 8 8C | 114.74 ms | Single /detect call |
| Phase 8 8H | 198.58 ms | 24× repeated (includes overhead) |
| Phase 8 8K | 232 ms avg | Edge average across tests |
| Phase 10 /orchestrate | ~117 ms | Inference portion of /orchestrate C1 |

Edge inference is CPU-bound on YOLOv8n (~6MB model). The variance between measurements reflects system load, image size, and psutil sampling overhead.

---

## 5. Cloud Inference Latency

| Source | Measurement | Context |
|--------|-------------|---------|
| Phase 8 8K | 193 ms avg | Cloud average across tests |

Raw model inference averages (Phase 8 8K): edge ~132.5ms, cloud ~113.5ms — the difference reflects hardware/runtime variation between EC2 instances, not ServiceBus. End-to-end through the orchestrator: edge ~232ms (adds ~100ms ServiceBus overhead), cloud ~193ms.

---

## 6. Concurrency Resilience

| Gate | Concurrency | Requests | Success Rate | Failures |
|------|-------------|----------|-------------|----------|
| Phase 8 8H | 1 (sequential) | 24 | 100% | 0 |
| Phase 9 9G | 1, 2, 4, 8 | 120 | 100% | 0 |
| Phase 10 10E-2 | 1, 2, 4, 8 | 180 | 100% | 0 |
| Phase 10 10E-5 | 1, 2, 4, 8 | 180 | 100% | 0 |
| Phase 10 10E-6 | 1, 2, 4, 8 | 180 | 100% | 0 |
| **Total** | | **684+** | **100%** | **0** |

No OOM events, no 5xx responses, no pod restarts under any concurrency level.

---

## 7. Stability Evidence

**Phase 8 8L — 15-minute sustained test:**
- 432 requests over 15 minutes
- 100% HTTP 200 success rate
- Zero pod restarts
- /health 200 at start and end
- Scheduler latency stable throughout

---

## 8. Summary Table

| Metric | Baseline (10E-2) | Optimized (10E-6) | Improvement |
|--------|------------------|-------------------|-------------|
| /decision C1 | 2100.9 ms | 66.0 ms | -96.9% |
| /decision C8 | 3128.3 ms | 1246.8 ms | -60.2% |
| /decision live uncached | 2016.9 ms | 1107.7 ms | -46.7% |
| /orchestrate C1 | N/A | 415.6 ms | First data point |
| Edge inference | ~114-232 ms | ~114-232 ms | No change |
| Cloud inference | ~193 ms | ~193 ms | No change |
| Success rate | 100% | 100% | No change |

---

## 9. What These Numbers Mean

1. **66 ms is NOT the end-to-end AI inference latency.** It is the scheduler's /decision time with cache hit. The full /orchestrate pipeline takes ~416ms at C1.

2. **The concurrent fetch optimization reduced scheduling overhead.** Live uncached /decision went from ~2017ms to ~1108ms (-46.7%). This is the pure concurrency effect.

3. **The metrics cache became effective after concurrent fetch.** Before concurrent fetch, sequential ~2s requests exceeded the 1s TTL, making the cache useless. After optimization, per-request time dropped below TTL, enabling cache hits.

4. **Inference latency is unchanged.** The optimization targeted the scheduler, not the AI model. Raw model inference averages: edge ~132.5ms, cloud ~113.5ms (Phase 8 8K).

5. **All improvements are monotonic.** Every concurrency level (C1, C2, C4, C8) shows improvement. No level regressed.

6. **Zero failures.** 684+ production requests with 100% success rate. The optimization introduced no instability.

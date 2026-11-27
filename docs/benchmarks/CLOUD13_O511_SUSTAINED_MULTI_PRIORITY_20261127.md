# O5.11: Sustained Multi-Priority Load and Stability Benchmark

**Date:** 27 November 2026  
**Status:** **PARTIAL PASS with reliability findings.** The workload ran across both phases and placement responded to resource recovery, but five HTTP 503 responses were observed.

## Objective

Extend O5.10 from short three-request bursts into a longer repeated multi-priority workload. Measure successful inference rate, latency percentiles, throughput, resource pressure, placement behavior and recovery.

## Method

- Sent real requests through the deployed `POST /orchestrate` endpoint.
- Used three concurrent requests per round: Low, Medium and High priority.
- Ran eight rounds during Edge CPU pressure and eight rounds during the recovery phase: **48 requests total**.
- Used live Edge and Cloud metrics for scheduler placement; no synthetic scheduler metric snapshots were supplied.
- Applied bounded CPU pressure using two worker processes on the Edge EC2 instance for approximately 60 seconds.
- Reused a 37,610-byte JPEG input (SHA-256: `cacdb9bc5e08c713231c1e45d3c620d40ef2145f1a8c3daef3dc0338584881a1`).

## Resource observations

| Resource | Edge under pressure | Cloud under pressure | Edge after recovery |
|---|---:|---:|---:|
| CPU | 100.0% | 7.0% | 1.5% |
| RAM | 32.6% | 65.2% | 33.0% |
| Disk | 20.1% | 30.3% | 20.1% |

Edge CPU was observed at 100% in all eight pressure-phase samples. During the recovery phase it remained at 100% for the first four samples, then dropped to 56.1%, 2.0%, 1.0% and 0.5%.

## Overall results

| Metric | Result |
|---|---:|
| Total requests | 48 |
| HTTP 200 | 43 |
| HTTP 503 | 5 |
| Successful inference rate | 89.58% |
| Completed inferences | 43 |
| Total detections returned | 129 |
| Fallbacks | 0 |

All 43 completed inference responses contained three detections. The five HTTP 503 responses returned no inference result. Their response bodies were not retained, so this report does not claim a specific queue or failure reason.

## Phase results

| Metric | Edge pressure | Recovery |
|---|---:|---:|
| Requests | 24 | 24 |
| HTTP 200 | 21 | 22 |
| HTTP 503 | 3 | 2 |
| Success rate | 87.50% | 91.67% |
| Attempt throughput | 0.832 req/s | 0.836 req/s |
| Client RTT p50 | 1,629.39 ms | 1,628.88 ms |
| Client RTT p95 | 1,784.33 ms | 1,841.55 ms |
| Mean client RTT | 1,653.23 ms | 1,629.27 ms |

### Placement behavior

| Phase | Cloud executions | Edge executions | No inference result |
|---|---:|---:|---:|
| Edge pressure | 20 | 1 | 3 |
| Recovery | 10 | 12 | 2 |

During Edge pressure, Cloud handled most completed requests. One High-priority workload was executed on Edge as best effort. At the beginning of the recovery phase, Edge was still overloaded, so the scheduler continued to use Cloud. As Edge CPU returned to low utilization, placement shifted back to Edge. The final recovery rounds routed all three priorities to Edge.

### Mean total latency by priority

| Phase | Low | Medium | High |
|---|---:|---:|---:|
| Edge pressure | 1,615.48 ms | 1,642.32 ms | 1,616.67 ms |
| Recovery | 1,612.57 ms | 1,592.65 ms | 1,627.69 ms |

These values are end-to-end orchestration latency, including scheduler metrics collection and inference. They are not isolated model execution times.

## Cluster and regression validation

- Cloud Node, Edge Node, Orchestrator and Scheduler: **1/1 Ready**.
- Pod restarts: **zero**.
- Orchestrator health endpoint: **status `ok`**.
- Full repository test suite: **143 passed in 14.95 seconds**.

## Findings and next actions

1. **Placement response:** The scheduler offloaded the majority of completed work to Cloud while Edge was saturated and returned work to Edge after CPU recovery.
2. **Reliability gap:** Five of 48 requests returned HTTP 503. Capture response bodies and correlate each with scheduler decision details in the next diagnostic run.
3. **Latency overhead:** Scheduler/metrics collection contributes materially to the roughly 1.6-second end-to-end request time. Profile scheduler decision latency separately from inference.
4. **Benchmark depth:** Increase to a sustained open-loop request generator and multiple concurrency levels only after the 503 causes are understood.

## Conclusion

**PARTIAL PASS:** The live system demonstrated adaptive placement under sustained Edge CPU pressure and gradual return to Edge after recovery. It completed 43 of 48 requests, but the 10.42% HTTP 503 rate means the stability objective is not fully met. O5.11 exposes a concrete reliability and latency investigation for the next milestone rather than masking those results.

Machine-readable evidence: `docs/benchmarks/cloud13_o511_sustained_multi_priority_20261127.json`.

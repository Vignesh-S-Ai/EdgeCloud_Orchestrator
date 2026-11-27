# CLOUD-13 O5: Scheduler Concurrency and Policy Matrix

**Execution date:** 2026-11-26 UTC  
**Environment:** Live AWS/K3s cluster, requests sent from the orchestrator pod to the scheduler ClusterIP service.  
**Change safety:** Read-only benchmark. No workload stress, pod restart, scale, Service patch, or deployment modification.

## Objective and method

Measure scheduler API latency under controlled concurrency and verify deterministic placement outcomes across representative resource/network conditions. The benchmark submitted synthetic, explicit Edge/Cloud/Network metric snapshots to `POST /decision`. This intentionally isolates scheduler API + policy execution from remote metrics collection and model inference.

Five warm-up requests succeeded. Four concurrency levels then ran 50 requests each. A separate policy matrix ran 20 requests per scenario.

## Concurrency results

| Concurrency | Requests | HTTP success | Mean (ms) | Median (ms) | p95 (ms) | Max (ms) |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 50 | 50 | 4.49 | 1.88 | 2.91 | 68.84 |
| 2 | 50 | 50 | 8.84 | 3.11 | 39.87 | 75.44 |
| 4 | 50 | 50 | 20.43 | 6.16 | 78.89 | 81.85 |
| 8 | 50 | 50 | 42.48 | 12.48 | 89.50 | 92.75 |

All 200 requests returned HTTP 200. The increasing tail latency under higher concurrency is visible, while median scheduler API latency remained below 13 ms at concurrency 8. Maximums indicate occasional outliers and should not be hidden by the median.

## Policy matrix

| Scenario | Expected target | Correct / total | Mean (ms) | p95 (ms) |
|---|---|---:|---:|---:|
| Edge healthy | Edge | 20/20 | 5.39 | 2.38 |
| Edge overloaded, Cloud healthy | Cloud | 20/20 | 4.77 | 30.06 |
| Both saturated | Error | 20/20 | 4.75 | 2.48 |
| Edge overloaded, high network latency, Medium priority | Queue | 20/20 | 4.74 | 28.80 |
| Edge overloaded, high network latency, High priority | Edge | 20/20 | 4.83 | 25.70 |

All 100 policy-matrix requests returned HTTP 200 and matched the expected deterministic rule-policy outcome (100/100). The `error` target is a valid policy decision in the both-saturated case, not an HTTP failure.

## Interpretation

- Scheduler decision handling with explicit metrics is lightweight in this test: median latency ranged from 1.88 ms at concurrency 1 to 12.48 ms at concurrency 8.
- The p95 increase at concurrency 2/4/8 suggests contention or request scheduling effects worth profiling in a larger run; the sample does not establish a capacity ceiling.
- The placement matrix confirms the current rule policy follows the five tested branches consistently.
- Earlier live scheduler-only measurements were around 1.1 s mean at concurrency 1 because they included live metric probes. Those results are not directly comparable to this isolated `/decision` benchmark.

## Limitations

This is not an end-to-end inference benchmark, does not load the Edge/Cloud nodes, does not validate camera availability, and does not establish ML/adaptive-policy accuracy. Synthetic metric inputs are used to test policy branches. The current Edge health endpoint has previously reported `camera_open=false` while `model_loaded=true`; no camera-dependent claim is made here.

## O5 status

**PASS: controlled scheduler API concurrency and tested rule-policy branch consistency.**  
**Not yet assessed:** live end-to-end concurrent inference, resource-load response, adaptive placement under changing measured loads, and failover overhead under concurrent requests.

## Reproduction

The benchmark was executed from the orchestrator pod against `http://scheduler.edgecloud.svc:8002/decision`, using explicit workload, Edge metrics, Cloud metrics, and network metrics payloads. Machine-readable results are in `cloud13_o5_scheduler_benchmark_20261127.json`.
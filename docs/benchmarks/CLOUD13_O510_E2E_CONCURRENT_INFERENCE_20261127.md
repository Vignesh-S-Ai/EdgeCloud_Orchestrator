# O5.10: End-to-End Concurrent Multi-Priority Inference Validation

**Date:** 27 November 2026  
**Status:** **PASS** for the tested live three-way concurrent inference and recovery scenario.

## Objective

Validate actual inference executions through the deployed orchestrator, not only scheduler decision requests. Exercise Low, Medium and High priorities concurrently while Edge is overloaded, then verify that placement returns to Edge after recovery.

## Method

- Sent requests through the deployed `POST /orchestrate` endpoint.
- Used the same 37,610-byte JPEG input for all requests (SHA-256: `cacdb9bc5e08c713231c1e45d3c620d40ef2145f1a8c3daef3dc0338584881a1`).
- Ran three concurrent requests per round, one each for Low, Medium and High priority.
- Executed two rounds during live Edge CPU pressure and two rounds after recovery: 12 actual inference requests total.
- Scheduler used live Edge and Cloud metrics. No synthetic metrics were supplied to orchestration requests.
- Applied a bounded 45-second CPU load using two worker processes on the **Edge EC2 instance**.

## Live resource snapshots

| Resource | Edge under pressure | Cloud under pressure | Edge after recovery |
|---|---:|---:|---:|
| CPU | 100.0% | 4.0% | 1.5% |
| RAM | 32.2% | 64.1% | 31.8% |
| Disk | 20.1% | 30.3% | 20.1% |

## End-to-end results

| Phase | Priority | Concurrent requests | Actual execution target | HTTP success |
|---|---|---:|---|---:|
| Edge pressure | Low | 2 | Cloud | 2/2 |
| Edge pressure | Medium | 2 | Cloud | 2/2 |
| Edge pressure | High | 2 | Cloud | 2/2 |
| Recovery | Low | 2 | Edge | 2/2 |
| Recovery | Medium | 2 | Edge | 2/2 |
| Recovery | High | 2 | Edge | 2/2 |

**12/12 requests returned HTTP 200.** All 12 completed on the scheduler-selected target, with no fallback and no orchestration errors. Every inference response contained three detections.

### Latency observations

| Phase | Priority | Mean total latency |
|---|---|---:|
| Edge pressure, Cloud execution | Low | 1,081.14 ms |
| Edge pressure, Cloud execution | Medium | 1,075.68 ms |
| Edge pressure, Cloud execution | High | 936.18 ms |
| Recovery, Edge execution | Low | 1,071.28 ms |
| Recovery, Edge execution | Medium | 1,119.37 ms |
| Recovery, Edge execution | High | 971.44 ms |

These are end-to-end orchestration timings under concurrent load, including scheduler/metrics collection and inference. They should not be interpreted as isolated model inference times.

## Recovery and cluster health

After the Edge load ended, Edge CPU returned to 1.5%. All three priority classes returned to Edge execution in both recovery rounds.

Post-test validation:
- Cloud Node, Edge Node, Orchestrator and Scheduler deployments: **1/1 Ready**.
- All four pods: **zero restarts**.
- Orchestrator health endpoint: **HTTP 200, status `ok`**.
- Full repository test suite: **143 passed in 16.16 seconds**.

## Conclusion

**PASS:** The live system concurrently executed Low, Medium and High inference workloads on Cloud while Edge CPU was at 100%, then returned all three priority classes to Edge after resource recovery. All 12 requests succeeded, each produced three detections, no fallback was needed, and the cluster remained healthy.

## Limitations

- Three concurrent requests per round; this is not a large-scale capacity or saturation benchmark.
- Only two rounds per phase were measured.
- Detection counts were captured, but no ground-truth accuracy evaluation was performed.
- Latencies include live scheduler metric collection and orchestration overhead.
- The test demonstrates placement and successful inference, not an application-level latency SLO.

Machine-readable evidence: `docs/benchmarks/cloud13_o510_e2e_concurrent_inference_20261127.json`.

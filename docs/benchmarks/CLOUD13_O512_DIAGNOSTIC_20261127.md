# O5.12: 503 Root-Cause and Scheduler Latency Diagnostic

**Date:** 27 November 2026  
**Status:** Diagnostic complete. No code or deployment changes made.

## Objective

Investigate the HTTP 503 responses and elevated scheduler latency observed in O5.11. Capture complete response bodies, correlate them with placement decisions, and isolate the measurable metrics-probe cost.

## 1. Baseline without injected Edge pressure

A five-round test sent 15 requests (three concurrent priorities per round) through the live orchestrator.

- **15/15 HTTP 200**, no errors.
- Mean scheduler latency: **902.81 ms**.
- Mean inference latency: **265.42 ms**.
- All 15 requests selected and executed on Edge.

Scheduler latency varied noticeably between rounds:
- Approximately 270-322 ms on faster rounds.
- Approximately 1,262-1,366 ms on slower rounds.

This is consistent with the cache refresh pattern, but the timing data alone does not prove each individual request was a cache hit or miss.

## 2. Metrics probe timing

Five direct probes were made from the Cloud EC2 host through the KubeEdge tunnel.

| Probe | HTTP | Mean latency |
|---|---:|---:|
| Edge `/metrics` | 200 | **1,009.61 ms** |
| Edge `/health` | 200 | **9.18 ms** |

The Edge metrics endpoint is the dominant measured probe cost. The health probe used for the network-latency policy check is comparatively quick.

The live scheduler configuration already has `SCHEDULER_METRICS_TTL_SEC=2`. Faster scheduler calls are consistent with cached node metrics, while cache refreshes still incur the slow Edge metrics fetch. Scheduler logs confirm successful HTTP 200 responses from both Edge and Cloud metrics endpoints.

A separate direct Cloud metrics timing attempt had a malformed tunnel path and a kubectl JSONPath quoting error. It is excluded from the latency measurements.

## 3. Reproducing HTTP 503 under Edge pressure

Two bounded CPU workers drove Edge CPU to 100%. Six rounds of three concurrent inference requests were sent through the live orchestrator.

| Metric | Result |
|---|---:|
| Requests | 18 |
| HTTP 200 | 14 |
| HTTP 503 | 4 |
| Success rate | 77.78% |
| Mean scheduler latency for successful requests | 805.75 ms |

### Captured HTTP 503 reasons

All four response bodies explicitly reported a scheduler placement of `target=queue`:

| Round | Priority | Edge CPU | Measured network latency | Policy result |
|---:|---|---:|---:|---|
| 1 | Medium | 100% | 233.1 ms | Queue |
| 2 | Low | 100% | 267.6 ms | Queue |
| 2 | Medium | 100% | 252.3 ms | Queue |
| 3 | Low | 100% | 236.5 ms | Queue |

Each network measurement exceeded the configured 200 ms offload limit. Edge was overloaded, so Low and Medium priority requests were queued instead of being sent to a Cloud path considered too slow by policy.

High-priority requests followed the existing policy: Cloud when viable, otherwise Edge best effort. The completed requests returned three detections each.

## 4. Root cause

**The reproduced 503 responses are intentional policy backpressure, not evidence of a scheduler crash or failed inference service.**

The decision chain is:

1. Edge CPU exceeds its priority-adjusted threshold.
2. The measured Edge-to-Cloud health RTT exceeds 200 ms.
3. Cloud offload is considered non-viable.
4. Low and Medium workloads receive a QUEUE decision.
5. The orchestrator represents a non-executable QUEUE target as HTTP 503 and includes the reason in the response detail.

This explains the reproduced 503s. O5.11 did not preserve its five original response bodies, so we cannot claim conclusively that every O5.11 503 had this same cause.

## 5. Latency finding

The strongest measured latency bottleneck is Edge `/metrics` over the KubeEdge tunnel, at roughly one second. The live scheduler already uses a two-second cache, which reduces repeated fetches but does not eliminate the cost of refreshes.

The next optimization should focus on reducing the cost of Edge metric acquisition without making placement decisions rely on excessively stale data. A small, bounded metrics cache or a more efficient metrics path must be evaluated against placement responsiveness before changing production settings.

## 6. Cluster health

- Cloud Node: 1/1 Ready
- Edge Node: 1/1 Ready
- Orchestrator: 1/1 Ready
- Scheduler: 1/1 Ready
- Pod restarts: zero
- Orchestrator health: `ok`

## Conclusion

O5.12 identified the reproduced HTTP 503 responses as expected QUEUE/backpressure outcomes when Edge is overloaded and Cloud network latency exceeds the policy limit. It also isolated Edge metrics acquisition over KubeEdge as the largest measured scheduler-probe cost.

No code or deployment changes were made. The next milestone should improve the efficiency and observability of metric collection, while preserving freshness and the existing adaptive-placement behavior.

Machine-readable evidence: `docs/benchmarks/cloud13_o512_diagnostic_20261127.json`.

# O5.7: Live Telemetry Placement Validation

**Date:** 27 November 2026  
**Status:** Completed against the deployed Kubernetes scheduler.

## Objective

Validate that the deployed scheduler can acquire current Edge and Cloud resource metrics and edge-to-cloud network latency from live endpoints, then make repeated placement decisions through its `/decision` API.

## Live observations

| Signal | Edge | Cloud |
|---|---:|---:|
| CPU | 1.0% | 3.5% |
| RAM | 32.1% | 63.7% |
| Disk | 20.1% | 30.3% |

Observed live network latency across requests ranged from **12.8 ms to 98.5 ms**. The scheduler pod successfully reached both the Edge metrics endpoint through the KubeEdge tunnel and the Cloud metrics service.

## Decision replay

The deployed scheduler received 15 requests using live `edge_url` and `cloud_url` inputs: five each for Low, Medium, and High priority, with the same workload ID reused within each priority sequence.

| Priority | Requests | HTTP 200 | Edge | Cloud | Queue/Error | Switches |
|---|---:|---:|---:|---:|---:|---:|
| Low | 5 | 5 | 5 | 0 | 0 | 0 |
| Medium | 5 | 5 | 5 | 0 | 0 | 0 |
| High | 5 | 5 | 5 | 0 | 0 | 0 |
| **Total** | **15** | **15** | **15** | **0** | **0** | **0** |

All 15 requests succeeded. With Edge resources comfortably below the configured priority-adjusted thresholds and measured network latency below the 200 ms offload limit, the scheduler consistently selected Edge.

## Scope and limitations

- This is a live telemetry integration check, not a synthetic threshold-jitter replay.
- Only the naturally observed healthy resource condition was tested. No overload was induced, so live overload-triggered offload remains unvalidated by this milestone.
- No inference workload was executed.
- The test validates live metric acquisition and the deployed scheduler decision path, not autonomous long-duration adaptation.

## Evidence

- `docs/benchmarks/cloud13_o57_live_telemetry_20261127.json`
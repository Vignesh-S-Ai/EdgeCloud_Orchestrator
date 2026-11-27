# CLOUD-13 O5.3: Live End-to-End Concurrent Inference Benchmark

**Execution:** 2026-11-26 18:56 UTC (2026-11-27 local time)  
**Environment:** AWS ap-south-1, live K3s/KubeEdge deployment, orchestrator `/orchestrate` endpoint  
**Result:** PASS for the tested C1/C2/C4 workloads on both inference targets

## Objective

Measure full-pipeline response time under controlled concurrent inference requests, comparing Edge and Cloud execution using the same image and request parameters.

## Method

- Image: `Sampleimage.jpg`, 37,610 bytes, SHA-256 `cacdb9bc5e08c713231c1e45d3c620d40ef2145f1a8c3daef3dc0338584881a1`
- Confidence: 0.25; annotated: false
- Two warm-up requests per target
- Ten measured requests per target at concurrency C1, C2 and C4
- Three-second cooldown between each batch
- Requests submitted through live `POST /orchestrate`; model inference ran on the real selected node
- Explicit synthetic resource snapshots were supplied to deterministically force Edge or Cloud placement. The inference execution was real; placement was not driven by live metrics in this experiment.
- C8 was deliberately omitted to protect the single-replica Edge inference deployment.

## Results

| Target | Concurrency | HTTP success | Mean client RTT | Median RTT | p95 RTT | Mean inference | Mean pipeline |
|---|---:|---:|---:|---:|---:|---:|---:|
| Edge | 1 | 10/10 | 186.80 ms | 192.06 ms | 199.50 ms | 159.25 ms | 184.54 ms |
| Edge | 2 | 10/10 | 319.61 ms | 306.02 ms | 398.29 ms | 208.61 ms | 314.57 ms |
| Edge | 4 | 10/10 | 558.91 ms | 563.74 ms | 659.58 ms | 309.74 ms | 525.53 ms |
| Cloud | 1 | 10/10 | 227.96 ms | 203.30 ms | 263.25 ms | 201.44 ms | 225.03 ms |
| Cloud | 2 | 10/10 | 374.47 ms | 363.23 ms | 431.15 ms | 236.98 ms | 342.20 ms |
| Cloud | 4 | 10/10 | 692.24 ms | 614.61 ms | 898.98 ms | 401.03 ms | 622.83 ms |

Scheduler mean latency by concurrency was 25.27 / 105.94 / 215.77 ms for Edge-selected C1/C2/C4 and 23.57 / 105.20 / 221.77 ms for Cloud-selected C1/C2/C4.

## Reliability and output consistency

- 60/60 measured requests returned HTTP 200.
- 30 requests executed on Edge and 30 on Cloud, matching the requested placement in every case.
- No fallback was required.
- Every successful response contained three detections.
- No request errors were recorded.

## Resource snapshots

| Node | Before CPU | Before RAM | After CPU | After RAM |
|---|---:|---:|---:|---:|
| Edge | 1.5% | 31.9% | 0.5% | 32.4% |
| Cloud | 3.5% | 63.0% | 4.0% | 64.5% |

These are point-in-time snapshots before and after the benchmark, not peak utilization measurements. They do not establish the maximum resource load reached during individual requests.

## Interpretation

- Edge had lower mean client RTT than Cloud at all three tested concurrency levels: 186.80 vs 227.96 ms at C1, 319.61 vs 374.47 ms at C2, and 558.91 vs 692.24 ms at C4.
- Latency increased with concurrency on both targets. At C4, Edge mean client RTT was 558.91 ms and Cloud was 692.24 ms; the Cloud p95 reached 898.98 ms.
- Mean inference time increased from C1 to C4 on both nodes, from 159.25 to 309.74 ms on Edge and 201.44 to 401.03 ms on Cloud.
- The scheduler portion also rose with concurrency, indicating the full pipeline cost is not inference-only.

## Limitations

This is a controlled placement comparison, not an adaptive scheduling accuracy test: explicit synthetic metrics were used to force each destination. It is also not a peak-capacity or saturation test. C8 was intentionally not attempted. Resource readings are snapshots rather than continuous peak telemetry. The Edge health endpoint continues to report `camera_open=false` while `model_loaded=true`; these image-based inference requests succeeded, but camera capture is not validated.

## Post-test health

All four deployments were 1/1 Ready: Cloud Node, Edge Node, Orchestrator and Scheduler. Orchestrator health returned HTTP 200 `ok`. Edge health returned HTTP 200 `degraded` with `model_loaded=true` and `camera_open=false`. No pods restarted and no deployment configuration was changed.

## O5.3 conclusion

**PASS:** Live end-to-end concurrent inference completed successfully for Edge and Cloud at C1, C2 and C4 with 60/60 HTTP successes and consistent three-detection responses. Edge was faster in mean client RTT in all tested batches. No claim is made about C8 capacity, maximum utilization, or adaptive policy accuracy.

Machine-readable results: `cloud13_o53_concurrent_inference_20261127.json`.
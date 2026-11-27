# O5.8: Live Load and Adaptive Offloading Validation

**Date:** 27 November 2026  
**Status:** Completed against the deployed AWS/K3s/KubeEdge environment.

## Objective

Exercise the deployed adaptive scheduler with real Edge and Cloud telemetry while controlled CPU pressure is applied to the Edge node. Verify Cloud offloading, end-to-end inference execution, and return to Edge after resource recovery.

## Test method

- Applied a bounded CPU busy-loop using two worker processes on the Edge EC2 node for approximately 55 seconds.
- Did not scale, delete, or restart any Kubernetes workload.
- Submitted live metric decisions to the deployed scheduler through its in-cluster API. Metrics were fetched from the Edge KubeEdge tunnel and Cloud metrics service, not supplied as synthetic snapshots.
- Used a Low-priority object-detection workload with a stable workload ID to exercise the stateful placement hysteresis.
- During overload, submitted an actual inference request through the deployed Orchestrator.

## Live overload observations

Across eight consecutive scheduler samples:

- Edge CPU remained at **100.0%**; Edge RAM was 32.3% and disk 20.1%.
- Cloud CPU ranged from 2.1% to 15.5%; Cloud RAM ranged from 63.9% to 64.3%.
- Measured network latency ranged from 25.1 ms to 103.7 ms, within the configured 200 ms limit.
- **8/8 decisions selected Cloud**, with no API errors.

The scheduler explicitly reported Edge CPU above the 70% Low-priority threshold and offloaded the workload to Cloud.

## End-to-end inference during overload

A real request was submitted to `POST /orchestrate` while Edge CPU was observed at 100%.

| Measure | Result |
|---|---:|
| HTTP response | 200 |
| Selected target | Cloud |
| Actual inference target | Cloud |
| Fallback used | No |
| Scheduler latency | 1,113.22 ms |
| Inference latency | 140.72 ms |
| Total pipeline latency | 1,253.97 ms |

The Cloud YOLOv8 inference endpoint completed successfully using a generated 320x240 test image. It returned zero detections, which is expected to be possible for this test input; this test validates placement and inference completion, not detection accuracy.

## Recovery and hysteresis

After the bounded load ended, repeated live decisions for the same workload ID showed:

1. While Edge CPU was still 100%, the scheduler retained Cloud placement for three observations.
2. When Edge CPU fell to 55.1%, it crossed the configured recovery margin and the scheduler returned the workload to Edge.
3. A subsequent observation showed Edge CPU at 2.0%, with the decision still on Edge.

This demonstrates Cloud retention during continued overload and a controlled return to Edge after recovery, without threshold-jitter toggling in this run.

## Post-test cluster health

All four deployments were ready after the test:

| Deployment | Ready |
|---|---:|
| Cloud Node | 1/1 |
| Edge Node | 1/1 |
| Orchestrator | 1/1 |
| Scheduler | 1/1 |

All four pods reported zero restarts. The temporary load was time-bounded and no deployment configuration was changed.

## Limitations

- The pressure generator was a bounded synthetic CPU busy-loop, not a representative production workload.
- Only Low-priority live offloading and recovery were exercised here.
- The inference test image was generated for this validation and produced zero detections; no detection-accuracy conclusion is drawn.
- This is a short controlled validation, not a long-duration reliability or maximum-capacity benchmark.

## Conclusion

**PASS for the tested path:** live Edge CPU overload was detected, eight of eight scheduler decisions moved to Cloud, a real orchestrated inference request completed on Cloud with HTTP 200, and the same workload returned to Edge once CPU utilization recovered below the hysteresis recovery threshold. Cluster deployments remained ready with zero pod restarts.

Machine-readable evidence: `docs/benchmarks/cloud13_o58_live_load_offload_20261127.json`.
# O5.4: Adaptive Placement Under Changing Resource Conditions

**Validation date:** 26 November 2026 UTC  
**Result:** PASS  
**Scheduler policy:** `rule_based`  
**Endpoint:** `http://127.0.0.1:8002/decision`

## Objective

Validate that the deployed scheduler selects the expected placement as Edge/Cloud resource snapshots, network latency, and workload priority change. This milestone validates the existing deterministic rule-based policy. It does not claim machine-learning-based scheduling or autonomous metric collection.

## Method

- Submitted requests to the live Scheduler API from inside the running scheduler pod.
- Supplied synthetic Edge, Cloud, and network metric snapshots.
- Executed 19 scenarios, each repeated five times (95 requests).
- Executed a sequential 12-step Edge CPU pressure transition series.
- Total: **107 requests**.
- No inference workloads were run, no pods were stopped or scaled, and no deployment configuration was changed.

## Results

| Scenario | Expected target | Requests | Correct | Mean API latency (ms) | p95 (ms) |
|---|---:|---:|---:|---:|---:|
| Healthy baseline | Edge | 5 | 5 | 36.189 | 89.470 |
| Edge CPU 69% | Edge | 5 | 5 | 1.096 | 1.294 |
| Edge CPU 70% boundary | Edge | 5 | 5 | 1.072 | 1.144 |
| Edge CPU 70.1% | Cloud | 5 | 5 | 0.962 | 1.046 |
| Edge CPU 95% | Cloud | 5 | 5 | 17.577 | 83.138 |
| Edge RAM 69% | Edge | 5 | 5 | 0.974 | 1.026 |
| Edge RAM 70% boundary | Edge | 5 | 5 | 1.082 | 1.456 |
| Edge RAM 70.1% | Cloud | 5 | 5 | 17.447 | 82.263 |
| Edge disk 85% boundary | Edge | 5 | 5 | 0.991 | 1.034 |
| Edge disk 85.1% | Cloud | 5 | 5 | 0.968 | 1.099 |
| Cloud CPU 80% boundary, Edge overloaded | Cloud | 5 | 5 | 0.938 | 1.036 |
| Cloud CPU 80.1%, Edge overloaded | Error | 5 | 5 | 17.323 | 81.891 |
| Cloud saturated, Edge healthy | Edge | 5 | 5 | 1.004 | 1.063 |
| Both nodes saturated | Error | 5 | 5 | 0.985 | 1.051 |
| Network latency 200 ms boundary | Cloud | 5 | 5 | 17.421 | 82.596 |
| Network latency 200.1 ms, Low priority | Queue | 5 | 5 | 0.986 | 1.074 |
| Network latency 500 ms, High priority | Edge | 5 | 5 | 0.948 | 1.250 |
| Network latency 500 ms, Medium priority | Queue | 5 | 5 | 17.183 | 81.978 |
| Edge RAM 80%, Cloud healthy | Cloud | 5 | 5 | 1.299 | 1.477 |

**Scenario matrix:** 95/95 requests returned HTTP 200 and 95/95 decisions matched the expected target.

## Sequential CPU transition

| Step | Edge CPU | Expected | Actual | HTTP |
|---:|---:|---|---|---:|
| 1 | 20% | Edge | Edge | 200 |
| 2 | 45% | Edge | Edge | 200 |
| 3 | 65% | Edge | Edge | 200 |
| 4 | 69% | Edge | Edge | 200 |
| 5 | 70% | Edge | Edge | 200 |
| 6 | 70.1% | Cloud | Cloud | 200 |
| 7 | 75% | Cloud | Cloud | 200 |
| 8 | 85% | Cloud | Cloud | 200 |
| 9 | 95% | Cloud | Cloud | 200 |
| 10 | 65% | Edge | Edge | 200 |
| 11 | 40% | Edge | Edge | 200 |
| 12 | 20% | Edge | Edge | 200 |

The sequence demonstrates Edge-to-Cloud offload when CPU exceeds the 70% Low-priority threshold, and Cloud-to-Edge return when Edge CPU falls back within capacity. All 12 transition requests returned HTTP 200 and matched expectations.

## Interpretation

- Threshold comparisons are inclusive: values exactly at 70% CPU/RAM and 85% disk remain eligible for Edge; values just above those limits trigger offload when Cloud and network are viable.
- Cloud CPU at 80% remains eligible; at 80.1%, with Edge overloaded, the scheduler reports no healthy placement.
- Network latency at 200 ms remains usable. At 200.1 ms, Low/Medium priority work is queued; High priority work is pinned to Edge as best effort.
- The policy is deterministic and explainable through its decision reason. This test validates rule execution against supplied snapshots, not live metric collection or real resource saturation.

## Post-test health

- Cloud Node: 1/1 Ready
- Edge Node: 1/1 Ready
- Orchestrator: 1/1 Ready
- Scheduler: 1/1 Ready
- Scheduler health endpoint: HTTP 200, `status=ok`
- Pod restarts: 0

## Evidence

Machine-readable summary and transition evidence: `cloud13_o54_adaptive_placement_20261127.json`.

Validation script staged locally: `o54_scheduler_matrix.py`.

## Conclusion

**O5.4 PASS.** The deployed rule-based scheduler returned the expected placement for all 19 repeated scenarios and all 12 CPU transition steps. All 107 requests succeeded with HTTP 200. No production workload or deployment changes were required.

# O5.9: Concurrent Multi-Priority Adaptive Scheduling Validation

**Date:** 27 November 2026  
**Status:** PASS for the tested concurrent scheduler decision matrix.

## Objective

Validate that the deployed scheduler applies priority-aware placement while Edge is overloaded, Cloud remains healthy, and network suitability differs. Exercise concurrent decisions for Low, Medium and High workloads, then verify placement returns to Edge after resource recovery.

## Method

- Applied bounded CPU pressure to the Edge EC2 node using two worker processes for approximately 50 seconds.
- Fetched Edge and Cloud CPU/RAM/disk snapshots from their live metrics endpoints while Edge was under pressure.
- Submitted 18 scheduler API requests in three rounds, with six requests executing concurrently per round.
- Used stable, independent workload IDs for Low, Medium and High priority.
- Used 80 ms as a usable network-latency input and 250 ms as a constrained network-latency input. These were controlled scheduler inputs, not a physical network impairment. Resource metrics were live.

## Live resource snapshot

| Resource | Edge | Cloud |
|---|---:|---:|
| CPU | 100.0% | 3.5% |
| RAM | 32.1% | 64.5% |
| Disk | 20.1% | 30.3% |

## Concurrent decision results

All 18 requests succeeded without HTTP errors and matched the expected policy behavior.

| Priority | Network input | Expected behavior | Result |
|---|---:|---|---:|
| Low | 80 ms | Cloud offload | 3/3 Cloud |
| Medium | 80 ms | Cloud offload | 3/3 Cloud |
| High | 80 ms | Cloud offload | 3/3 Cloud |
| Low | 250 ms | Queue for retry | 3/3 Queue |
| Medium | 250 ms | Queue for retry | 3/3 Queue |
| High | 250 ms | Edge best-effort execution | 3/3 Edge |

The policy therefore distinguishes priority when Cloud offload is not viable: Low and Medium are deferred, while High is retained on Edge on a best-effort basis. When network latency is within the configured 200 ms limit and Cloud is healthy, all three priorities are offloaded from the overloaded Edge node.

## Recovery validation

After the bounded load ended, live Edge CPU was 0.5%, RAM was 32.2%, and all three priority classes selected Edge with an 80 ms network input.

## Cluster health

All four deployments remained 1/1 Ready: Cloud Node, Edge Node, Orchestrator and Scheduler. All pods reported zero restarts.

## Limitations

- This validates concurrent scheduler decisions, not 18 simultaneous inference executions.
- Network latency values were controlled API inputs; no physical network impairment was introduced.
- High-priority Edge execution under constrained network is explicitly best-effort and is not an SLO guarantee.
- Scheduler placement state is process-local and the deployment uses one scheduler replica.

## Conclusion

**PASS:** The deployed scheduler handled 18/18 concurrent decision requests under live Edge overload, correctly offloaded all priorities when the network input was usable, applied distinct Low/Medium/High behavior when the network input was constrained, and returned all priority classes to Edge after recovery. All deployments remained healthy with zero pod restarts.

Machine-readable evidence: `docs/benchmarks/cloud13_o59_multi_priority_validation_20261127.json`.
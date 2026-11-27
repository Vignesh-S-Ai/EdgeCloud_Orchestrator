# O5.6: Scheduler Hysteresis and Anti-Oscillation Validation

**Date:** 27 November 2026  
**Status:** Implemented, deployed to Kubernetes, and live jitter-validated.

## Objective

Reduce placement oscillation when Edge CPU measurements fluctuate around priority-adjusted placement thresholds, while retaining immediate Edge-to-Cloud offload when overload is detected.

## Implementation

- Added configurable `hysteresis_margin_percent` (default: 5 percentage points).
- Added configurable placement-state TTL (default: 300 seconds) and maximum entries (default: 10,000).
- The decision engine stores the last stable EDGE/CLOUD target by `workload_id`.
- A thread-safe lock makes state lookup, decision, and update atomic within one scheduler process.
- An EDGE-to-CLOUD transition remains immediate when Edge overload and Cloud/network conditions justify offloading.
- A CLOUD-to-EDGE transition requires Edge CPU, RAM, and disk to be at least 5 percentage points below their current priority-adjusted thresholds.
- Priority bias remains intact: Low 0, Medium 5, High 15 percentage points.
- The current request priority is used when calculating recovery thresholds, so priority changes are respected.
- QUEUE and ERROR decisions do not erase the last stable placement. Expiry and bounded entry count prevent unbounded state growth.
- If Cloud is not a viable placement, hysteresis does not pin the workload to Cloud.

## Automated tests

Scheduler test suite: **83 passed**.

New tests cover:
1. Cloud-to-Edge recovery margin.
2. Immediate Edge-to-Cloud overload transition.
3. Threshold jitter suppression.
4. Independent state for different workload IDs.
5. Priority changes using the current priority's thresholds.
6. State expiry.
7. Cloud unavailability not forcing Cloud retention.

## O5.5 versus O5.6 jitter comparison

The same six-step CPU sequences recorded in O5.5 were replayed for Low, Medium, and High priority.

| Priority | O5.5 switches | O5.6 switches |
|---|---:|---:|
| Low | 5 | 1 |
| Medium | 5 | 1 |
| High | 5 | 1 |
| **Total** | **15** | **3** |

**Observed reduction: 80% fewer placement switches** for these deterministic sequences.

O5.5 baseline was the previously captured scheduler API result. O5.6 results were produced by the local stateful DecisionEngine using the same CPU sequences. This comparison was first reproduced locally and then replayed against the deployed Kubernetes scheduler API using synthetic metric snapshots.

## Configuration

| Setting | Default | Meaning |
|---|---:|---|
| `SCHEDULER_HYSTERESIS_MARGIN_PERCENT` | 5.0 | Recovery margin below priority-adjusted CPU/RAM and base disk thresholds |
| `SCHEDULER_PLACEMENT_STATE_TTL_SEC` | 300.0 | Time before an inactive workload's placement history expires |
| `SCHEDULER_PLACEMENT_STATE_MAX_ENTRIES` | 10,000 | Maximum remembered workload placements |

Set the TTL to 0 to disable placement memory and restore stateless decisions.

## Live Kubernetes deployment and validation

- Immutable image: 171743139339.dkr.ecr.ap-south-1.amazonaws.com/edgecloud/scheduler:o56-hysteresis-20261127
- ECR digest: sha256:51a853dc8f4cc76dabdfae6958fb3825f0889a1e3b854a0006e618de3582cca5
- Scheduler rollout completed successfully; scheduler Deployment is 1/1 Ready.
- Live POST /decision jitter replay: 18/18 successful requests across Low, Medium, and High priority; one placement switch per priority (3 total versus 15 in O5.5).
- Cloud node, Edge node, orchestrator, and scheduler Deployments all remained 1/1 Ready; pod restart counts were zero.
- Orchestrator health endpoint returned HTTP 200 with status ok.
- Runtime settings verified: 5-point hysteresis, 300-second state TTL, 10,000-entry cap.

## Limitations and deployment considerations

- Placement state is in-memory and local to one scheduler process. It is cleared on process restart and is not shared across multiple scheduler replicas.
- The current implementation is appropriate for the existing single-process scheduler deployment. A future multi-replica deployment should use shared state or explicit workload affinity.
- The live jitter replay used synthetic metric snapshots submitted to the deployed scheduler API. It did not run inference workloads or validate autonomous telemetry.
- The scheduler image and running Deployment were updated for this milestone.

## Evidence

- `docs/benchmarks/o56_hysteresis_comparison.py`
- `docs/benchmarks/cloud13_o56_hysteresis_comparison_20261127.json`
- `scheduler/tests/test_hysteresis.py`

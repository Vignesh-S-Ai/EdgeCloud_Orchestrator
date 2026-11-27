# O5.5: Scheduler Decision Stability and Priority-Aware Validation

**Result: PASS** for deterministic rule-based decision validation. **Oscillation observed** under deliberately alternating threshold inputs.

## Method
The live scheduler `POST /decision` endpoint was tested with synthetic metric snapshots. The benchmark ran 27 static scenarios five times each (135 requests), plus six-step CPU jitter sequences for Low, Medium, and High priorities (18 requests). Total: **153 requests**. No inference workloads or deployment changes were made.

## Priority thresholds

| Priority | Effective CPU threshold | Effective RAM threshold |
|---|---:|---:|
| Low | 70% | 70% |
| Medium | 75% | 75% |
| High | 85% | 85% |

Disk threshold remained **85%** for all priorities. Values exactly at thresholds were accepted as within capacity; values above the threshold triggered the overloaded path.

## Validation results

- **153/153 HTTP 200**
- **153/153 decisions matched expected targets**
- 27 static scenarios, each repeated five times.
- Verified CPU and RAM below/at/above priority thresholds.
- Verified disk at 85.0% and above at 85.1%.
- Verified poor-network behavior: High priority remained on Edge best-effort; Low and Medium were queued.

## Threshold jitter experiment

| Priority | CPU sequence (%) | Observed placement |
|---|---|---|
| Low | 69.9, 70.1, 69.9, 70.1, 70.0, 70.1 | EDGE → CLOUD → EDGE → CLOUD → EDGE → CLOUD |
| Medium | 74.9, 75.1, 74.9, 75.1, 75.0, 75.1 | EDGE → CLOUD → EDGE → CLOUD → EDGE → CLOUD |
| High | 84.9, 85.1, 84.9, 85.1, 85.0, 85.1 | EDGE → CLOUD → EDGE → CLOUD → EDGE → CLOUD |

Each priority sequence produced five placement switches, **15 switches total**. This is expected from the current stateless threshold policy and is evidence that small oscillations around a threshold can cause placement changes.

## Interpretation and limitation

O5.5 confirms that priority-specific thresholds and boundary behavior are applied consistently by the live scheduler API. It also exposes a design limitation: the current policy has no hysteresis or debounce mechanism, so it does not suppress rapid placement oscillation. Do not describe this milestone as implementing oscillation prevention.

The inputs were synthetic snapshots. This was not a test of live telemetry, inference performance, an ML scheduler, or autonomous adaptation.

## Execution safety
The test issued scheduler decision requests only. No pods were stopped or scaled, and no deployment or scheduler configuration was changed.

SSM command: `2fd17750-4245-4e94-bc0b-008b5fbe86b9` (Success).

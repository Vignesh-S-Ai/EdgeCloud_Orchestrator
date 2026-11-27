"""Deterministic O5.5 vs O5.6 scheduler jitter comparison.

Uses the exact six-step CPU jitter sequences recorded in O5.5. The baseline
switch counts are the captured O5.5 live scheduler results; O5.6 is evaluated
against the local stateful DecisionEngine implementation.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

from scheduler.config import SchedulerSettings
from scheduler.decision_engine import DecisionEngine
from scheduler.models import CloudMetrics, EdgeMetrics, NetworkMetrics, Priority, Target, Workload

SEQUENCES = {
    "low": [69.9, 70.1, 69.9, 70.1, 70.0, 70.1],
    "medium": [74.9, 75.1, 74.9, 75.1, 75.0, 75.1],
    "high": [84.9, 85.1, 84.9, 85.1, 85.0, 85.1],
}
PRIORITIES = {"low": Priority.LOW, "medium": Priority.MEDIUM, "high": Priority.HIGH}


def main():
    settings = SchedulerSettings(
        _env_file=None,
        hysteresis_margin_percent=5.0,
        placement_state_ttl_sec=300.0,
    )
    engine = DecisionEngine(settings)
    cloud = CloudMetrics(
        cpu_percent=30.0, ram_percent=40.0, disk_percent=50.0,
        timestamp=datetime.now(timezone.utc),
    )
    network = NetworkMetrics(latency_ms=20.0)
    result = {}
    total_switches = 0
    for name, values in SEQUENCES.items():
        wl = Workload(
            workload_id=f"o56-jitter-{name}",
            priority=PRIORITIES[name],
            latency_requirement_ms=100.0,
        )
        targets = []
        for cpu in values:
            edge = EdgeMetrics(
                cpu_percent=cpu, ram_percent=40.0, disk_percent=40.0,
                timestamp=datetime.now(timezone.utc),
            )
            targets.append(engine.decide(wl, edge, cloud, network).target.value)
        switches = sum(a != b for a, b in zip(targets, targets[1:]))
        total_switches += switches
        result[name] = {
            "cpu_sequence": values,
            "targets": targets,
            "placement_switches": switches,
        }

    baseline_switches = 15
    reduction = round((baseline_switches - total_switches) / baseline_switches * 100, 2)
    output = {
        "milestone": "O5.6",
        "test": "same-sequence deterministic jitter comparison",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "configuration": {
            "hysteresis_margin_percent": 5.0,
            "placement_state_ttl_sec": 300.0,
            "edge_cpu_threshold_percent": 70.0,
            "priority_bias": {"low": 0.0, "medium": 5.0, "high": 15.0},
        },
        "sequences": result,
        "comparison": {
            "o55_baseline_switches": baseline_switches,
            "o56_switches": total_switches,
            "switch_reduction_percent": reduction,
            "o55_source": "O5.5 captured result: 5 switches per priority, 15 total",
            "o56_method": "local deterministic DecisionEngine using stateful hysteresis",
        },
        "scope": [
            "Synthetic CPU metrics and deterministic local engine test",
            "Not a live Kubernetes scheduler deployment test",
            "No inference workloads, ML policy, or autonomous telemetry",
        ],
    }
    out = Path("docs/benchmarks/cloud13_o56_hysteresis_comparison_20261127.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(output, indent=2) + "\\n", encoding="utf-8")
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()

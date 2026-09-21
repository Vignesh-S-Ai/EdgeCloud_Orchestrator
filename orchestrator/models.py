"""Typed data models for the orchestration request/response.

Reuses the Decision Engine models (:mod:`scheduler.models`) for the workload
and optional metrics snapshots so the orchestrator stays a thin facade over the
verified M1/M2/M3 public APIs. The inference result is kept as an opaque dict
because its schema (``DetectionResult``) is owned by the Edge/Cloud modules and
the orchestrator does not need to interpret it.
"""

from datetime import datetime, timezone
from typing import List, Optional

from pydantic import BaseModel, Field, model_validator

from scheduler.models import (
    CloudMetrics,
    EdgeMetrics,
    NetworkMetrics,
    Workload,
)


class OrchestrateRequest(BaseModel):
    """A workload to place and execute, plus the image to infer on.

    Provide ``edge_metrics``/``cloud_metrics``/``network_metrics`` to force a
    deterministic decision (demo/testing), or omit them to let the scheduler
    fetch live metrics and latency from the running nodes.
    """

    workload: Workload
    image_base64: str = Field(min_length=16)
    confidence: Optional[float] = Field(default=None, ge=0.05, le=0.95)
    annotated: bool = False
    classes: Optional[List[int]] = None

    edge_metrics: Optional[EdgeMetrics] = None
    cloud_metrics: Optional[CloudMetrics] = None
    network_metrics: Optional[NetworkMetrics] = None

    @model_validator(mode="after")
    def _metrics_snapshot_is_complete(self) -> "OrchestrateRequest":
        supplied = [
            self.edge_metrics is not None,
            self.cloud_metrics is not None,
            self.network_metrics is not None,
        ]
        if any(supplied) and not all(supplied):
            raise ValueError(
                "edge_metrics, cloud_metrics and network_metrics must be "
                "provided together"
            )
        return self


class OrchestrationResult(BaseModel):
    """Unified response of one end-to-end orchestration run."""

    workload_id: str
    priority: str
    #: Target chosen by the scheduler: edge | cloud | queue | error.
    selected_target: str
    #: Where inference actually ran (None if the workload was not executed).
    actual_target: Optional[str] = None
    decision_score: float
    decision_reason: str
    fallback_used: bool = False
    fallback_reason: Optional[str] = None
    #: DetectionResult JSON from the executing node (edge /detect or cloud /infer).
    inference_result: Optional[dict] = None
    scheduler_latency_ms: float
    inference_latency_ms: Optional[float] = None
    total_latency_ms: float
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

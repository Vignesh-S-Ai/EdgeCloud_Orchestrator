"""Typed data models for workloads, metrics and scheduling decisions.

Framework-agnostic: no torch, ultralytics or FastAPI internals. The edge and
cloud metrics schemas mirror the JSON produced by the Edge/Cloud Node
``/metrics`` endpoints so the engine can consume them directly.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Priority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class WorkloadType(str, Enum):
    GENERIC = "generic"
    OBJECT_DETECTION = "object_detection"
    IMAGE_CLASSIFICATION = "image_classification"
    VIDEO_STREAM = "video_stream"
    BATCH_JOB = "batch_job"


class Target(str, Enum):
    EDGE = "edge"
    CLOUD = "cloud"
    QUEUE = "queue"
    ERROR = "error"


class Workload(BaseModel):
    """A unit of work to place on the edge or the cloud."""

    workload_id: str
    priority: Priority = Priority.MEDIUM
    workload_type: WorkloadType = WorkloadType.GENERIC
    estimated_compute: Optional[float] = Field(default=None, ge=0.0)
    estimated_inference_ms: Optional[float] = Field(default=None, ge=0.0)
    # End-to-end latency budget for this workload (ms).
    latency_requirement_ms: float = Field(gt=0.0)


class ResourceMetrics(BaseModel):
    """Resource snapshot, schema-compatible with the node /metrics endpoints."""

    cpu_percent: float = Field(ge=0.0, le=100.0)
    ram_percent: float = Field(ge=0.0, le=100.0)
    disk_percent: float = Field(ge=0.0, le=100.0)
    timestamp: datetime


class EdgeMetrics(ResourceMetrics):
    """Snapshot of the Edge Node utilisation."""


class CloudMetrics(ResourceMetrics):
    """Snapshot of the Cloud Node utilisation."""


class NetworkMetrics(BaseModel):
    """Quality of the edge<->cloud network path."""

    latency_ms: float = Field(ge=0.0)
    bandwidth_mbps: Optional[float] = Field(default=None, ge=0.0)


class Decision(BaseModel):
    """Outcome of the placement decision for a workload."""

    workload_id: str
    #: Where the workload should run: edge | cloud | queue | error.
    target: Target
    #: Edge suitability score, 0-100 (100 = edge fully available, 0 = saturated).
    score: float = Field(ge=0.0, le=100.0)
    #: Human-readable explanation, later shown on the dashboard.
    reason: str
    priority: Priority
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

# Final Limitations and Future Work

## Clear Separation

This document separates **actual limitations** (things that exist but are incomplete or constrained) from **optional future improvements** (things that could be done but are not required for capstone validation).

---

## ACTUAL LIMITATIONS

These are real constraints of the current system. They are documented, understood, and do not block capstone submission.

### L1: No Automatic Edge → Cloud Failover

**What:** When the edge node fails, the system returns a 503 error. It does NOT automatically retry on the cloud.

**Why:** This is a deliberate design decision. Edge workloads are chosen for low latency. Falling back to cloud would add 100-200ms of network latency, violating the workload's latency requirement. The system returns an explicit error rather than silently degrading.

**Evidence:** Phase 8 gate 8E — edge failure produces 503 after timeout. Phase 8 report: "Edge failures never failover."

**Impact:** Edge node failure means workloads cannot be processed. The cloud→edge fallback (for HIGH priority) is the only implemented fallback direction.

### L2: PostgreSQL Not Connected

**What:** Terraform provisions an RDS PostgreSQL instance, but no application code connects to it. There are no database schemas, migrations, or ORM usage.

**Why:** The database was planned for Phase 4 but not implemented. The core capstone (orchestration) does not require persistence.

**Impact:** Detection results are not stored. No historical data, no query capability, no audit trail in the database.

### L3: React Dashboard Not Implemented

**What:** Zero frontend code exists. The `frontend/` directory is empty.

**Why:** The dashboard was planned for Phase 7 but not implemented. The backend APIs provide all necessary data.

**Impact:** No visual monitoring interface. The evaluator must use kubectl commands and API calls to observe the system.

### L4: Prometheus/Grafana Not Deployed

**What:** No monitoring stack is deployed. No Prometheus, no Grafana, no metrics-server.

**Why:** Planned for Phase 6 but not executed. In-app psutil metrics are sufficient for the scheduler's needs.

**Impact:** No historical metric dashboards, no alerting, no long-term visibility. Monitoring is limited to in-app /metrics endpoints.

### L5: Public API Unauthenticated HTTP

**What:** The orchestrator is publicly accessible on NodePort :30083 over plain HTTP with no authentication.

**Why:** The Terraform security group has a drift (0.0.0.0/0 instead of /32 edge IP only). No ALB/ingress/TLS termination is configured.

**Impact:** Anyone with network access can send orchestration requests. Acceptable for demo/evaluation; not suitable for production.

**Mitigation:** For demo, the evaluator connects from a known IP. The edge node itself remains fully protected (zero inbound SG rules).

### L6: Synthetic Video Only

**What:** Video processing uses synthetic MP4 files decoded by OpenCV. No physical camera is connected.

**Why:** EC2 instances do not have camera hardware.

**Impact:** The video processing pipeline is validated but not with live camera feed. The `/detect/video` endpoint works correctly with pre-recorded video.

### L7: CPU-Only Inference

**What:** All inference runs on CPU (no GPU). YOLOv8n on CPU takes ~114ms per frame (single-call measurement; average across repeated calls is ~132ms).

**Why:** The c5-class EC2 instances do not have GPU hardware.

**Impact:** Inference is slower than GPU alternatives. ONNX FP32 was tested (Phase 9 9H) but not deployed. INT8 quantization regressed 4× on this hardware.

### L8: psutil Bottleneck Remains

**What:** `psutil.cpu_percent(interval=1.0)` blocks for ~1 second server-side per metrics endpoint. This is the dominant latency component of the scheduler.

**Why:** psutil's CPU measurement requires a 1-second sampling window. This is a fundamental constraint of the library.

**Impact:** Even with concurrent fetch, live uncached /decision takes ~1108ms. Further optimization would require replacing psutil with a non-blocking metric source.

### L9: Short-Term Reliability Only

**What:** Reliability testing covers 15 minutes (Phase 8 8L, 432 requests) and additional benchmark phases (180 requests each). No long-duration (hours/days) testing.

**Why:** Time and resource constraints.

**Impact:** Long-term behavior (memory leaks, connection drift, metric staleness) is not validated.

### L10: No Dynamic Workload Migration

**What:** Once a workload is routed to edge or cloud, it runs to completion there. There is no mechanism to migrate a running workload between nodes.

**Why:** YOLOv8 inference is fast (~114ms). Migration overhead would exceed the inference time.

**Impact:** If a node becomes overloaded mid-inference, the workload completes on the overloaded node.

### L11: hostPort:8000 Cannot Be Removed

**What:** The edge pod uses hostPort:8000 as a bridge between host and pod network namespaces. Removing it breaks ServiceBus connectivity.

**Why:** Phase 9 gate 9D proved that removing hostPort breaks the iptables DNAT chain that allows EdgeCore to reach the pod.

**Impact:** The hostPort is a functional requirement, not an exposure vector (verified by edge SG zero-inbound rules).

### L12: CloudCore REST :9443 Plain HTTP

**What:** KubeEdge v1.23.1's CloudCore REST interface on :9443 does not support TLS. The code has a `// TODO: add tls for router` comment.

**Why:** KubeEdge v1.23.1 does not implement TLS for the Router REST API.

**Impact:** Internal communication between cloud pods and CloudCore is unencrypted. :9443 is not exposed through the security group, so this is not externally exploitable.

---

## OPTIONAL FUTURE IMPROVEMENTS

These are enhancements that could be made but are NOT required for capstone validation. They represent natural next steps for a production system.

### F1: React Dashboard (Phase 7)

**Description:** Build a React frontend that displays live metrics, scheduler decisions, detection results, and system health.

**Priority:** MEDIUM
**Effort:** HIGH (2-3 weeks)
**Impact:** Visual monitoring, demo polish, stakeholder visibility

### F2: PostgreSQL Integration (Phase 4)

**Description:** Connect the cloud node to the provisioned RDS instance. Store detection results, scheduling decisions, and metrics history.

**Priority:** MEDIUM
**Effort:** MEDIUM (1 week)
**Impact:** Data persistence, historical analysis, audit trail

### F3: Prometheus/Grafana Monitoring (Phase 6)

**Description:** Deploy Prometheus for metric collection and Grafana for dashboards. Add ServiceMonitor CRDs for K8s pod metrics.

**Priority:** LOW
**Effort:** MEDIUM (1 week)
**Impact:** Operational monitoring, alerting, long-term visibility

### F4: Automatic Edge → Cloud Failover

**Description:** Implement retry-on-cloud when edge fails, similar to the existing cloud→edge fallback.

**Priority:** LOW
**Effort:** HIGH (1-2 weeks)
**Impact:** Improved resilience, but may violate latency requirements

### F5: TLS on Public API

**Description:** Add TLS termination (via ALB or nginx ingress) and authentication (JWT/OAuth2) to the orchestrator endpoint.

**Priority:** LOW
**Effort:** MEDIUM (1 week)
**Impact:** Security hardening, production readiness

### F6: CI/CD Pipeline

**Description:** Automated build, test, and deploy pipeline using GitHub Actions or AWS CodePipeline.

**Priority:** LOW
**Effort:** MEDIUM (1 week)
**Impact:** Deployment automation, faster iteration

### F7: Physical Camera Integration

**Description:** Connect a USB/IP camera to the edge node for live video feed processing.

**Priority:** LOW
**Effort:** HIGH (2-3 weeks)
**Impact:** Real-world demo, live inference showcase

### F8: GPU Inference

**Description:** Deploy on GPU-enabled EC2 instances (p3/g4dn) for faster YOLOv8 inference.

**Priority:** LOW
**Effort:** HIGH (cost + code changes)
**Impact:** Lower inference latency, higher throughput

### F9: Long-Duration Reliability Testing

**Description:** Run the system for 24-72 hours under sustained load to validate stability.

**Priority:** LOW
**Effort:** LOW (just time)
**Impact:** Confidence in production stability

### F10: KubeEdge Device Management

**Description:** Implement KubeEdge Device CRDs for IoT device management (temperature sensors, cameras, etc.).

**Priority:** LOW
**Effort:** HIGH
**Impact:** Extends the system to real IoT scenarios

---

## Classification Summary

| Category | Items | Capstone Impact |
|----------|-------|----------------|
| Actual Limitations | L1-L12 | None blocking — all documented |
| Optional Future Work | F1-F10 | None required — all enhancements |

**Key point:** The core capstone objectives (edge-cloud orchestration, AI inference, scheduler decision-making, KubeEdge communication, latency benchmarking) are fully demonstrated despite these limitations. The limitations are in supporting infrastructure, not the core innovation.

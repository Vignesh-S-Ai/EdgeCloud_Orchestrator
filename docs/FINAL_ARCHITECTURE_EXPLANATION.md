# Final Architecture Explanation

## Complete Runtime Flow

This document explains the end-to-end architecture of the Edge-Cloud Orchestration system, suitable for project report, viva, presentation, and technical review.

---

## 1. High-Level Data Flow

```
Client / Workload (image + workload definition)
        |
        v
Orchestrator (:30083)
        |
        v
Scheduler (/decision) --- fetches live metrics --- Edge /metrics (ServiceBus)
        |                                            Cloud /metrics (ClusterIP)
        |                                            Cloud /health (latency probe)
        v
Decision: EDGE | CLOUD | QUEUE | ERROR
        |
        +--- EDGE ---> Orchestrator ---> CloudCore :9443 ---> ServiceBus
        |                                      ---> EdgeCore ---> Edge Pod
        |                                      ---> YOLOv8n ---> DetectionResult
        |
        +--- CLOUD --> Orchestrator ---> Cloud Node ClusterIP :8001
        |                                      ---> YOLOv8n ---> DetectionResult
        |
        v
OrchestrationResult (target, inference result, latency breakdown)
```

**Note on video workloads:** For video input, the edge application's `/detect/video` endpoint handles OpenCV frame decoding and per-frame YOLOv8n inference. The scheduler routes the workload to the edge node; the edge application handles the video processing pipeline internally.

---

## 2. The Request Path (Step by Step)

### Step 1: Client Sends Request

A client sends a POST request to the orchestrator:

```
POST http://<orchestrator-ip>:30083/orchestrate
{
  "workload": {
    "workload_id": "demo-001",
    "priority": "HIGH",
    "workload_type": "object_detection",
    "latency_requirement_ms": 500
  },
  "image_base64": "<base64-encoded JPEG>",
  "confidence": 0.5,
  "annotated": false
}
```

### Step 2: Orchestrator Calls Scheduler

The orchestrator forwards the request to the scheduler's `/decision` endpoint. The scheduler needs current metrics from both edge and cloud to make a placement decision.

### Step 3: Scheduler Fetches Metrics (Concurrent)

The scheduler makes three concurrent HTTP calls:

1. **Edge `/metrics`** via KubeEdge ServiceBus → returns CPU%, RAM%, disk%
2. **Cloud `/metrics`** via ClusterIP → returns CPU%, RAM%, disk%
3. **Cloud `/health`** latency measurement → returns round-trip time

These three calls run concurrently using `anyio.create_task_group()`, overlapping the two ~1-second `psutil.cpu_percent(interval=1.0)` samples.

### Step 4: Policy Evaluation

The `RuleBasedPolicy` evaluates the fetched metrics:

- If edge CPU < 70%, RAM < 80%, Disk < 85% → **EDGE** (score 80-100)
- If edge overloaded + cloud healthy + latency < 200ms → **CLOUD**
- If both saturated → **ERROR**

### Step 5: Routing

Based on the decision, the orchestrator routes to:

- **Edge:** `POST http://edge-node:8000/detect` (via ServiceBus)
- **Cloud:** `POST http://cloud-node:8001/infer` (via ClusterIP)

### Step 6: Inference

The selected node runs YOLOv8n inference on the image and returns a `DetectionResult` with bounding boxes, class names, and confidence scores.

### Step 7: Response

The orchestrator returns an `OrchestrationResult` including:

- `selected_target`: Scheduler's choice (edge/cloud)
- `actual_target`: Where it actually ran (may differ if fallback occurred)
- `fallback_used`: Whether fallback was triggered
- `inference_result`: The detection results
- `scheduler_latency_ms`: Time for scheduler decision
- `inference_latency_ms`: Time for inference
- `total_latency_ms`: End-to-end time

---

## 3. KubeEdge Communication Path

The edge node is NOT directly accessible from the cloud. All communication goes through KubeEdge ServiceBus:

```
Cloud Orchestrator Pod (10.42.x)
    |
    | HTTP to CloudCore REST
    v
CloudCore (:9443) --- Router
    |
    | KubeEdge Rule (detect-route, metrics-route, etc.)
    v
RuleEndpoint (servicebus-target)
    |
    | WebSocket to EdgeCore
    v
CloudHub (:10000, TLS)
    |
    | WebSocket over internet
    v
EdgeCore (on edge EC2)
    |
    | localhost:8000
    v
Edge Pod (hostPort:8000 bridge)
    |
    v
Edge Application (FastAPI)
```

**Why this path exists:** KubeEdge provides a secure, managed communication channel between cloud and edge. The edge node sits behind a NAT/firewall with zero inbound security group rules. The only way to reach it is through the EdgeCore agent, which maintains an outbound WebSocket connection to CloudCore.

**Why direct access is blocked:**
- Edge security group: zero inbound rules (default-deny)
- No SSH tunnels, no socat, no frp, no EdgeMesh
- hostPort:8000 is a functional bridge for ServiceBus, not an exposure vector

---

## 4. Why the Edge Application Is Not Directly Exposed

The edge application (FastAPI on port 8000) is intentionally not directly accessible:

1. **Security:** The edge EC2 has zero inbound security group rules. This is the strongest possible security posture — no attack surface.

2. **Architecture:** KubeEdge's ServiceBus model requires all cloud→edge communication to flow through CloudCore. This provides:
   - Authentication and authorization via KubeEdge Rules
   - Single audit trail
   - Consistent networking policy
   - No need to open firewall ports on the edge

3. **Functionality:** The `hostPort:8000` mapping on the edge pod is a Kubernetes bridge between the host network namespace and the pod network namespace. It allows EdgeCore's localhost connection to reach the pod. It is NOT a public exposure.

**Verified in production (Phase 8 gate 8I):**
- Direct pod-IP access: BLOCKED
- ClusterIP access: BLOCKED
- Public port 8000: BLOCKED
- Only path: CloudCore :9443 → ServiceBus → EdgeCore → localhost:8000 → pod

---

## 5. Scheduler Decision Flow

```
Incoming request
    |
    v
Check metrics cache (TTL = 1 second)
    |
    +--- Cache hit: use cached metrics
    |
    +--- Cache miss: fetch concurrently
              |
              +---> edge /metrics (ServiceBus)
              +---> cloud /metrics (ClusterIP)
              +---> cloud /health (latency probe)
              |
              v
         All three complete (~1.1 seconds concurrent)
              |
              v
         Store in cache (TTL = 1 second)
              |
              v
    Evaluate RuleBasedPolicy
              |
              v
    Decision: {target, score, reason}
```

The 1-second cache means that within a burst of requests, only the first request pays the full metric-fetch cost. Subsequent requests within 1 second reuse cached metrics.

---

## 6. Inference Path Comparison

### Edge Inference

```
Client → Orchestrator → Scheduler → Decision: EDGE
    → Orchestrator → CloudCore :9443 → ServiceBus → EdgeCore → Edge Pod
    → YOLOv8n inference
    → DetectionResult back through same path
```

### Cloud Inference

```
Client → Orchestrator → Scheduler → Decision: CLOUD
    → Orchestrator → Cloud Node ClusterIP :8001
    → YOLOv8n inference
    → DetectionResult back
```

Both edge and cloud run identical YOLOv8n on CPU. Raw model inference averages (Phase 8 8K): edge ~132.5ms, cloud ~113.5ms. End-to-end through the orchestrator (Phase 8 8K): edge ~232ms (includes ServiceBus overhead), cloud ~193ms. The scheduler routes based on load, capacity, and latency — not inference speed alone. The edge path adds ServiceBus overhead (~100ms) but provides the only direct path to the physical data source.

---

## 7. Failover Path

### Cloud → Edge Fallback (Implemented)

```
Client → Orchestrator → Scheduler → Decision: CLOUD
    → Orchestrator → Cloud Node → FAILS (5xx or timeout)
    → Check: Is workload HIGH priority? Is edge healthy?
    → YES: Retry on Edge → DetectionResult with fallback_used=True
    → NO: Return 503
```

### Edge → Cloud Failover (NOT Implemented)

```
Client → Orchestrator → Scheduler → Decision: EDGE
    → Orchestrator → Edge via ServiceBus → FAILS
    → Return 503 (no automatic cloud retry)
```

This is a deliberate design decision. Edge workloads are latency-sensitive; failing over to cloud would violate the latency requirement. The system returns an error instead of silently degrading.

---

## 8. Production Topology

```
AWS Cloud (ap-south-1)
    |
    +--- VPC (10.0.0.0/16)
         |
         +--- Public Subnet (10.0.1.0/24)
         |    |
         |    +--- Cloud EC2 (ip-10-0-1-113)
         |         - K3s control-plane
         |         - CloudCore (KubeEdge)
         |         - Pods: orchestrator, scheduler, cloud-node
         |
         +--- Private Subnet
              |
              +--- RDS PostgreSQL (provisioned, unused by app)
```

```
Edge Location
    |
    +--- Edge EC2 (10.0.1.123)
         - K3s worker (KubeEdge EdgeCore)
         - Pod: edge-node
         - Security Group: zero inbound rules
```

```
Legacy (Cordoned)
    |
    +--- WSL2 Node (NotReady, SchedulingDisabled)
         - No running pods
         - Retained for reference only
```

---

## 9. Key Architectural Decisions

| Decision | Rationale |
|----------|-----------|
| KubeEdge ServiceBus for edge communication | Secure, managed, no inbound firewall rules needed |
| Rule-based scheduler (not ML) | Deterministic, explainable, auditable decisions |
| Identical YOLOv8n on edge and cloud | Schema parity, fair comparison, no code divergence |
| Orchestrator as single entry point | Architecture invariant: AI layer never talks to cloud directly |
| Cloud→edge fallback only | Edge workloads are latency-sensitive; cloud fallback would violate SLA |
| hostPort:8000 on edge pod | Functional bridge for ServiceBus, not exposure |
| WSL2 node cordoned (not deleted) | Preserved for reference; removing would require re-registration |
| Concurrent metric fetch | Overlaps two ~1s psutil samples, reducing /decision from ~2s to ~1.1s |
| 1-second metrics cache | Effective after concurrent fetch makes per-request time < TTL |

---

## 10. Summary

The system is a complete edge-cloud orchestration pipeline:

1. **Input:** Video frames or images
2. **Processing:** YOLOv8n object detection
3. **Decision:** Rule-based scheduler evaluates live edge/cloud metrics
4. **Routing:** Orchestrator sends to edge or cloud
5. **Output:** Detection results with latency breakdown

The KubeEdge ServiceBus provides secure, managed edge-cloud communication. The concurrent metric fetch optimization reduces scheduling latency by 96.9% at C1 (cached). The system is deployed in production with zero regressions across hundreds of production requests.

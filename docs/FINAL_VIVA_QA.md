# Final Viva Preparation — Q&A

## PROJECT BASICS

### Q1: Why edge computing?
**A:** Edge computing reduces latency by processing data closer to the source. For real-time AI inference (object detection), round-trip to a cloud data center adds 50-200ms of network latency. Edge inference eliminates this by processing on the local node.

### Q2: Why cloud computing?
**A:** Cloud provides elastic capacity. When the edge node is CPU-saturated (above 70%), workloads can be offloaded to the cloud which has more compute resources. This ensures the system remains responsive under peak load.

### Q3: Why edge-cloud orchestration?
**A:** Neither pure-edge nor pure-cloud is optimal for all scenarios. Edge is low-latency but capacity-limited. Cloud is high-capacity but latency-prone. Orchestration dynamically routes workloads to the optimal location based on live conditions, combining the benefits of both.

### Q4: Why KubeEdge?
**A:** KubeEdge extends Kubernetes to edge nodes, providing: (1) CloudCore/EdgeCore agents for edge-cloud communication, (2) ServiceBus for secure message routing, (3) Rules/RuleEndpoints for traffic management, (4) Integration with K3s for unified orchestration. It solves the networking problem of reaching edge nodes behind NATs/firewalls.

### Q5: Why K3s?
**A:** K3s is a lightweight Kubernetes distribution designed for edge and IoT. It runs on resource-constrained EC2 instances, has a small footprint, and integrates natively with KubeEdge. It provides the same Kubernetes API as full K8s but with less overhead.

### Q6: Why YOLOv8n?
**A:** YOLOv8n (nano variant) is the smallest YOLOv8 model (~6MB). It provides real-time object detection on CPU (~114ms per frame) without requiring GPU hardware. This makes it suitable for edge deployment where GPU resources may not be available.

### Q7: Why FastAPI?
**A:** FastAPI provides async Python HTTP with automatic request validation (Pydantic), OpenAPI documentation, and high performance. The async nature allows concurrent metric fetching without blocking. It's used consistently across all four services.

### Q8: Why Docker/containerd?
**A:** Docker provides containerized deployment. K3s uses containerd as its container runtime. Each service (edge, cloud, scheduler, orchestrator) runs in its own container with isolated dependencies, reproducible builds, and Kubernetes-native deployment.

---

## ARCHITECTURE

### Q9: How does a request reach the edge?
**A:** Client → Orchestrator :30083 → Scheduler /decision → Decision: EDGE → Orchestrator → CloudCore :9443 → ServiceBus → EdgeCore → Edge pod :8000 → YOLOv8n → DetectionResult back through the same path.

### Q10: Why is CloudCore needed?
**A:** CloudCore is KubeEdge's cloud-side agent. It maintains a WebSocket connection to EdgeCore, translates HTTP requests to the ServiceBus protocol, and provides the only working path to the edge node. Without CloudCore, the edge is unreachable from the cloud.

### Q11: What is EdgeCore?
**A:** EdgeCore is KubeEdge's edge-side agent. It runs on the edge EC2, maintains an outbound WebSocket to CloudCore, and proxies requests to the local edge pod. It enables the edge to receive commands from the cloud without exposing any inbound ports.

### Q12: What is ServiceBus?
**A:** ServiceBus is KubeEdge's message routing layer. It maps HTTP requests from CloudCore to the correct edge pod using Rules and RuleEndpoints. It's the only way to communicate with edge pods from the cloud.

### Q13: Why can't the cloud directly reach the edge pod?
**A:** Three reasons: (1) Edge security group has zero inbound rules (default-deny), (2) The edge sits behind NAT with no public IP mapping for port 8000, (3) The architecture requires all communication to flow through KubeEdge for security and audit. This is verified in Phase 8 gate 8I — all direct access attempts are blocked.

### Q14: Why is the edge port 8000 blocked?
**A:** Port 8000 is blocked by the edge security group (zero inbound rules). The `hostPort:8000` mapping is a Kubernetes bridge between host and pod network namespaces, allowing EdgeCore's localhost connection to reach the pod. It is not a public exposure vector.

---

## SCHEDULER

### Q15: How does scheduling work?
**A:** The scheduler fetches live metrics from edge and cloud, evaluates a rule-based policy, and returns a decision. The policy checks: Is edge healthy (CPU < 70%, RAM < 80%, Disk < 85%)? → EDGE. Is edge overloaded but cloud healthy with acceptable latency? → CLOUD. Both saturated? → ERROR.

### Q16: What metrics are used?
**A:** CPU utilization percentage, RAM utilization percentage, and disk utilization percentage from both edge and cloud nodes. Additionally, cloud /health latency is measured to assess network quality. All metrics are fetched via HTTP endpoints (/metrics, /health).

### Q17: What is the CPU threshold?
**A:** Edge CPU threshold is 70%. Below 70%, the edge is considered healthy and workloads are routed there. Above 70%, the edge is considered overloaded and cloud offload is considered.

### Q18: What happens when edge is overloaded?
**A:** If edge CPU > 70% (or RAM > 80%, Disk > 85%), the scheduler checks cloud metrics. If cloud is healthy and latency < 200ms → CLOUD. If cloud is also overloaded → ERROR. If cloud is unavailable and priority is HIGH → EDGE (best effort). If priority is LOW/MED → QUEUE.

### Q19: What happens when cloud is unavailable?
**A:** If the cloud /metrics fetch fails, the scheduler cannot confirm cloud health. For HIGH-priority workloads, it routes to edge as best effort. For LOW/MED priority, it returns QUEUE. The orchestrator's fallback mechanism (cloud→edge) handles runtime cloud failures.

### Q20: What is the difference between QUEUE and ERROR?
**A:** QUEUE means the workload is deferred (no capacity available now, will retry later). ERROR means the system cannot process the workload at all (both edge and cloud are saturated). QUEUE is for LOW/MED priority; ERROR is for any priority when both are saturated.

### Q21: Why is latency measured live?
**A:** The scheduler measures cloud /health latency on every /decision call (unless cached). This ensures the routing decision reflects current network conditions, not stale data. If network latency degrades, the scheduler will prefer edge even if cloud compute is available.

---

## OPTIMIZATION

### Q22: What was the 10E-6 bottleneck?
**A:** The scheduler made three sequential HTTP calls: edge /metrics, cloud /metrics, cloud /health. Each /metrics call triggered `psutil.cpu_percent(interval=1.0)`, blocking for ~1 second server-side. Sequential total: ~2 seconds. This exceeded the 1-second metrics cache TTL, making the cache ineffective.

### Q23: Why were metrics taking approximately 1 second?
**A:** `psutil.cpu_percent(interval=1.0)` is a blocking call that measures CPU utilization over a 1-second window. It's called by the edge and cloud /metrics endpoints. This is the dominant component of the ~2-second sequential fetch.

### Q24: What did psutil.cpu_percent(interval=1.0) do?
**A:** It sampled CPU utilization over a 1-second interval, blocking the calling thread. Both edge and cloud /metrics endpoints call this. Two sequential calls = 2 seconds. This is a server-side measurement cost, not network latency.

### Q25: Why did sequential requests cost approximately 2 seconds?
**A:** Three sequential calls: edge /metrics (~1010ms) + cloud /metrics (~1005ms) + cloud /health (~3ms) = ~2018ms. The two /metrics calls are the bottleneck because each waits for psutil's 1-second CPU sample.

### Q26: Why use anyio.create_task_group()?
**A:** `anyio.create_task_group()` runs the three metric-fetch calls concurrently while maintaining compatibility with both asyncio and trio backends (the project tests on both). It's the async-agnostic way to achieve concurrency in Python.

### Q27: Why not asyncio.gather()?
**A:** The project's test suite runs on both asyncio and trio backends (`@pytest.mark.anyio`). `asyncio.gather()` only works on asyncio. `anyio.create_task_group()` works on both, maintaining the dual-backend testing requirement.

### Q28: How did concurrency reduce latency?
**A:** By running the two ~1-second psutil samples concurrently instead of sequentially, they overlap. Sequential: ~2018ms. Concurrent: ~1108ms (the two 1-second samples run in parallel, plus ~3ms health probe + overhead). This is a ~46.7% reduction in the uncached path.

### Q29: What is the difference between cached and uncached latency?
**A:** Cached: metrics are reused from the 1-second TTL cache (C1=66ms because 12 sequential requests fit within TTL). Uncached: each request fetches fresh metrics (1107.7ms). The cache is effective because concurrent fetch reduced per-request time below the 1-second TTL.

---

## AI

### Q30: How does YOLOv8 inference work?
**A:** YOLOv8n is a convolutional neural network for object detection. Input: a JPEG image (base64-encoded). Processing: the model runs through backbone → neck → head layers to detect objects. Output: bounding boxes with class labels and confidence scores. On CPU, this takes ~114ms per frame.

### Q31: What happens on the edge?
**A:** The edge receives an image via /detect (through ServiceBus), runs YOLOv8n inference, and returns a DetectionResult with bounding boxes, class names, confidence scores, and metadata (inference time, image dimensions).

### Q32: What happens on the cloud?
**A:** The cloud receives an image via /infer (via ClusterIP), runs identical YOLOv8n inference, and returns an identical DetectionResult. The code is intentionally the same to ensure schema parity.

### Q33: How was inference verified?
**A:** Phase 8 gate 8M: 31-key schema parity check (identical keys between edge and cloud responses). Byte-identical detection results. Phase 8 gate 8C: real `cup` detection with confidence 0.870. Phase 9 9F: video processing with per-frame detection.

### Q34: What is schema parity?
**A:** Edge and cloud return responses with identical structure (same 31 JSON keys), same data types, and byte-identical detection values. This ensures workloads can be routed to either location transparently — the client sees the same response regardless of where inference ran.

### Q35: Why is CPU inference used?
**A:** The EC2 instances (c5-class) do not have GPU hardware. YOLOv8n on CPU provides ~114ms inference latency on a single call (Phase 8 8C), with repeated-call averages around ~132ms (Phase 8 8K). This is acceptable for the demo. GPU would further reduce latency but is not available in the current infrastructure.

---

## FAILOVER

### Q36: Does edge failover to cloud?
**A:** No. When the edge fails, the system returns a 503 error. This is a deliberate design decision — edge workloads are latency-sensitive, and failing over to cloud would violate the latency requirement.

### Q37: Does cloud failover to edge?
**A:** Yes, but only for HIGH-priority workloads. If the cloud returns 5xx or is unreachable, and the edge is healthy, the orchestrator retries on the edge and sets `fallback_used=True`.

### Q38: Under what priority conditions?
**A:** Cloud→edge fallback requires: (1) cloud fails (5xx or transport error), (2) workload priority is HIGH, (3) edge /health confirms model_loaded. LOW and MED priority workloads do not fall back — they return 503.

### Q39: Why is edge→cloud automatic failover not implemented?
**A:** Edge workloads are chosen for low latency. If the edge fails, falling back to cloud would add 100-200ms of network latency, violating the workload's latency requirement. It's better to return an explicit error than silently degrade. This is documented as a design decision in Phase 8.

---

## PERFORMANCE

### Q40: What is the baseline?
**A:** 10E-2 baseline (sequential, no cache): /decision C1=2100.9ms, C8=3128.3ms. This is the original production scheduler before any optimization.

### Q41: What is the optimized result?
**A:** 10E-6 (concurrent fetch + cache): /decision C1=66.0ms (cached), C8=1246.8ms. Live uncached /decision = 1107.7ms.

### Q42: Why is C1 66 ms?
**A:** At concurrency 1, 12 sequential requests complete within the 1-second TTL cache window. After the first request (which fetches fresh metrics), the remaining 11 hit the cache. This is the combined effect of concurrent fetch (reducing per-request time below TTL) and the metrics cache.

### Q43: What is the uncached result?
**A:** 1107.7ms (live uncached /decision). This measures the pure concurrent fetch effect without cache benefit. Improvement: sequential sum 2016.9ms → concurrent 1107.7ms (-46.7%).

### Q44: What happens as concurrency increases?
**A:** Latency increases because the scheduler handles more concurrent requests. C1=66ms (cache hit), C2=338ms, C4=680ms, C8=1247ms. The increase is roughly linear — no catastrophic degradation or failure.

### Q45: What is the /orchestrate latency?
**A:** /orchestrate includes scheduler decision + inference. C1=415.6ms (scheduler ~66ms cached + inference ~117ms + overhead). This is the full end-to-end workload processing time.

### Q46: What does the benchmark actually measure?
**A:** /decision: time to fetch edge/cloud metrics, evaluate policy, return decision. /orchestrate: time for full pipeline (decision + routing + inference + response). Neither includes client network time.

---

## PRODUCTION

### Q47: How many nodes?
**A:** 2 active nodes: cloud control-plane (ip-10-0-1-113) and edge EC2 (10.0.1.123). 1 cordoned node: WSL2 (NotReady, SchedulingDisabled). Total 4 pods: orchestrator, scheduler, cloud-node, edge-node.

### Q48: Where is the scheduler deployed?
**A:** On the cloud control-plane node (ip-10-0-1-113), pinned via nodeSelector. This ensures it never lands on the edge node, which would cause network routing issues (edge pod network 10.244.x is disjoint from cloud 10.42.x).

### Q49: Why is WSL2 cordoned?
**A:** WSL2 was a legacy development node that re-registered after being deleted. It's marked SchedulingDisabled to prevent pods from landing on it. It has no running pods and serves no function.

### Q50: What happens if the scheduler lands on the edge node?
**A:** The scheduler would be on the 10.244.x pod network, which is unreachable from cloud-side pods (10.42.x). The ClusterIP endpoints for cloud-node and scheduler would be unreachable, causing /decision and /orchestrate to fail. This was the root cause of the 10E-5 placement issue.

### Q51: How was production regression checked?
**A:** Pre-deployment: 14/14 safety gate checks (pods, services, rules, endpoints, nodeSelector). Post-deployment: 11/11 functional regression checks (health, metrics, detect, video, routing). All phases (8-10) verified zero regressions.

---

## SECURITY

### Q52: Is the edge directly exposed?
**A:** No. The edge security group has zero inbound rules (default-deny). All access goes through KubeEdge ServiceBus (CloudCore :9443 → EdgeCore). Verified in Phase 8 gates 8I and 8J.

### Q53: Is port 8000 public?
**A:** No. Port 8000 is blocked by the edge security group. The hostPort:8000 mapping is a functional bridge for ServiceBus, not a public exposure.

### Q54: Is the orchestrator HTTPS?
**A:** No. The orchestrator runs on NodePort :30083 over plain HTTP with no authentication. This is documented as a known limitation (Phase 10 10D). Acceptable for demo purposes.

### Q55: Is authentication implemented?
**A:** No. The public orchestrator endpoint has no authentication. Internal service-to-service communication relies on Kubernetes network policies and KubeEdge's ServiceBus authorization.

### Q56: What are the documented security limitations?
**A:** (1) Orchestrator :30083 public HTTP, no auth, (2) CloudCore REST :9443 plain HTTP (internal only, SG-blocked), (3) No TLS on data plane, (4) Terraform SG drift (0.0.0.0/0 instead of /32). None are capstone-blocking.

---

## LIMITATIONS

### Q57: Why no PostgreSQL integration?
**A:** Terraform provisions an RDS instance, but no application code connects to it. The database was planned for Phase 4 but not implemented. The core capstone (orchestration) does not require persistence.

### Q58: Why no React dashboard?
**A:** Zero frontend code exists. The dashboard was planned for Phase 7 but not implemented. The scheduler and orchestrator APIs provide all necessary data for a dashboard.

### Q59: Why no Prometheus/Grafana?
**A:** Not deployed. Planned for Phase 6 but not executed. In-app psutil metrics are sufficient for the scheduler's needs.

### Q60: Why no physical camera?
**A:** The EC2 instances have no camera hardware. Video testing uses synthetic MP4 files decoded by OpenCV. This is sufficient to validate the video processing pipeline.

### Q61: Why no GPU?
**A:** The c5-class EC2 instances do not have GPU hardware. YOLOv8n on CPU provides acceptable latency (~114ms). GPU would further reduce latency but requires different instance types.

### Q62: Why no automatic edge→cloud failover?
**A:** Deliberate design decision. Edge workloads are latency-sensitive. Cloud fallback would violate latency requirements. The system returns explicit errors instead of silently degrading.

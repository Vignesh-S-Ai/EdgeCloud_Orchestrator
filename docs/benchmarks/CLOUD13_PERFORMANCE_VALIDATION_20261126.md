# CLOUD-13 Performance Validation - 26 November 2026

## 1. Matched inference service benchmark
- 5 warm-ups and 100 measured requests per target, 25 at each concurrency C1/C2/C4/C8.
- Identical Sampleimage.jpg (37,610 bytes, SHA-256 cacdb9bc5e08c713231c1e45d3c620d40ef2145f1a8c3daef3dc0338584881a1), confidence 0.25, annotated=false.
- All 200 requests returned HTTP 200. Both targets returned three detections: book, clock, cup.
- Cloud mean RTT 353.72 ms, median 282.38 ms, p95 812.04 ms; mean inference 339.66 ms.
- Edge mean RTT 304.91 ms, median 186.45 ms, p95 722.53 ms; mean inference 281.91 ms.
- Mean RTT by concurrency, Cloud / Edge: C1 121.23 / 97.27 ms; C2 217.87 / 171.56 ms; C4 382.06 / 327.24 ms; C8 693.72 / 623.57 ms.
- Boundary: Cloud called directly via localhost /infer; Edge called through CloudCore REST Router /detect. This is an inference-path comparison, not the complete orchestrator path. Single image and one run only.

## 2. Full orchestrator benchmark
- 5 warm-ups and 100 measured requests at C1/C2/C4/C8, with live runtime metrics and the same image.
- 100/100 HTTP 200; 100 selected Edge; no fallback. All responses returned three detections.
- Mean scheduler / inference / total latency:
  - C1: 1107.42 / 116.50 / 1223.95 ms
  - C2: 1131.73 / 122.88 / 1254.63 ms
  - C4: 1461.64 / 211.44 / 1673.11 ms
  - C8: 2315.56 / 568.60 / 2884.18 ms
- Overall total mean 1758.97 ms, median 1295.94 ms, p95 3289.16 ms.
- Boundary: All measured requests selected Edge, so Cloud fallback was not exercised.

## 3. Scheduler-only live decision benchmark
- Executed inside the orchestrator pod against scheduler.edgecloud.svc:8002, matching the real in-cluster route.
- 5 warm-ups and 100 measured requests; 100/100 successful decisions, all selected Edge.
- Mean latency by C1/C2/C4/C8: 1111.89 / 1303.29 / 1476.33 / 2044.66 ms.
- This isolates scheduler live-metrics decision latency from image inference.

## 4. Isolated metrics-cache experiment
- No cache (TTL 0): 10 decisions, mean 1193.53 ms, median 1150.29 ms.
- TTL 2 seconds: first cold decision 1182.59 ms; following 9 warm decisions mean 66.19 ms, median 85.01 ms. Ten-request mean including cold start 177.83 ms.
- This was an isolated in-process test inside the scheduler pod. It did not modify the live Deployment.
- Only /metrics resource snapshots are cached; /health latency measurement remains live. TTL is bounded by the implementation.

## 5. Interpretation and next action
- The inference route is operational and returns consistent detections in this test.
- Full orchestrator latency is dominated by live scheduler metrics collection at low concurrency; contention increases scheduler and inference time at C4/C8.
- Scheduler deployment currently has no SCHEDULER_METRICS_TTL_SEC environment setting, so the code default of zero disables metrics caching.
- Next controlled experiment: back up the scheduler Deployment, apply SCHEDULER_METRICS_TTL_SEC=2, verify rollout, repeat the full orchestrator benchmark, and compare. Roll back if health or decision quality regresses.
- Edge /health remains HTTP 200 but reports degraded because camera_open=false. Camera capture is not verified.
## 6. Live scheduler metrics-cache rollout and post-change benchmark
- Before change, the scheduler Deployment had no SCHEDULER_METRICS_TTL_SEC environment variable; code default was 0.0 (cache disabled).
- Backed up the local scheduler Deployment manifest to scheduler-deployment-before-ttl-20261126.yaml and the live Deployment to /tmp/cloud13-scheduler-deployment-before-ttl-20261126.yaml on Cloud EC2.
- Added SCHEDULER_METRICS_TTL_SEC=2 to the local infra/k3s/scheduler-deployment.yaml and applied the environment variable to the live scheduler Deployment. Rollout succeeded; one scheduler replica is 1/1 Ready.
- Post-rollout five-request smoke test: all HTTP 200, selected Edge, 3 detections each. Scheduler latency: 1191.18 ms cold, then 30.31, 28.93, 29.19 and 30.43 ms.
- Repeated full orchestrator benchmark: 100/100 HTTP 200; all selected Edge; no fallback.
- Post-TTL overall: scheduler mean 487.85 ms (median 204.13 ms); total mean 811.88 ms (median 497.18 ms; p95 2001.96 ms).
- Pre/post comparison: scheduler mean reduced 67.6%; total mean reduced 53.8%; total median reduced 61.6%; total p95 reduced 39.1%.
- Post-TTL mean total latency by C1/C2/C4/C8: 268.01 / 487.80 / 1027.22 / 1464.51 ms. Scheduler means: 124.63 / 317.51 / 657.50 / 851.74 ms.
- Interpretation: the 2-second bounded resource-metrics cache materially reduced scheduler and full-workflow latency. The first request after cache expiry remains slower, and high concurrency still increases inference and scheduler latency. Do not claim that YOLO model inference itself became faster; inference mean was higher in this second run.
- Final health snapshot after rollout: orchestrator HTTP 200 status ok; Cloud HTTP 200 status ok; Edge HTTP 200 but body degraded because camera_open=false and model_loaded=true. CloudCore, Cloud node, Edge node, Scheduler and Orchestrator pods were Ready.
- The live configuration change is reversible. Previous live YAML is backed up on Cloud EC2; previous local manifest is retained in docs/benchmarks.

## 7. CloudCore RBAC audit and least-privilege correction
- CloudCore runs as ServiceAccount kubeedge/cloudcore. CloudCore logs showed forbidden list/watch calls for devicestatuses.devices.kubeedge.io.
- The installed CloudCore ClusterRole covered devices, devicemodels and their status resources, but omitted the separate devicestatuses resource.
- KubeEdge v1.23 introduced DeviceStatus as a separate CRD. An additive, least-privilege ClusterRole and ClusterRoleBinding were created: cloudcore-devicestatus-reader, granting only get/list/watch on devices.kubeedge.io/devicestatuses.
- Verified with kubectl auth can-i: get=yes, list=yes, watch=yes. kubectl get devicestatuses returned No resources found (not Forbidden). After a 30-second retry window, no new DeviceStatus Forbidden errors were observed. CloudCore was not restarted; Edge health remained HTTP 200.
- Remaining warning: CloudCore continues to log unknown fields failMessages and successMessages around UpdateRulestatus successfully. The installed Rule CRD schema contains both status properties; RuleEndpoint has no status schema, and no Rule status subresource is configured. A server-side dry-run of a normal Rule status patch accepted those properties. No speculative CRD patch was applied because routing works and the exact origin of the CloudCore warning has not been conclusively identified.
- Evidence: infra/k3s/cloudcore-devicestatus-rbac.yaml and docs/benchmarks/cloud13_cloudcore_rbac_audit_20261126.json.

## 8. Controlled Cloud-offload branch validation
- Five full /orchestrate requests with explicit synthetic Edge/Cloud/network metrics forced the Cloud branch. All 5 returned HTTP 200; selected and actual target were Cloud; no fallback; each returned 3 detections (book, clock, cup).
- Scheduler mean 19.15 ms. First Cloud inference cold 2794.35 ms; four warm requests averaged 191.92 ms inference and 212.28 ms total.
- This validates the controlled Cloud offload path, not live-metrics Cloud selection or automatic failover.

## 9. Repository regression validation
- python -m pytest -q: 131 passed in 20.84 seconds (exit code 0).
- YAML parsing succeeded for scheduler Deployment and CloudCore DeviceStatus RBAC manifests. git diff --check found no whitespace errors; Git only reported line-ending conversion warnings for existing working-copy files.


## 10. Bidirectional orchestrator failover implementation and live validation
- Implemented symmetric high-priority fallback in orchestrator/service.py: Edge inference failure -> health-check Cloud -> Cloud inference; Cloud inference failure -> health-check Edge -> Edge inference.
- Preserved safety policy: only high-priority workloads fail over; 4xx request errors are returned without retry; the alternate service must pass its health endpoint; if fallback inference also fails, return HTTP 503 with both failure details.
- Added five regression tests for Edge-to-Cloud success, non-high-priority no-fallback, Cloud-unhealthy no-fallback, 4xx no-fallback, and fallback-target failure. Updated the prior Edge-failure 503 test to assert the medium-priority policy.
- Full repository test suite: python -m pytest -q -> 136 passed, 0 failed, 13.22 seconds.
- Built and pushed immutable ECR tag failover-20261126, digest sha256:3b561a55d8430d853226c28c28f420428657e0ca0870fe129683a27f5629a910. Docker Hub TLS handshake timed out when resolving the Python base image, so the final code-only layer was built from the already-present local orchestrator:0.1.0 base image (digest sha256:3164699333bf732646c315b0c52be6a4ee9222136b4ed014a6a874c85ee44969); no dependencies changed.
- Deployed the immutable image to the live orchestrator Deployment. Rollout completed with 1/1 Ready. The local infra/k3s/orchestrator-deployment.yaml points to the immutable tag; prior manifest backed up as orchestrator-deployment-before-failover-20261126.yaml.
- Edge-to-Cloud live route failure injection: temporarily set only ORCHESTRATOR_EDGE_URL=http://127.0.0.1:9. A high-priority request selected Edge, encountered connection refused, health-checked Cloud, then completed on Cloud. HTTP 200, fallback_used=true, 3 detections, scheduler 151.62 ms, inference 144.26 ms, total 456.22 ms, client RTT 461.34 ms. Original Edge URL restored automatically and verified.
- Cloud-to-Edge live route failure injection: temporarily set only ORCHESTRATOR_CLOUD_URL=http://127.0.0.1:9. A high-priority request selected Cloud, encountered connection refused, health-checked Edge, then completed on Edge. HTTP 200, fallback_used=true, 3 detections, scheduler 194.01 ms, inference 171.63 ms, total 491.78 ms, client RTT 497.97 ms. Original Cloud URL restored automatically and verified.
- Injection scope: upstream routes from the orchestrator were made unreachable; neither inference Deployment was stopped or scaled down. This safely validates connection-failure handling and fallback, not process-crash or node-loss recovery.
- Post-restore smoke: Edge and Cloud normal routing both returned HTTP 200, selected and actual targets matched, fallback_used=false, and 3 detections. All four application Deployments were 1/1 Ready. Cloud health ok; Edge HTTP health still reports degraded only because camera_open=false while model_loaded=true.
- Full evidence: cloud13_bidirectional_failover_20261126.json.

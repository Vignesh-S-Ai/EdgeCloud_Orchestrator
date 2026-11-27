# CLOUD-13 O4.3 End-to-End Failover & Recovery Validation

**Date:** 27 November 2026 | **Environment:** AWS ap-south-1, K3s, namespace `edgecloud`

| Scenario | Selected | Actual | Fallback | HTTP | Client RTT | Detections |
|---|---|---|---|---:|---:|---:|
| Cloud Service isolated | Cloud | Edge | Yes | 200 | 431.82 ms | 3 |
| Cloud restored | Cloud | Cloud | No | 200 | 203.80 ms | 3 |
| Edge upstream route failed | Edge | Cloud | Yes | 200 | 470.01 ms | 3 |
| Edge route restored | Edge | Edge | No | 200 | 270.19 ms | 3 |

## Cloud: real Kubernetes Service isolation

Changed the `cloud-node` Service selector to a non-matching label and verified its endpoint list was empty. A high-priority request selected Cloud, failed to connect because no endpoints existed, and completed inference on Edge. HTTP 200, 3 detections; scheduler 117.13 ms, inference 111.53 ms, total 426.55 ms, client RTT 431.82 ms. Restored the selector and endpoint `10.42.0.9:8001`; the next request ran on Cloud without fallback (HTTP 200, 3 detections).

## Edge: actual KubeEdge route failure

The production Edge path is `http://10.0.1.95:9443/edge-ec2-node/edgecloud`. The edge-node ClusterIP Service route was tested separately and was not reachable from the orchestrator, so Service selector isolation would not interrupt the production path. Injected connection refusal on the actual KubeEdge upstream URL using loopback port 9. A high-priority request selected Edge and completed on Cloud (HTTP 200, 3 detections; scheduler 68.93 ms, inference 195.88 ms, total 464.65 ms, client RTT 470.01 ms). Restored the original KubeEdge URL; the next request ran on Edge without fallback (HTTP 200, 3 detections).

## Safety and final health

- Automatic exit trap restored the Cloud selector and both original orchestrator URLs.
- No inference pods stopped, deleted, or scaled.
- Cloud, Edge, orchestrator, scheduler deployments all 1/1 Ready.
- Cloud endpoint `10.42.0.9:8001`; Edge endpoint `10.0.1.226:8000`.
- Orchestrator health HTTP 200, `ok`.
- Edge health HTTP 200, `degraded`, `model_loaded=true`, `camera_open=false`.

**Scope:** PASS for Cloud Kubernetes Service isolation failover/recovery and Edge actual KubeEdge route failure failover/recovery. Does not claim Edge Service endpoint isolation or Edge node failure.
# Final Demo Runbook

## Overview

A reliable 5-10 minute live demonstration of the Edge-Cloud Orchestration system.

**Prerequisites:**
- SSH access to cloud EC2 (i-07ecfbdd7781c5ef5)
- kubectl configured with edgecloud namespace
- All 4 pods Running, RESTARTS=0

---

## Demo Step 1: Production Topology

**Command:**
```bash
kubectl get nodes -o wide
```

**Expected output:**
```
NAME                           STATUS     ROLES                  AGE   VERSION
ip-10-0-1-113.ap-south-1...   Ready      control-plane,master   ...   v1.28.4+k3s1
edge-ec2-node                  Ready      <none>                 ...   v1.28.4+k3s1
wsl2-edge-node                 NotReady   <none>                 ...   v1.28.4+k3s1
```

**What the evaluator should notice:**
- 2 Ready nodes (cloud CP + edge)
- 1 NotReady,SchedulingDisabled (WSL2, legacy)
- K3s running on both active nodes

**Backup evidence:** Phase 8 8B, Phase 10 10E-6 production validation

---

## Demo Step 2: Edge Node Ready

**Command:**
```bash
kubectl describe node edge-ec2-node | grep -A 5 "Conditions:"
```

**Expected output:**
```
Conditions:
  Type             Status  ...  Reason                       Message
  ----             ------       ------                       -------
  MemoryPressure   False        KubeletHasEnoughMemory       ...
  DiskPressure     False        KubeletHasNoDiskPressure     ...
  Ready            True         KubeletReady                 ...
```

**What the evaluator should notice:**
- Edge node is Ready
- No pressure conditions
- KubeEdge EdgeCore running on this node

**Backup evidence:** Phase 8 8B baseline, all Phase 8-10 gates

---

## Demo Step 3: Four Production Pods

**Command:**
```bash
kubectl get pods -n edgecloud -o wide
```

**Expected output:**
```
NAME                            READY   STATUS    RESTARTS   AGE   IP           NODE
cloud-node-...                  1/1     Running   0          ...   10.42.0.19   ip-10-0-1-113
edge-node-...                   1/1     Running   0          ...   10.244.0.6   edge-ec2-node
orchestrator-...                1/1     Running   0          ...   10.42.0.18   ip-10-0-1-113
scheduler-8f4bb9b96-lhlpj      1/1     Running   0          ...   10.42.0.20   ip-10-0-1-113
```

**What the evaluator should notice:**
- All 4 pods Running, READY 1/1
- RESTARTS=0 across all pods
- Scheduler, orchestrator, cloud-node on cloud CP
- Edge-node on edge-ec2-node
- Different pod IPs: cloud=10.42.x, edge=10.244.x

**Backup evidence:** Phase 10 10E-6 production validation, all regression checks

---

## Demo Step 4: Scheduler Health

**Command:**
```bash
kubectl exec -n edgecloud deploy/orchestrator -- python -c "
import httpx
r = httpx.get('http://scheduler-svc:8002/health')
print(f'Status: {r.status_code}')
print(f'Body: {r.json()}')
"
```

**Expected output:**
```
Status: 200
Body: {'status': 'ok', 'service': 'scheduler', 'version': '10e-6', ...}
```

**What the evaluator should notice:**
- Scheduler is healthy
- Version confirms 10e-6 image
- Orchestrator can reach scheduler via ClusterIP

**Backup evidence:** Phase 10 10E-6 functional gate, 11/11 PASS

---

## Demo Step 5: Edge Health via ServiceBus

**Command:**
```bash
kubectl exec -n edgecloud deploy/orchestrator -- python -c "
import httpx
r = httpx.get('http://scheduler-svc:8002/decision', params={
    'edge_url': 'http://edge-node-svc:8000',
    'cloud_url': 'http://cloud-node-svc:8001'
})
print(f'Status: {r.status_code}')
d = r.json()
print(f'Target: {d[\"target\"]}')
print(f'Score: {d[\"score\"]}')
print(f'Reason: {d[\"reason\"]}')
"
```

**Expected output:**
```
Status: 200
Target: edge
Score: 80-100
Reason: edge_healthy
```

**What the evaluator should notice:**
- Scheduler made a real decision
- Target is edge (edge is healthy)
- Score reflects edge fitness
- Metrics were fetched via ServiceBus (edge) and ClusterIP (cloud)

**Backup evidence:** Phase 9 9B, Phase 10 10E-6

---

## Demo Step 6: Real YOLO Detection

**Command:**
```bash
kubectl exec -n edgecloud deploy/orchestrator -- python -c "
import httpx, base64
with open('/app/Sampleimage.jpg', 'rb') as f:
    img_b64 = base64.b64encode(f.read()).decode()
r = httpx.post('http://edge-node-svc:8000/detect', json={
    'image_base64': img_b64,
    'confidence': 0.5,
    'annotated': False
}, timeout=30)
print(f'Status: {r.status_code}')
d = r.json()
print(f'Detections: {d[\"count\"]}')
print(f'Inference time: {d[\"inference_ms\"]}ms')
for det in d['detections'][:3]:
    print(f'  - {det[\"class_name\"]}: {det[\"confidence\"]:.2f}')
"
```

**Expected output:**
```
Status: 200
Detections: N (varies by image)
Inference time: ~114ms
  - cup: 0.87 (or other classes)
```

**What the evaluator should notice:**
- Real YOLOv8 inference running
- Real detection results with class names and confidence
- Inference latency ~114ms (CPU-bound)
- Response schema matches cloud (parity verified)

**Backup evidence:** Phase 8 8C (cup, conf 0.870, 114.74ms), Phase 8 8M (schema parity)

---

## Demo Step 7: Orchestrator Request

**Command:**
```bash
kubectl exec -n edgecloud deploy/orchestrator -- python -c "
import httpx, base64
with open('/app/Sampleimage.jpg', 'rb') as f:
    img_b64 = base64.b64encode(f.read()).decode()
r = httpx.post('http://localhost:8003/orchestrate', json={
    'workload': {
        'workload_id': 'demo-001',
        'priority': 'HIGH',
        'workload_type': 'object_detection',
        'latency_requirement_ms': 500
    },
    'image_base64': img_b64,
    'confidence': 0.5,
    'annotated': False
}, timeout=30)
print(f'Status: {r.status_code}')
d = r.json()
print(f'Selected: {d[\"selected_target\"]}')
print(f'Actual: {d[\"actual_target\"]}')
print(f'Score: {d[\"decision_score\"]}')
print(f'Scheduler: {d[\"scheduler_latency_ms\"]}ms')
print(f'Inference: {d[\"inference_latency_ms\"]}ms')
print(f'Total: {d[\"total_latency_ms\"]}ms')
print(f'Fallback: {d[\"fallback_used\"]}')
print(f'Detections: {len(d[\"inference_result\"][\"detections\"])}')
"
```

**Expected output:**
```
Status: 200
Selected: edge
Actual: edge
Score: 80-100
Scheduler: ~66ms (cached) or ~1100ms (uncached)
Inference: ~117ms
Total: ~416ms
Fallback: False
Detections: N
```

**What the evaluator should notice:**
- Full orchestration pipeline works
- Scheduler made a decision (edge selected)
- Inference completed on edge
- Latency breakdown shows scheduler + inference
- No fallback (normal path)

**Backup evidence:** Phase 8 8C, Phase 10 10E-6 /orchestrate benchmark

---

## Demo Step 8: Cloud Fallback (If Safely Demonstrable)

**Note:** This step requires temporarily making the cloud node unhealthy. Only do this if the evaluator approves and you can safely restore.

**Command (safe variant — just show cloud is selectable):**
```bash
kubectl exec -n edgecloud deploy/orchestrator -- python -c "
import httpx, base64
with open('/app/Sampleimage.jpg', 'rb') as f:
    img_b64 = base64.b64encode(f.read()).decode()
# Send with forced cloud metrics (edge overloaded)
r = httpx.post('http://localhost:8003/orchestrate', json={
    'workload': {
        'workload_id': 'demo-cloud',
        'priority': 'HIGH',
        'workload_type': 'object_detection',
        'latency_requirement_ms': 500
    },
    'image_base64': img_b64,
    'confidence': 0.5,
    'annotated': False,
    'edge_metrics': {'cpu_percent': 95.0, 'ram_percent': 85.0, 'disk_percent': 50.0},
    'cloud_metrics': {'cpu_percent': 30.0, 'ram_percent': 40.0, 'disk_percent': 20.0},
    'network_metrics': {'latency_ms': 50.0}
}, timeout=30)
d = r.json()
print(f'Selected: {d[\"selected_target\"]}')
print(f'Score: {d[\"decision_score\"]}')
print(f'Reason: {d[\"decision_reason\"]}')
"
```

**Expected output:**
```
Selected: cloud
Score: ...
Reason: edge_overloaded,cloud_healthy
```

**What the evaluator should notice:**
- Scheduler correctly routes to cloud when edge is overloaded
- Cloud is a viable alternative
- Decision logic works as documented

**Backup evidence:** Phase 8 8F-B (cloud selectable), Phase 8 8F-A (cloud fallback for HIGH priority)

---

## Demo Step 9: Benchmark Summary

**Command (read-only — display pre-computed results):**
```bash
echo "=== 10E-6 Production Benchmark Results ==="
echo ""
echo "/decision Latency (scheduler only):"
echo "  C1:  66.0 ms  (was 2100.9 ms, -96.9%)"
echo "  C2: 338.1 ms  (was 2201.1 ms, -84.6%)"
echo "  C4: 680.4 ms  (was 2305.8 ms, -70.5%)"
echo "  C8: 1246.8 ms (was 3128.3 ms, -60.2%)"
echo ""
echo "/orchestrate Latency (scheduler + inference):"
echo "  C1: 415.6 ms"
echo "  C2: 811.0 ms"
echo "  C4: 1474.3 ms"
echo "  C8: 2076.5 ms"
echo ""
echo "Live uncached /decision: 1107.7 ms (was 2016.9 ms, -46.7%)"
echo "Success rate: 100% (684+ requests)"
echo "Pod restarts: 0"
```

**What the evaluator should notice:**
- Monotonic improvement at all concurrency levels
- C1=66ms is cached; uncached is 1107.7ms
- Zero failures across all tests
- Production-grade results

**Backup evidence:** docs/phase10/10E/10E-6_production_validation.md, docs/phase10/10E/10E-2_baseline.md

---

## Demo Step 10: Production State Summary

**Command:**
```bash
echo "=== Production State ==="
kubectl get pods -n edgecloud --no-headers -o custom-columns=NAME:.metadata.name,STATUS:.status.phase,RESTARTS:.status.containerStatuses[0].restartCount
echo ""
echo "=== Services ==="
kubectl get svc -n edgecloud --no-headers
echo ""
echo "=== Scheduler Image ==="
kubectl get deploy scheduler -n edgecloud -o jsonpath='{.spec.template.spec.containers[0].image}'
echo ""
echo "=== WSL2 State ==="
kubectl get node wsl2-edge-node -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'
echo ""
echo "=== Rules ==="
kubectl get rules -n edgecloud --no-headers
```

**Expected output:**
```
=== Production State ===
cloud-node-...  Running  0
edge-node-...   Running  0
orchestrator-... Running 0
scheduler-...   Running  0

=== Services ===
cloud-node-svc    ClusterIP   10.43.x.x   8001/TCP
edge-node-svc     ClusterIP   10.43.x.x   8000/TCP
orchestrator-svc  NodePort    10.43.x.x   8003:30083/TCP
scheduler-svc     ClusterIP   10.43.x.x   8002/TCP

=== Scheduler Image ===
325580898273.dkr.ecr.ap-south-1.amazonaws.com/edgecloud/scheduler:10e-6

=== WSL2 State ===
False

=== Rules ===
detect-route
health-route
metrics-route
video-route
```

**What the evaluator should notice:**
- All pods Running, RESTARTS=0
- Scheduler is 10e-6 (latest optimized image)
- WSL2 is NotReady (cordoned)
- 4 KubeEdge Rules deployed

**Backup evidence:** All Phase 10 production validation gates

---

## Backup Evidence Summary

If live demo fails at any step, reference these documents:

| Step | Backup Document |
|------|----------------|
| Topology | Phase 8 8B, Phase 10 10E-6 production validation |
| Pods | Phase 10 10E-6 post-deploy regression (11/11 PASS) |
| Health | Phase 8 8B, Phase 9 9B, Phase 10 10E-6 |
| Detection | Phase 8 8C (cup, conf 0.870, 114.74ms) |
| Orchestration | Phase 8 8C, Phase 10 10E-6 /orchestrate |
| Fallback | Phase 8 8F-B (cloud selectable, HIGH priority) |
| Benchmark | 10E-2_baseline.md, 10E-6_production_validation.md |
| Reliability | Phase 8 8L (432 requests, 15-min stability) |

---

## Timing

| Step | Duration |
|------|----------|
| 1. Topology | 30s |
| 2. Edge node | 30s |
| 3. Pods | 30s |
| 4. Scheduler health | 30s |
| 5. Edge via ServiceBus | 1 min |
| 6. YOLO detection | 1 min |
| 7. Orchestrator request | 1 min |
| 8. Cloud fallback (optional) | 2 min |
| 9. Benchmark summary | 30s |
| 10. State summary | 30s |
| **Total** | **~7-9 min** |

---

## Troubleshooting

| Issue | Resolution |
|-------|-----------|
| Pod not Running | Check `kubectl describe pod <name> -n edgecloud` |
| ServiceBus timeout | Verify CloudCore is running: `ps aux | grep cloudcore` |
| Edge /metrics 503 | Check edge pod logs: `kubectl logs -n edgecloud <edge-pod>` |
| /detect slow | YOLOv8n first-load downloads model (~6MB), subsequent calls faster |
| WSL2 shows Running | Should be NotReady,SchedulingDisabled; if not, cordon manually |

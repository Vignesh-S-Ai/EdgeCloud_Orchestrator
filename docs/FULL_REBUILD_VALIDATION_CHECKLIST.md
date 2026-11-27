# Full Rebuild Validation Checklist

After rebuilding from zero, execute every gate. System is not production-ready until all gates pass.

## Level 0: AWS Infrastructure

| Gate | Check | Command | Expected |
|------|-------|---------|----------|
| 0A | VPC exists | `aws ec2 describe-vpcs --filters Name=tag:Project,Values=edgecloud` | VPC returned |
| 0B | Subnets exist | `aws ec2 describe-subnets --filters Name=tag:Project,Values=edgecloud` | 2 subnets |
| 0C | EC2 instances running | `aws ec2 describe-instances --filters Name=tag:Project,Values=edgecloud` | 2 instances running |
| 0D | EIP allocated | `aws ec2 describe-addresses --filters Name=tag:Project,Values=edgecloud` | 1 EIP |
| 0E | ECR repos exist | `aws ecr describe-repositories --repository-names edgecloud/*` | 4 repos |
| 0F | RDS available | `aws rds describe-db-instances --db-instance-identifier edgecloud-db` | Instance available |

## Level 1: K3s Cluster

| Gate | Check | Command | Expected |
|------|-------|---------|----------|
| 1A | Cloud node Ready | `kubectl get nodes` | cloud node Ready (name = `CLOUD_NODE_NAME` in rebuild.env; hostname style `ip-<private-ip-dashed>.<region>.compute.internal`) |
| 1B | Edge node Ready | `kubectl get nodes` | edge-ec2-node Ready |
| 1C | WSL2 absent/cordoned | `kubectl get nodes` | wsl2-edge-node NotReady,SchedulingDisabled (or absent) |
| 1D | Namespace exists | `kubectl get ns edgecloud` | edgecloud Active |
| 1E | ECR secret exists | `kubectl get secret ecr-registry-secret -n edgecloud` | Secret exists |

## Level 2: KubeEdge

| Gate | Check | Command | Expected |
|------|-------|---------|----------|
| 2A | CloudCore running | `kubectl get pods -n kubeedge` | cloudcore Running |
| 2B | EdgeCore connected | `kubectl get nodes` | edge-ec2-node in node list |
| 2C | Rules exist | `kubectl get rules -n edgecloud` | detect-route, health-route, metrics-route, video-route |
| 2D | RuleEndpoints exist | `kubectl get ruleendpoints -n edgecloud` | rest-source, servicebus-target |

## Level 3: Application Pods

| Gate | Check | Command | Expected |
|------|-------|---------|----------|
| 3A | All 4 pods Running | `kubectl get pods -n edgecloud -o wide` | 4 Running, RESTARTS=0 |
| 3B | Orchestrator on cloud CP | `kubectl get pods -n edgecloud -o wide` | orchestrator on cloud node (label `node-role=cloud`) |
| 3C | Scheduler on cloud CP | `kubectl get pods -n edgecloud -o wide` | scheduler on cloud node (label `node-role=cloud`) |
| 3D | Cloud-node on cloud CP | `kubectl get pods -n edgecloud -o wide` | cloud-node on cloud node (label `node-role=cloud`) |
| 3E | Edge-node on edge EC2 | `kubectl get pods -n edgecloud -o wide` | edge-node on edge-ec2-node |

## Level 4: Service Health

| Gate | Check | Command | Expected |
|------|-------|---------|----------|
| 4A | Orchestrator health | `kubectl exec -n edgecloud deployment/orchestrator -- curl -sf http://localhost:8003/health` | status: ok |
| 4B | Scheduler health | `kubectl exec -n edgecloud deployment/scheduler -- curl -sf http://localhost:8002/health` | status: ok |
| 4C | Cloud-node health | `kubectl exec -n edgecloud deployment/cloud-node -- curl -sf http://localhost:8001/health` | status: ok |
| 4D | Edge health (ServiceBus) | `kubectl exec -n edgecloud deployment/orchestrator -- curl -sf http://10.0.1.113:9443/edge-ec2-node/edgecloud/health` | status: ok |

## Level 5: Inference

| Gate | Check | Command | Expected |
|------|-------|---------|----------|
| 5A | Edge /detect (ServiceBus) | POST image to ServiceBus edge /detect | DetectionResult with detections |
| 5B | Cloud /infer | POST image to cloud-node ClusterIP | DetectionResult with detections |
| 5C | Schema parity | Compare edge and cloud response keys | 31 identical keys |
| 5D | Video processing | POST video to ServiceBus /detect/video | VideoResult with frames |

## Level 6: Scheduler

| Gate | Check | Command | Expected |
|------|-------|---------|----------|
| 6A | /decision works | POST to scheduler /decision with edge_url + cloud_url | Decision (EDGE or CLOUD) |
| 6B | /orchestrate works | POST to orchestrator /orchestrate | OrchestrationResult |
| 6C | EDGE decision routes correctly | Test with low-load metrics | target: EDGE |
| 6D | CLOUD decision routes correctly | Test with high edge-load metrics | target: CLOUD |

## Level 7: Fallback

| Gate | Check | Command | Expected |
|------|-------|---------|----------|
| 7A | Cloud -> Edge fallback | Simulate cloud failure + HIGH priority | fallback_used: true |
| 7B | No fallback for LOW priority | Simulate cloud failure + LOW priority | 503 error |

## Level 8: Security

| Gate | Check | Command | Expected |
|------|-------|---------|----------|
| 8A | Edge direct port 8000 blocked | `curl http://<EDGE_PUBLIC_IP>:8000/health` | Connection refused/timeout |
| 8B | Orchestrator NOT publicly reachable (secure access design) | `curl --max-time 5 http://<CLOUD_PUBLIC_IP>:30083/health` | Connection refused/timeout (SG has no 30083 rule) |
| 8C | Orchestrator reachable via SSM tunnel | SSM port-forward 30083 per `docs/SSM_DASHBOARD_ACCESS.md`, then `curl http://127.0.0.1:30083/health` | status: ok |
| 8D | Public ports 80/443 closed | `curl --max-time 5 http://<CLOUD_PUBLIC_IP>:80/health` | Connection refused/timeout |

## Level 9: Metrics and Optimization

| Gate | Check | Command | Expected |
|------|-------|---------|----------|
| 9A | Edge /metrics (ServiceBus) | GET edge /metrics through ServiceBus | CPU, RAM, disk values |
| 9B | Cloud /metrics | GET cloud /metrics | CPU, RAM, disk values |
| 9C | Concurrent fetch works | /decision with live URLs | Returns in ~1100ms uncached |

## Level 10: Stability

| Gate | Check | Command | Expected |
|------|-------|---------|----------|
| 10A | No CrashLoopBackOff | `kubectl get pods -n edgecloud` | No CrashLoopBackOff |
| 10B | No OOM | `kubectl describe pods -n edgecloud` | No OOMKilled |
| 10C | 10 requests succeed | Send 10 sequential /decision requests | 100% HTTP 200 |
| 10D | No unexpected restarts | `kubectl get pods -n edgecloud` | RESTARTS=0 |

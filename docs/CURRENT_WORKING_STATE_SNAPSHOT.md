# Current Working State Snapshot

## AWS Infrastructure

| Value | Current Value | Classification |
|-------|---------------|----------------|
| Region | ap-south-1 | PROJECT-CONSTANT (can change) |
| VPC CIDR | 10.0.0.0/16 | ACCOUNT-SPECIFIC |
| Public Subnet | 10.0.1.0/24 | ACCOUNT-SPECIFIC |
| RDS Subnet | 10.0.2.0/24 | ACCOUNT-SPECIFIC |
| AZ (primary) | ap-south-1a | ACCOUNT-SPECIFIC |
| AZ (secondary) | ap-south-1b | ACCOUNT-SPECIFIC |

## EC2 Instances

| Value | Current Value | Classification |
|-------|---------------|----------------|
| Cloud Instance ID | i-07ecfbdd7781c5ef5 | ACCOUNT-SPECIFIC (REBUILD-GENERATED) |
| Cloud Instance Type | t3.small | PROJECT-CONSTANT |
| Cloud Public IP | (Elastic IP) | ACCOUNT-SPECIFIC (REBUILD-GENERATED) |
| Cloud Private IP | 10.0.1.113 | ACCOUNT-SPECIFIC (REBUILD-GENERATED) |
| Cloud Node Name | ip-10-0-1-113.ap-south-1.compute.internal | ACCOUNT-SPECIFIC (REBUILD-GENERATED) |
| Edge Instance ID | i-0080aa7404208982c | ACCOUNT-SPECIFIC (REBUILD-GENERATED) |
| Edge Instance Type | t3.medium | PROJECT-CONSTANT |
| Edge Public IP | (assigned) | ACCOUNT-SPECIFIC (REBUILD-GENERATED) |
| Edge Private IP | 10.0.1.123 | ACCOUNT-SPECIFIC (REBUILD-GENERATED) |
| Edge Node Name | edge-ec2-node | REBUILD-GENERATED (manually set) |

## WSL2 Node

| Value | Current Value | Classification |
|-------|---------------|----------------|
| Node Name | wsl2-edge-node | PROJECT-CONSTANT (legacy) |
| Status | NotReady, SchedulingDisabled | PROJECT-CONSTANT (cordoned) |

## Kubernetes

| Value | Current Value | Classification |
|-------|---------------|----------------|
| K3s Version (cloud) | v1.32.13+k3s1 | REBUILD-GENERATED |
| K3s Version (edge) | v1.32.10-kubeedge-v1.23.1-dirty | REBUILD-GENERATED |
| Namespace | edgecloud | PROJECT-CONSTANT |
| Pod CIDR | (K3s default) | REBUILD-GENERATED |
| Service CIDR | (K3s default) | REBUILD-GENERATED |

## Pods

| Pod | Node | Image | Port | Classification |
|-----|------|-------|------|----------------|
| orchestrator | cloud CP (ip-10-0-1-113) | edgecloud/orchestrator:latest | :8003 (NodePort :30083) | REBUILD-GENERATED |
| scheduler | cloud CP (ip-10-0-1-113) | edgecloud/scheduler:latest | :8002 (ClusterIP) | REBUILD-GENERATED |
| cloud-node | cloud CP (ip-10-0-1-113) | edgecloud/cloud-node:latest | :8001 (ClusterIP) | REBUILD-GENERATED |
| edge-node | edge EC2 (edge-ec2-node) | edgecloud/edge-node:latest | :8000 (ClusterIP + hostPort) | REBUILD-GENERATED |

## Services

| Service | Type | Port | NodePort | Classification |
|---------|------|------|----------|----------------|
| orchestrator | NodePort | 8003 | 30083 | PROJECT-CONSTANT |
| scheduler | ClusterIP | 8002 | — | PROJECT-CONSTANT |
| cloud-node | ClusterIP | 8001 | — | PROJECT-CONSTANT |
| edge-node | ClusterIP | 8000 | — | PROJECT-CONSTANT |

## KubeEdge

| Value | Current Value | Classification |
|-------|---------------|----------------|
| CloudCore Version | v1.23.1-dirty | PROJECT-CONSTANT |
| EdgeCore Version | v1.23.1-dirty | PROJECT-CONSTANT |
| CloudHub WS Port | 10000 | PROJECT-CONSTANT |
| CloudHub HTTPS Port | 10002 | PROJECT-CONSTANT |
| CloudCore REST Port | 9443 | PROJECT-CONSTANT |
| Orchestrator Edge URL | http://10.0.1.113:9443/edge-ec2-node/edgecloud | ACCOUNT-SPECIFIC |

## KubeEdge Rules (in cluster)

| Rule | Source | Target | Path |
|------|--------|--------|------|
| detect-route | rest-source | servicebus-target | /detect |
| health-route | rest-source | servicebus-target | /health |
| metrics-route | rest-source | servicebus-target | /metrics |
| video-route | rest-source | servicebus-target | /detect/video |

Note: detect-route and health-route were created manually (no YAML file in repo). metrics-route and video-route have YAML files in infra/k3s/.

## KubeEdge RuleEndpoints

| RuleEndpoint | Type | Configuration |
|--------------|------|---------------|
| rest-source | REST | tenantURL = /edge-ec2-node/edgecloud |
| servicebus-target | ServiceBus | service_port = 8000 |

Note: RuleEndpoints were created manually (no YAML file in repo). They exist in the cluster but are not in the repository.

## ECR Repositories

| Repository | URI Pattern | Classification |
|-----------|-------------|----------------|
| edge-node | <ACCOUNT_ID>.dkr.ecr.ap-south-1.amazonaws.com/edgecloud/edge-node | ACCOUNT-SPECIFIC |
| cloud-node | <ACCOUNT_ID>.dkr.ecr.ap-south-1.amazonaws.com/edgecloud/cloud-node | ACCOUNT-SPECIFIC |
| scheduler | <ACCOUNT_ID>.dkr.ecr.ap-south-1.amazonaws.com/edgecloud/scheduler | ACCOUNT-SPECIFIC |
| orchestrator | <ACCOUNT_ID>.dkr.ecr.ap-south-1.amazonaws.com/edgecloud/orchestrator | ACCOUNT-SPECIFIC |

## Scheduler Configuration

| Setting | Value | Classification |
|---------|-------|----------------|
| Policy | rule_based | PROJECT-CONSTANT |
| Edge CPU Threshold | 70.0 | PROJECT-CONSTANT |
| Edge RAM Threshold | 70.0 | PROJECT-CONSTANT |
| Edge Disk Threshold | 85.0 | PROJECT-CONSTANT |
| Cloud CPU Threshold | 80.0 | PROJECT-CONSTANT |
| Cloud RAM Threshold | 80.0 | PROJECT-CONSTANT |
| Cloud Disk Threshold | 90.0 | PROJECT-CONSTANT |
| Max Latency MS | 200.0 | PROJECT-CONSTANT |
| Metrics TTL | configurable (default 0.0) | PROJECT-CONSTANT |
| Metrics Timeout | 2.0 sec | PROJECT-CONSTANT |

## Security Posture

| Component | Status | Classification |
|-----------|--------|----------------|
| Edge SG | Zero inbound rules (egress-only) | PROJECT-CONSTANT |
| Orchestrator | NodePort :30083, public HTTP, no auth | PROJECT-CONSTANT |
| CloudCore REST :9443 | Plain HTTP, internal only | PROJECT-CONSTANT |
| CloudHub :10000/:10002 | TLS enabled | PROJECT-CONSTANT |
| hostPort:8000 | Required (ServiceBus bridge) | PROJECT-CONSTANT |

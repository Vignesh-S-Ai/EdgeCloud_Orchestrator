# Master Project Rebuild and Disaster Recovery

> **MASTER REBUILD OBJECTIVE:** "The goal of this document is to allow the project to be reconstructed from a clean AWS account to the validated Phase 10 working architecture without relying on undocumented manual knowledge."

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Infrastructure](#2-infrastructure)
3. [AWS Setup](#3-aws-setup)
4. [ECR](#4-ecr)
5. [Cloud EC2](#5-cloud-ec2)
6. [Edge EC2](#6-edge-ec2)
7. [K3s](#7-k3s)
8. [KubeEdge](#8-kubeedge)
9. [Kubernetes Manifests](#9-kubernetes-manifests)
10. [Application Deployment](#10-application-deployment)
11. [Configuration](#11-configuration)
12. [Secrets Procedure](#12-secrets-procedure)
13. [Validation](#13-validation)
14. [Benchmark](#14-benchmark)
15. [Troubleshooting](#15-troubleshooting)
16. [Disaster Recovery](#16-disaster-recovery)
17. [New AWS Account Rebuild](#17-new-aws-account-rebuild)
18. [Known Limitations](#18-known-limitations)

---

## 1. Architecture Overview

### Runtime Flow

```
Client / Workload
    -> Orchestrator (:30083)
    -> Scheduler (/decision)
    -> Live metrics from Edge (ServiceBus) + Cloud (ClusterIP)
    -> RuleBasedPolicy
    -> Decision: EDGE | CLOUD | QUEUE | ERROR
    -> Selected inference service
    -> YOLOv8n
    -> DetectionResult
    -> OrchestrationResult
```

### KubeEdge Edge Path

```
Orchestrator
    -> CloudCore REST :9443
    -> Rule (detect-route / health-route / metrics-route / video-route)
    -> RuleEndpoint (rest-source -> servicebus-target)
    -> CloudHub :10000 (WebSocket)
    -> EdgeCore (outbound WS connection)
    -> ServiceBus (localhost:8000)
    -> Edge pod (hostPort:8000)
```

### Production Topology

```
AWS Cloud (ap-south-1)
    |
    +--- VPC (10.0.0.0/16)
         |
         +--- Public Subnet (10.0.1.0/24)
         |    |
         |    +--- Cloud EC2 (t3.small)
         |         - Amazon Linux 2023
         |         - Docker + Docker Compose (BOOTSTRAP: user_data.sh)
         |           - cloud-node :8001
         |           - scheduler :8002
         |           - orchestrator :80 -> :8003
         |         - K3s (RUNTIME: installed via SSM after bootstrap)
         |         - CloudCore (KubeEdge: installed via SSM)
         |         - K8s deployments: orchestrator, scheduler, cloud-node
         |         - Orchestrator NodePort :30083
         |
         +--- RDS Subnet (10.0.2.0/24)
              |
              +--- RDS PostgreSQL (db.t3.micro) [PROVISIONED ONLY]

Edge Location
    |
    +--- Edge EC2 (t3.medium)
         - Amazon Linux 2023
         - Containerd + CNI + crictl (installed via SSM)
         - EdgeCore (standalone, NOT K3s)
         - Edge pod (hostPort:8000)
         - Security Group: zero inbound rules (egress-only)
```

**Deployment layers:**
- **BOOTSTRAP (Docker Compose):** Terraform user_data.sh creates a 3-service Docker Compose stack on cloud EC2. This runs on the host and is the first thing that starts.
- **RUNTIME (K3s + KubeEdge):** K3s is installed manually via SSM after bootstrap. K3s runs the same services as Kubernetes deployments. KubeEdge provides edge-cloud communication via ServiceBus.
- Both coexist on the same EC2 instance. Docker Compose is the bootstrap layer; K3s/KubeEdge is the production runtime layer.

---

## 2. Infrastructure

- **Terraform:** 13 .tf files, 49 managed resources
- **Source:** `infra/terraform/`
- **Safety guide:** `docs/TERRAFORM_REBUILD_SAFETY.md`
- **Can recreate from zero:** YES (for new account)
- **Drift risk:** YES (EIP, EC2 replacement, SG rule changes)

---

## 3. AWS Setup

- **Region:** ap-south-1 (Mumbai)
- **Profile:** edgecloud
- **VPC CIDR:** 10.0.0.0/16
- **Subnets:** 10.0.1.0/24 (public, EC2), 10.0.2.0/24 (RDS)
- **AMI:** Amazon Linux 2023 (auto-resolved by Terraform data source)

---

## 4. ECR

- **4 repositories:** edgecloud/edge-node, edgecloud/cloud-node, edgecloud/scheduler, edgecloud/orchestrator
- **Tag mutability:** MUTABLE
- **Lifecycle:** untagged images expire after 7 days
- **Account-specific:** YES — ECR URIs contain AWS account ID

---

## 5. Cloud EC2

- **Type:** t3.small, 30GB gp3 encrypted
- **Bootstrap:** user_data.sh installs Docker, pulls ECR, starts docker-compose
- **Services:** cloud-node (:8001), scheduler (:8002), orchestrator (:8003 -> host :80)
- **IAM:** ECR pull, Secrets Manager read, CloudWatch, SSM

---

## 6. Edge EC2

- **Type:** t3.medium, 30GB gp3 encrypted
- **Bootstrap:** edge_user_data.sh installs base packages only
- **Runtime:** containerd + CNI + EdgeCore (installed manually via SSM)
- **Security:** egress-only SG (zero inbound rules)
- **IAM:** ECR pull, SSM only

---

## 7. K3s

- **Version:** v1.32.13+k3s1 (cloud), v1.32.10 (edge, via KubeEdge)
- **Install:** `curl -sfL https://get.k3s.io | sh -s - server`
- **Edge node:** NOT K3s — standalone EdgeCore

---

## 8. KubeEdge

- **Version:** v1.23.1-dirty
- **CloudCore:** keadm init --cloudcore-port=10002
- **EdgeCore:** Manual binary installation (see KUBEEDGE_REBUILD_BLUEPRINT.md)
- **Rules + RuleEndpoints:** Repository files in `infra/k3s/`:
  - `edgecloud-kubeedge-rules.yaml` — 4 Rules (detect-route, health-route, metrics-route, video-route)
  - `edgecloud-kubeedge-ruleendpoints.yaml` — 2 RuleEndpoints (rest-source, servicebus-target)
- **Apply:** `kubectl apply -f infra/k3s/edgecloud-kubeedge-ruleendpoints.yaml` then `kubectl apply -f infra/k3s/edgecloud-kubeedge-rules.yaml`

---

## 9. Kubernetes Manifests

- **Source:** `infra/k3s/` (16 YAML files)
- **Apply order:** namespace -> rules/ruleendpoints -> deployments -> services
- **All required K8s resources are now in the repository:**
  - Deployments: cloud-node, scheduler, orchestrator, edge-node (EC2 variant)
  - Services: cloud-node, scheduler, orchestrator (NodePort), edge-node
  - KubeEdge Rules: edgecloud-kubeedge-rules.yaml (4 rules)
  - KubeEdge RuleEndpoints: edgecloud-kubeedge-ruleendpoints.yaml (2 endpoints)
- **Apply via script:** `bash infra/rebuild/scripts/06-deploy-k8s.sh`

---

## 10. Application Deployment

- **4 pods:** orchestrator, scheduler, cloud-node, edge-node
- **Placement:** orchestrator/scheduler/cloud-node on cloud CP, edge-node on edge EC2
- **Image pull:** via ecr-registry-secret

---

## 11. Configuration

- **Environment variables:** Set in deployment YAML env sections
- **Key settings:** scheduler thresholds, orchestrator URLs, edge/cloud ports
- **Detailed values:** `docs/CURRENT_WORKING_STATE_SNAPSHOT.md`

---

## 12. Secrets Procedure

- **AWS credentials:** Local CLI profile
- **ECR token:** `aws ecr get-login-password`
- **KubeEdge token:** `keadm gettoken` or `kubectl get secret tokensecret`
- **Database:** Terraform auto-generates, stored in Secrets Manager (PROVISIONED ONLY)
- **Detailed guide:** `docs/RECOVERY_SECRETS_AND_CREDENTIALS.md`

---

## 13. Validation

- **34 gates:** `docs/FULL_REBUILD_VALIDATION_CHECKLIST.md`
- **Covers:** AWS infrastructure, K3s, KubeEdge, pods, health, inference, scheduler, fallback, security, metrics, stability

---

## 14. Benchmark

- **Tool:** `docs/phase10/10E/p10_10e_bench.py`
- **Targets:** /decision uncached ~1100ms, /decision C1 cached ~66ms, /orchestrate C1 ~415ms
- **Note:** Exact numbers differ by hardware; validate by order of magnitude

---

## 15. Troubleshooting

See `docs/DISASTER_RECOVERY_SCENARIOS.md` for per-scenario recovery.

---

## 16. Disaster Recovery

10 scenarios documented: A (edge lost) through J (images lost). See `docs/DISASTER_RECOVERY_SCENARIOS.md`.

---

## 17. New AWS Account Rebuild

Step-by-step from empty account to validated system. See `docs/NEW_AWS_ACCOUNT_REBUILD.md`.

---

## 18. Known Limitations

| Limitation | Status |
|-----------|--------|
| PostgreSQL | PROVISIONED ONLY — no app connects |
| React Dashboard | NOT IMPLEMENTED — zero frontend code |
| Prometheus/Grafana | NOT DEPLOYED |
| Edge->Cloud failover | NOT IMPLEMENTED — returns 503 |
| GPU inference | NOT AVAILABLE — CPU only |
| Camera | Synthetic MP4 only — no physical camera |
| Long-term reliability | NOT TESTED beyond 15 minutes |
| CloudCore REST TLS | NOT IMPLEMENTED (plain HTTP) |
| Public API auth | NONE — HTTP, no authentication |
| hostPort:8000 | REQUIRED — cannot be removed |

---

## Supporting Documents

| Document | Purpose |
|----------|---------|
| `REBUILD_QUICKSTART.md` | Short entry point |
| `MASTER_REBUILD_RUNBOOK.md` | 30-phase step-by-step |
| `CURRENT_WORKING_STATE_SNAPSHOT.md` | Exact current state |
| `FULL_REBUILD_VALIDATION_CHECKLIST.md` | 34 validation gates |
| `NEW_AWS_ACCOUNT_REBUILD.md` | Fresh account procedure |
| `KUBEEDGE_REBUILD_BLUEPRINT.md` | KubeEdge details |
| `TERRAFORM_REBUILD_SAFETY.md` | Terraform safety |
| `REBUILD_VERSION_MATRIX.md` | Locked versions |
| `RECOVERY_SECRETS_AND_CREDENTIALS.md` | Secrets procedure |
| `DISASTER_RECOVERY_SCENARIOS.md` | Per-scenario recovery |
| `REPOSITORY_REPRODUCIBILITY_AUDIT.md` | Repo gaps |

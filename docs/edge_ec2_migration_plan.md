# Module 5 / Gate 4 — Dedicated EC2 Edge Node: Migration Plan

**Status:** PLAN ONLY — no infrastructure has been provisioned or modified.
**Author:** opencode session
**Date:** 2026-08-31
**Type:** Migration of experimental edge runtime from unstable WSL2 → dedicated EC2 edge node.

---

## 1. Current architecture (verified by inspection)

```
CLOUD EC2  (i-07ecfbdd7781c5ef5, t3.medium, ap-south-1a)
  VPC: vpc-085fedc9cda6619be (10.0.0.0/16)
  Public subnet: 10.0.1.0/24 (subnet-034eb0edef8df69e9)
  SG: edgecloud-ec2-sg (sg-09aada8e7591efe3e)
  EIP: 13.206.229.162  |  Private: 10.0.1.113
  ├── K3s v1.32.13 (control-plane, ip-10-0-1-113)
  │     pod CIDR 10.42.0.0/24 -> control-plane node
  │     service CIDR 10.43.0.0/16
  ├── CloudCore v1.23.1 (systemd) — websocket :10000, https :10002, router :9443
  ├── Pod cloud-node        (10.42.0.5:8001, Running 13d)
  ├── Pod scheduler         (10.42.0.6:8002, Running 13d)
  └── Pod orchestrator      (10.42.0.7:8003/30083, Running 13d)
        ORCHESTRATOR_EDGE_URL  -> edge-node.edgecloud.svc:8000
        ORCHESTRATOR_CLOUD_URL -> cloud-node.edgecloud.svc:8001
        ORCHESTRATOR_SCHEDULER_URL -> scheduler.edgecloud.svc:8002

UNSTABLE EDGE (WSL2)
  ├── EdgeCore v1.23.1-dirty (3 source patches) — node name: wsl2-edge-node
  │     pod CIDR 10.42.1.0/24
  ├── containerd (edge-containerd.service, system containerd masked)
  ├── CNI v1.6.2
  └── edge-node pod (FastAPI + YOLOv8) — killed every 30-120s by VHD unmounts
```

## 2. Why WSL2 cannot be used for reliable Gate 4 testing

Confirmed via `dmesg` on 2026-08-25: the WSL2 ext4 VHD backing `/var/lib/containerd`
(`/dev/sdd`) is repeatedly unmounted every 30-120s. Each unmount destroys the running
containerd workload (container exit code 255). The application logic, containerd,
EdgeCore, ECR pull, and YOLO startup are all verified correct — the component that is
unreliable is the WSL2/Hyper-V storage layer, which is outside our control and cannot
be patched from inside the VM. This makes a stable 5-15 minute observation window,
required for Gate 4 evidence, impossible.

## 3. Decision

Provision a **dedicated second EC2 instance** as the stable KubeEdge edge node.
No changes to the existing cloud node, CloudCore, WSL2 node, RDS, or existing
production deployments until the new node is proven stable.

"Migration of the experimental edge runtime from an unstable WSL2 environment to a
dedicated cloud-hosted edge node to achieve reproducible Edge-Cloud integration testing."

## 4. Proposed edge-EC2 architecture

```
CLOUD EC2                                  EDGE EC2 (NEW)
  K3s (control-plane)                       EdgeCore v1.23.1-dirty (patched)
  CloudCore (:10000 websocket,              containerd (ONE, custom service)
    :10002, router :9443)                   CNI v1.6.2
  Scheduler / Orchestrator / Cloud-node     FastAPI + YOLOv8 (edge-node pod)
        |  KubeEdge WebSocket/ServiceBus   |  (node: edge-ec2-node)
        └───────────────────────────────────┘
```

Hard requirements (avoid re-creating the dual-containerd/dual-kubelet conflict):
- EXACTLY ONE containerd service on the edge EC2.
- EXACTLY ONE EdgeCore.
- CNI installed.
- **NO K3s server, NO K3s agent/kubelet, NO embedded containerd** on the edge EC2.
  (A plain Amazon Linux 2023 image has no k3s by default; we simply do NOT install k3s.)

## 5. Exact Terraform resources required (additive)

All under `infra/terraform/`, reusing existing VPC/subnet/route table.

- `aws_instance.edge_node` — t3.medium, AL2023 AMI, subnet `aws_subnet.public`,
  new SG, new IAM profile, `associate_public_ip_address = true`, root 30GB gp3 encrypted,
  user_data bootstraps containerd + CNI + EdgeCore.
- `aws_security_group.edge_node` — inbound: SSH/SSM not needed (SSM covers access);
  outbound: all. Inbound for KubeEdge/containerd deliberately minimal (see §6).
- `aws_iam_role.edge_node` + `aws_iam_instance_profile.edge_node`:
  - `AmazonSSMManagedInstanceCore` (session manager access)
  - ECR pull policy — copy the existing `ecr_pull` policy (GetDownloadUrlForLayer,
    BatchGetImage, GetAuthorizationToken, BatchCheckLayerAvailability,
    DescribeRepositories, ListImages). Needed to pull `edgecloud/edge-node:latest`.
    (Do NOT reuse the cloud role blindly — separate least-privilege role is cleaner
    and avoids granting the edge node RDS/secrets access it does not need.)
  - CloudWatch logs policy (mirror existing) if we add a log agent.
- `aws_eip.edge_node` + association — optional but recommended so EdgeCore's
  outbound source IP and the ServiceBus target node are stable. (Without it the
  node's public IP changes on restart, which matters for restricting cloud SG rules.)
- New SG rule on the CLOUD SG allowing the edge node IN only if a stable source IP
  is available. Preferred: use the edge node's **private IP 10.0.1.x/32** and/or the
  edge EIP, so existing `0.0.0.0/0` KubeEdge rules (10000, 10002, 30083) and the
  Terraform `${edge_public_ip}/32` rules can later be tightened.
- Variable additions: `edge_instance_type` (default t3.medium), `edge_root_volume_size`.
- Outputs: edge instance id, public ip, eip.

Files touched: `ec2.tf` (add resource), `security_groups.tf` (add SG),
`iam.tf` (add role/profile/policy), `eip.tf` (add edge EIP), `variables.tf`,
`outputs.tf`, new `edge_user_data.sh`.

Do NOT modify: `rds.tf`, `secrets.tf`, `cloudwatch.tf` (except optional edge alarm),
`docker-compose.yml`, existing `aws_instance.cloud`.

## 6. Networking requirements

- Edge EC2 outbound: must reach CloudCore at `13.206.229.162:10000` (websocket) and
  ECR + internet (model download). Egress all `0.0.0.0/0` on edge SG.
- Edge EC2 inbound (edge SG): **none/public** custom required for the architecture.
  KubeEdge uses outbound to CloudCore. containerd/EdgeCore bind locally.
  For convenience/testing only, optionally open SSH or use SSM (SSM recommended; port 22
  stays closed). No 6443, no 10250 on the edge node (it is not a k3s/kubelet node).
- Cloud SG: CloudCore ports **10000, 10002, 30083, 9443** must be reachable from the
  edge EC2. Prefer restricting to the edge private CIDR `10.0.1.0/24` (same subnet) or
  to the edge EIP `/32`. Document the rationale; keep as-is (0.0.0.0/0) only until the
  edge node's stable source IP is confirmed, then tighten.
- Same VPC/public subnet -> edge node private IP 10.0.1.x, K3s/CloudCore at 10.0.1.113.
- No new VPC/subnet/route needed: reuse `aws_subnet.public` (10.0.1.0/24, ap-south-1a).

## 7. KubeEdge / EdgeCore design

- **Join endpoint:** CloudCore `13.206.229.162:10000` (unchanged).
- **Node name:** `edge-ec2-node` (distinct from `wsl2-edge-node` to avoid collisions;
  WSL2 node left untouched).
- **Pod CIDR:** KubeEdge controller assigns dynamically from the cluster (10.42.x.0/24);
  no manual reservation needed. The new node picks up the next free pod CIDR.
- **EdgeCore version:** v1.23.1 **with the same 3 source patches** (processQuery
  feedbackError, imitator Kind injection, processPatch synchronous). Rebuild the
  patched binary on the edge EC2 from the source tree (repackaging the 3 patches is a
  sub-task; do NOT silently drop them — they remain required for node Ready + status patch).
- **containerd:** install standalone `containerd` (NOT k3s-embedded). One service only,
  analogous to `edge-containerd.service` (system `containerd.service` masked to prevent
  the dual-service BoltDB conflict from resurfacing). CRI enabled, sandbox image
  `registry.k8s.io/pause:3.8`, `config.toml` matching the WSL2 verified config.
- **CNI:** v1.6.2 plugins at `/opt/cni/bin/` (loopback + bridge), matching verified setup.
- **systemd services:** one `containerd` service + one `edgecore` service with
  `Restart=always`, socket-wait `ExecStartPre`, matching verified WSL2 definitions
  (minus the `basic.target`/session-cascade hacks that were only needed for WSL2).
- **ECR auth:** use the instance profile's ECR permission to generate the dockerconfigjson
  secret, or pull the image via containerd with `kubectl create secret docker-registry`
  using an ECR token (same approach as `ecr-registry-secret`). The deployment already
  references `imagePullSecrets: ecr-registry-secret`.

## 8. Migration sequence (phase-gated, WSL2 untouched until stable)

1. Terraform: add edge EC2 resources + `terraform plan` review.
2. `terraform apply` edge node (E1: infra valid, E2: reachable).
3. Bootstrap via user_data/SSM: dnf packages, containerd, CNI, patched EdgeCore, edgecore.service.
4. Gate E3: containerd + CNI healthy (crictl info, /opt/cni/bin present).
5. Start EdgeCore, join CloudCore (E4: EdgeCore stable).
6. Node registers as `edge-ec2-node`, reaches Ready (E5).
7. Gate E6: deploy nginx test pod with nodeSelector `kubernetes.io/hostname=edge-ec2-node`; verify 1/1 Running + pod IP.
8. Gate E7/E8/E9: deploy existing `edge-node` deployment pointed at the new node
   (new nodeSelector), confirm ECR pull, YOLO startup, `/health` 200, `/detect` JSON, `/metrics`.
9. ServiceBus config for the edge node (node-scoped servicebus target) (E10/E11:
   CloudCore -> ServiceBus -> edge /health and /detect via :9443).
10. Gate E12: 15-30 min stability test (no restarts, node remains Ready, no PLEG/CRI errors).
11. Gate E13: performance measurements (local inference, cloud offload, round-trip,
    CPU/RAM, network, success rate) — real measured values only.
12. Only after E13 passes: plan WSL2 edge retirement (documented rollback in place).

## 9. Rollback sequence

- Keep WSL2 `wsl2-edge-node` and all existing deployments untouched during validation.
- If new node fails any gate: `kubectl cordon edge-ec2-node`, delete edge-ec2 deployments,
  `terraform destroy -target=aws_instance.edge_node` (and edge SG/role/EIP), re-point the
  edge-node deployment nodeSelector back to `wsl2-edge-node`. Existing cloud stack unaffected.
- Cloud SG rule changes are additive-only during migration; rollback = remove added rules.

## 10. Cost implications

- t3.medium on-demand ap-south-1 ≈ **$26.79/mo** (~$30 incl. EIP is free + small shared-EBS).
- Root 30 GB gp3 ≈ ~$3/mo. Total incremental ≈ **~$30-33/mo**.
- AWS credits: **$139 expiring 2026-10-10**. Running cloud (t3.medium ~$27) + new edge
  (t3.medium ~$27) + RDS (~$13) ≈ ~$67/mo. Budget check: 2 months ≈ $134 — tight but within,
  assuming cloud node stays t3.medium; consider stopping the cloud node when idle.
- Recommend confirming the credit budget before apply.

## 11. Risks

- **Cost/credit exhaustion** — monitor before applying.
- **Pod CIDR / controller conflicts** — KubeEdge node join on an already-populated cluster;
  mitigated by unique node name + letting the controller assign CIDR.
- **Rebuild misses a patch** — mitigated by a dedicated sub-task to re-apply the 3 patches
  verbatim and checksum the binary.
- **Dual containerd recurrence** — hardened by masking system containerd on the edge EC2
  and not installing k3s.
- **Port opening / security** — SG rules tightened to edge node source where possible;
  live 0.0.0.0/0 rules documented and scheduled to be restricted.
- **ServiceBus node targeting** — KubeEdge servicebus targets a node; must create a
  node-scoped rule/endpoint for `edge-ec2-node` and confirm `service_port: 8000`.

## 12. Gate checklist (Gate E1–E13)

| Gate | Check | Evidence |
|---|---|---|
| E1 | Terraform infra valid | `terraform plan` + `apply` |
| E2 | Edge EC2 reachable | SSM/`ssh`/ping, public+private IP |
| E3 | containerd + CNI healthy | `crictl info`, `/opt/cni/bin` |
| E4 | EdgeCore starts, stays up | `systemctl is-active edgecore` > 15 min |
| E5 | KubeEdge node Ready | `kubectl get node edge-ec2-node` = Ready |
| E6 | nginx test pod Running | `kubectl get pod` 1/1, pod IP reachable |
| E7 | YOLOv8 pod Running | edge-node pod 1/1 Running |
| E8 | local /health | HTTP 200 |
| E9 | local /detect | valid detection JSON |
| E10 | CloudCore→ServiceBus→edge /health | POST :9443 health → 200 |
| E11 | CloudCore→ServiceBus→edge /detect | POST :9443 detect → detection JSON |
| E12 | 15-30 min stability | no restarts, node Ready, no CRI/PLEG errors |
| E13 | Performance measurements | measured latencies + resource usage |

Do not advance past a failed gate without diagnosis.

## 13. Files that WILL be modified / created

- `infra/terraform/ec2.tf` — add `aws_instance.edge_node`
- `infra/terraform/security_groups.tf` — add `aws_security_group.edge_node` + rules
- `infra/terraform/iam.tf` — add edge role/profile + ECR pull + SSM + CW
- `infra/terraform/eip.tf` — add `aws_eip.edge_node` (optional but recommended)
- `infra/terraform/variables.tf` — add edge instance type / volume vars
- `infra/terraform/outputs.tf` — add edge outputs
- `infra/terraform/edge_user_data.sh` — NEW: edge EC2 bootstrap (containerd+CNI+EdgeCore)
- `infra/k3s/edge-node-deployment.yaml` — new nodeSelector `edge-ec2-node` (as a new variant,
   do not overwrite the WSL2 variant in-place until E13 passes)
- A new `infra/k3s/nginx-edge-ec2.yaml` test manifest (or reuse nginx-edge with nodeSelector)
- New `infra/k3s/ruleendpoint-servicebus-edge-ec2.yaml` + `rule-edge-ec2.yaml` (node-scoped)
- Rebuild/repack script for the 3 KubeEdge patches on AL2023
- `docs/` migration entry + research-diary notes

## 14. Files that MUST NOT be modified (during migration)

- Existing `aws_instance.cloud`, its SG rules (additive only), RDS (`rds.tf`, `secrets.tf`)
- `cloud/Dockerfile`, `scheduler/Dockerfile`, `orchestrator/Dockerfile` (no change needed)
- `edge/Dockerfile` + `edge/` source (application logic is already correct; no code change)
- `infra/k3s/cloud-node-*.yaml`, `scheduler-*.yaml`, `orchestrator-*.yaml`
- CloudCore config and existing kubeedge Rule/RuleEndpoint for `wsl2-edge-node`
- WSL2 config, WSL2 EdgeCore, the existing production `edge-node` deployment (until E13)
- `.gitignore.txt` handling — create a real `.gitignore` if new tracked files are added

## 15. Commands that would be executed later (after approval)

```bash
# From repo root (Windows PowerShell can't cd; use -chdir / workdir)
cd infra/terraform
terraform init
terraform plan -var "edge_public_ip=<new-edge-eip-or-ignore>"
terraform apply -auto-approve

# Verify new edge node
terraform output edge_public_ip edge_instance_id

# Post-bootstrap, from EC2 cloud instance (k3s.kubeconfig)
kubectl taint nodes edge-ec2-node node-role.kubernetes.io/edge:NoSchedule- 2>/dev/null || true
kubectl get node edge-ec2-node -o wide
kubectl apply -f /tmp/nginx-edge-ec2.yaml
kubectl get pods -n edge-test -o wide
# Then apply edge-node deployment with nodeSelector=edge-ec2-node, verify E7-E9
# Then ServiceBus rules/endpoint for edge-ec2-node, verify E10-E11 via:
curl -k https://13.206.229.162:9443/edge-ec2-node/edgecloud/health
```
(Exact command set finalized and re-run at implementation time.)

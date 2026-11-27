# Secure Remote Access — SSM Session Manager Port Forwarding

**Design decision (2026-11 new-account rebuild):** The orchestrator and all
management interfaces are **NOT publicly exposed**. Remote access from any
network (home Wi-Fi, college Wi-Fi, mobile hotspot) goes through
**AWS Systems Manager Session Manager port forwarding**, which is
IAM-authenticated and requires **zero inbound security-group rules**.

This supersedes the legacy design where NodePort `30083` was reachable from
the internet with no authentication.

---

## Why Session Manager first (vs Client VPN)

| Criterion | Session Manager port forwarding | AWS Client VPN |
|---|---|---|
| Authentication | IAM identity (keys/SSO + MFA policy) | IAM/OIDC + VPN certs |
| Inbound SG rules needed | **None** (outbound 443 only) | None (but ENI + subnet) |
| Works from any network | Yes | Yes |
| Extra cost | **$0** (standard sessions included) | ~$0.10/hr/connection + endpoint hourly (~$25/mo+) |
| Browser access | Via localhost port-forward | Native |
| Verdict | **SELECTED** — meets all requirements | Fallback only if native VPN later required |

Client VPN is **not** needed unless a future requirement demands
OS-level VPN tunneling. If that day comes, see
`docs/MASTER_PROJECT_REBUILD_AND_DISASTER_RECOVERY.md` for patterns.

---

## Prerequisites (verified statically in Stage 2)

1. **IAM instance roles** — both `edgecloud-ec2-role` and
   `edgecloud-edge-node-role` attach `AmazonSSMManagedInstanceCore`
   (`infra/terraform-new/iam.tf:108`, `infra/terraform-new/edge_node.tf:68`). ✅
2. **SSM Agent** — Amazon Linux 2023 AMI ships with `ssm-agent` preinstalled
   and enabled. (Live verification at Stage 5:
   `aws ssm describe-instance-information --profile edgecloud --region ap-south-1`
   must list both instance IDs.)
3. **Network path** — both instances are in the public subnet with a public IP
   and route to an Internet Gateway; SSM connects *outbound* to
   `ssm.<region>.amazonaws.com` over 443. The cloud SG egress rule allows all
   outbound; the edge SG is egress-only. ✅ No VPC endpoint required.
4. **Local tool** — `session-manager-plugin` must be installed on the operator
   machine (NOT currently installed — see blockers):
   ```powershell
   winget install Amazon.SessionManagerPlugin
   # verify:
   session-manager-plugin --version
   ```
5. **Caller permissions** — the IAM user/role running `start-session` needs:
   `ssm:StartSession`, `ssm:TerminateSession`, `ssm:DescribeSession`,
   `ssm:DescribeInstanceInformation` (and `ssm:SendCommand` for kubeconfig
   retrieval). The documented admin policy set (ECR/VPC/IAM/etc. full access)
   plus `AmazonSSMFullAccess` covers this.

---

## Connection commands

Replace `<CLOUD_INSTANCE_ID>` / `<EDGE_INSTANCE_ID>` with values from
`infra/rebuild/rebuild.env` (never hardcode).

### A. Orchestrator / future dashboard → localhost:30083

```powershell
aws ssm start-session --target <CLOUD_INSTANCE_ID> `
  --region ap-south-1 --profile edgecloud `
  --document-name AWS-StartPortForwardingSession `
  --parameters '{"portNumber":["30083"],"localPortNumber":["30083"]}'
```

Second terminal (session must stay open):

```powershell
curl http://127.0.0.1:30083/health
curl -X POST http://127.0.0.1:30083/orchestrate -H "Content-Type: application/json" --data-binary "@edge.json"
```

The React dashboard (future stage) will be served or reached at
`http://127.0.0.1:30083` through the same tunnel — authentication is the IAM
session itself; add an app-level auth layer before exposing any management
function beyond read-only health.

### B. kubectl → localhost:6443 (K3s API, stays private)

Retrieve kubeconfig **once** (output redirected to file — never printed):

```powershell
aws ssm send-command --target <CLOUD_INSTANCE_ID> `
  --region ap-south-1 --profile edgecloud `
  --document-name AWS-RunShellScript `
  --parameters commands="sudo cat /etc/rancher/k3s/k3s.yaml" `
  --query "Command.CommandInvocations[0].CommandPlugins[0].Output" `
  --output text > $HOME\.kube\config
```

Keep a port-forward session open while using kubectl:

```powershell
aws ssm start-session --target <CLOUD_INSTANCE_ID> `
  --region ap-south-1 --profile edgecloud `
  --document-name AWS-StartPortForwardingSession `
  --parameters '{"portNumber":["6443"],"localPortNumber":["6443"]}'
```

`k3s.yaml` already points at `https://127.0.0.1:6443` — **no edit needed**,
and port 6443 is never opened in any security group.

```powershell
kubectl get nodes
```

### C. Shell on either instance (debugging)

```powershell
aws ssm start-session --target <CLOUD_INSTANCE_ID> --region ap-south-1 --profile edgecloud
aws ssm start-session --target <EDGE_INSTANCE_ID>  --region ap-south-1 --profile edgecloud
```

---

## Final security-group rule set (post-rebuild)

| SG | Port | Source | Purpose |
|----|------|--------|---------|
| `edgecloud-ec2-sg` | 10000/tcp | edge node **Elastic IP/32** | KubeEdge CloudHub WebSocket |
| `edgecloud-ec2-sg` | 10002/tcp | edge node **Elastic IP/32** | KubeEdge CloudHub HTTPS |
| `edgecloud-ec2-sg` | *(all other inbound)* | **NONE** | 80, 443, 30083, 22, 6443, 9443 all closed |
| `edgecloud-ec2-sg` | all outbound | 0.0.0.0/0 | ECR, pip, model download, SSM, GitHub |
| `edgecloud-edge-node-sg` | *(all inbound)* | **NONE** | egress-only by design |
| `edgecloud-edge-node-sg` | all outbound | 0.0.0.0/0 | containerd, EdgeCore→CloudCore, SSM |
| `edgecloud-rds-sg` | 5432/tcp | `edgecloud-ec2-sg` only | PostgreSQL private |

- Edge inference API `:8000` — unreachable from internet (zero inbound edge SG). ✅
- CloudCore REST `:9443` — not in any SG (internal-only, plain HTTP). ✅
- RDS — not publicly accessible, SG-restricted to the cloud node. ✅
- Orchestrator — reachable **only** through an IAM-authenticated SSM tunnel. ✅

---

## Optional hardening (not enabled — record for later)

- Session Manager **session logging** to CloudWatch Logs/S3 (audit trail of
  every shell/port-forward session): `aws ssm update-document` with
  `CloudWatchLogGroupName`/`S3Bucket` in `AWS-StartPortForwardingSession`.
- IAM policy condition `ssm:SessionTag` / `aws:RequestedRegion` lockdown.
- MFA enforced on the IAM user via `aws:MultiFactorAuthPresent` condition.

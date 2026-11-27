# NEW AWS DEPLOYMENT PROGRESS — EdgeCloud Orchestrator

Target: new AWS account `171743139339` · region `ap-south-1` · old account `325580898273` (suspended, never touched)
Mode: approval gates before every billable/resource-creating AWS action.

---

## Stage status

| Stage | Description | Status |
|-------|-------------|--------|
| 0 | Repository inspection (docs + Terraform + manifests + scripts) | **DONE** |
| 0b | Local test suite (pytest, 4 services) | **DONE — 131/131 passed** |
| 1 | AWS authentication (new account identity verified) | **DONE — `171743139339`, profile `edgecloud`, ap-south-1** |
| 2 | Code/config fixes (account ID, nodeSelector, SG, fresh TF dir, SSM access) | **DONE — local only, 0 AWS calls** |
| 3 | Terraform init + ECR repos (targeted apply) | **DONE — Gate 1 approved & applied: 4 ECR repos created** |
| 4 | Docker build + push 4 images | **DONE — all 4 pushed, digests verified in AWS** |
| 5 | Full Terraform apply (VPC/EC2/RDS/IAM/SG/Secrets/CW) | **GATE 2 FINAL PLAN READY (2026-11-26): cost safeguards added ($110 budget + billing alarm + SNS email); `tfplan-post-upgrade` = 12 create / 0 change / 0 destroy (39 preserved, 0 drift), SHA256 `DED1DC52…CE80` — awaiting final approval, NOT applied** |
| 6 | Collect rebuild.env + wait cloud bootstrap | PENDING |
| 7 | K3s install on cloud (SSM) | PENDING |
| 8 | Local kubeconfig | PENDING |
| 9 | CloudCore install (keadm init) | PENDING |
| 10 | Edge prep: containerd/CNI/crictl/EdgeCore (SSM) | PENDING |
| 11 | EdgeCore start + node registration | PENDING |
| 12 | Uncordon/label edge node | PENDING |
| 13 | `06-deploy-k8s.sh` (4 services) | PENDING |
| 14 | `07-configure-rules.sh` (Rules/RuleEndpoints) | PENDING |
| 15 | `08-validate.sh` + checklist gates | PENDING |
| 16 | Real inference E2E (edge + cloud) + benchmark | PENDING |

---

## Files modified (this rebuild)

### Stage 1
| File | Change |
|------|--------|
| AWS profile `edgecloud` (local ~/.aws) | Repointed to NEW account `171743139339`, region `ap-south-1` (user action) |

### Stage 2 — Terraform working dir `infra/terraform-new/` (fresh state; original `infra/terraform/` preserved)
| File | Change |
|------|--------|
| `infra/terraform-new/` (new dir) | Clean copy of 17 source files + `.terraform.lock.hcl` + `.terraform/providers`; no tfstate/tfplan copied |
| `user_data.sh` | ECR login uses `$AWS_ACCOUNT_ID` (no braces — templatefile constraint) fed by new `account_id` template var; removed hardcoded `325580898273` |
| `ec2.tf` | Added `data "aws_caller_identity" "current" {}` + `account_id` templatefile arg |
| `security_groups.tf` | **Removed 80/443/30083 inbound rules** (zero public exposure); 10000/10002 sourced from `aws_eip.edge`/32; design note in header |
| `edge_node.tf` | Added `aws_eip.edge` + `aws_eip_association.edge`; `edge_node_public_ip` output now returns the EIP; fixed stale `13.206.229.162` comment |
| `variables.tf` | `instance_type` default → `t3.medium` (runbook compliance); removed dead `edge_public_ip` var (replaced with explanatory note) |
| `providers.tf` | `Project` tag → `var.project_name` (fixes `tag:Project=edgecloud` vs `edge-cloud-orchestrator` mismatch in validation gates) |

### Stage 2 — K8s manifests (`infra/k3s/`)
| File | Change |
|------|--------|
| `orchestrator-deployment.yaml` | nodeSelector → `node-role: cloud`; ECR URI → new account `171743139339` |
| `scheduler-deployment.yaml` | Added `nodeSelector: node-role: cloud`; ECR URI → new account |
| `cloud-node-deployment.yaml` | Added `nodeSelector: node-role: cloud`; ECR URI → new account |
| `edge-node-deployment-edge.yaml` | ECR URI → new account (nodeSelector already correct) |
| `edge-node-deployment.yaml` (WSL2 legacy) | ECR URI → new account (consistency; not deployed by scripts) |

### Stage 2 — Rebuild scripts (`infra/rebuild/scripts/`)
| File | Change |
|------|--------|
| `00-collect-outputs.sh` | `TF_DIR` → `../../terraform-new`; `CLOUD/EDGE_PRIVATE_IP` + `CLOUD_NODE_NAME` auto-derived via `aws ec2 describe-instances` (with `--region/--profile`); fallback `<MANUAL>` |
| `04-install-k3s.sh` | Removed `--node-name` override (aligns with runbook Phase 7 — node name = instance hostname) |
| `06-deploy-k8s.sh` | New Step 2b: normalizes `<CLOUD_PRIVATE_IP>` placeholder + derives cloud node name from `kubectl get nodes` + `kubectl label node ... node-role=cloud --overwrite` |
| `08-validate.sh` | Placeholder normalization for `CLOUD_PRIVATE_IP`; `describe-instances` now has `--region/--profile` |

### Stage 2 — Docs
| File | Change |
|------|--------|
| `docs/SSM_DASHBOARD_ACCESS.md` | **NEW** — Session Manager port-forward design: connection commands (30083/6443/shell), final SG rule table, prerequisites, $0 cost rationale, Client VPN as fallback only |
| `docs/FULL_REBUILD_VALIDATION_CHECKLIST.md` | Gates 1A/3B–3D updated for `node-role=cloud`; Gate 8B flipped — 30083 must now be **blocked** publicly; added 8C (SSM tunnel works) + 8D (80/443 blocked) |

Not modified: application source (`edge/`, `cloud/`, `scheduler/`, `orchestrator/`) — tests pass as-is.

---

## AWS resources created

| Stage | Resources | Account | Region |
|-------|-----------|---------|--------|
| Gate 1 (2026-11-26) | 4× ECR: `edgecloud/cloud-node`, `edgecloud/scheduler`, `edgecloud/orchestrator`, `edgecloud/edge-node` | `171743139339` | `ap-south-1` |

Verified live via `aws ecr describe-repositories` + `describe-registry` (registryId `171743139339`). State: 4 entries in `infra/terraform-new/terraform.tfstate`. **Nothing else created.**

**Stage 4 images pushed (2026-11-26, tag `latest`, all digests verified in AWS):**

| Repo | Digest | Compressed size |
|---|---|---|
| `edgecloud/cloud-node` | `sha256:3366c11e4ea1231d32e19defb389f637e876938f03b5fcbcb3386f8e745fec35` | ~525 MiB |
| `edgecloud/scheduler` | `sha256:bc86124de82f2cb9170890a8cca8e1ed89e086b547454fb61e797b97aa56322d` | ~56 MiB |
| `edgecloud/orchestrator` | `sha256:3164699333bf732646c315b0c52be6a4ee9222136b4ed014a6a874c85ee44969` | ~56 MiB |
| `edgecloud/edge-node` | `sha256:fb6165722e861d1782957c46502109bf9d3c98461b51761fa3550fa19b4244cf` | ~1671 MiB |

**Gate 2 plan (`tfplan-full`, read-only, saved):** 42 create, 0 change, 0 destroy (4 no-ops = Gate 1 repos). No replacements, no destroys, no unexpected resources. Billable items: 2× t3.medium, 2× EIP, RDS db.t3.micro+20GB, Secrets Manager; no NAT gateway. **Estimated ~$92–98/mo.** Full review: security = only 10000/10002 (edge EIP/32) + 5432 (ec2 SG) ingress; 80/30083/22/6443 closed. RDS flags: `deletion_protection=false`, `skip_final_snapshot=true` (noted, not blocking).

**Gate 2 conditions applied (2026-11-26, `rds.tf`):** `deletion_protection=true`, `skip_final_snapshot=false` + `final_snapshot_identifier=edgecloud-db-final-snapshot`, `copy_tags_to_snapshot=true`. fmt+validate pass; plan regenerated: still **42 create / 0 change / 0 destroy**. Plan SHA256 `DBEACD78…C90F`; config mtimes < plan mtime; fresh `tfplan-verify` (with AWS refresh) identical → no drift. **Exact cost (AWS Price List API): guaranteed $100.30/mo** (EC2 $65.41 + EBS $5.47 + IPv4 $7.30 + RDS inst $18.98 + RDS stor $2.62 + SM $0.40 + ECR $0.12 + CW/backups/transfer $0); conditional free-tier (12 mo, if eligible) −$25.37 → **$74.93/mo**.

---

## Errors and fixes

| # | Error found (inspection) | Status | Fix |
|---|--------------------------|--------|-----|
| E1 | `user_data.sh` hardcodes old account ID → first-boot ECR login would fail | **FIXED** | Dynamic `aws_caller_identity` → `account_id` template var; bash uses `$VAR` (no braces) to avoid templatefile interpolation collision |
| E2 | `orchestrator-deployment.yaml` nodeSelector hardcodes old node hostname; sed doesn't match (dots vs dashes) → pod Pending risk | **FIXED** | `node-role: cloud` label on 3 cloud manifests; `06-deploy-k8s.sh` labels the node at deploy time |
| E3 | `security_groups.tf` uses `var.edge_public_ip` (default `""` → invalid `/32`) | **FIXED** | Removed var entirely; KubeEdge 10000/10002 now source from dedicated `aws_eip.edge` (always defined) |
| E4 | Old `terraform.tfstate*`/`tfplan*` belong to suspended account + contain old DB password | **FIXED** | Fresh `infra/terraform-new/` with zero state; original untouched |
| E5 | Profile `edgecloud` pointed to OLD account via expired SSO | **FIXED (Stage 1)** | User reconfigured; verified `171743139339` |
| E6 | Docker Desktop daemon not running (client only) | **OPEN** | User must start Docker Desktop before Stage 4 |
| E7 | `session-manager-plugin` not installed (needed for `aws ssm start-session`) | **OPEN** | `winget install Amazon.SessionManagerPlugin` before Stage 7 interactive access; `send-command` works without it |
| E8 | Doc Step 6 left `edge_public_ip=""` → plan failure | **FIXED** | Var removed; SG reads EIP resource |
| E9 | Scripts inject literal `<CLOUD_PRIVATE_IP>` if rebuild.env empty → broken manifests | **FIXED** | Placeholder normalization in `06-deploy-k8s.sh` + `08-validate.sh`; `00-collect-outputs.sh` auto-derives values |
| E10 | `templatefile()` parsed `${AWS_ACCOUNT_ID}`/`${...}` in user_data.sh comments as template vars → validate error | **FIXED** | All bash vars in user_data.sh use `$VAR` without braces (comment documents constraint) |
| E11 | `providers.tf` hardcodes `Project=edgecloud` while validation gates expect `edge-cloud-orchestrator` | **FIXED** | Tag now `var.project_name` |

Doc-vs-implementation verification: ECR `-target` names in runbook match `ecr.tf` ✅. Script pipeline `00..08` matches README ✅. Runbook 16 phases match `NEW_AWS_ACCOUNT_REBUILD.md` ✅.

---

## Secure access design (Stage 2, requirement 9)

- **No public ingress**: 80/443/30083 removed from cloud SG; edge SG already egress-only.
- **Access path**: AWS SSM Session Manager port forwarding (IAM auth, works from any network, **$0**), documented in `docs/SSM_DASHBOARD_ACCESS.md`.
- **KubeEdge**: 10000/10002 open only from edge node's **Elastic IP/32** (new `aws_eip.edge`).
- **RDS**: private, SG-restricted to cloud node.
- **IAM**: both instance roles attach `AmazonSSMManagedInstanceCore` (statically verified `iam.tf:108`, `edge_node.tf:68`); AL2023 ships ssm-agent; live check deferred to Stage 5.
- **Client VPN**: not selected (costs ~$0.10/hr/connection + endpoint); documented as fallback only.

---

## Validation evidence

- Local tests: `pytest edge/tests cloud/tests scheduler/tests orchestrator/tests` → **131 passed** (2026-11-26)
- Stage 2: `terraform fmt -check` → exit 0 ✅; `terraform validate` in `infra/terraform-new/` → **Success** ✅
- Stage 2: `bash -n` on scripts 00/04/05/06/08 → all OK ✅; placeholder-detection pattern tested (`<MANUAL>` → detected, `10.0.1.5` → not detected) ✅
- Stage 2: `rg` confirms **0** old-account/`edge_public_ip` references left in `infra/terraform-new/` (only an intentional removal-note comment) ✅
- AWS: profile verified Stage 1; no create/update/delete calls yet
- Cluster: pending Stages 7–15
- E2E inference: pending Stage 16

---

## Commands to resume (at current point)

```powershell
# --- GATE 1 (next, needs user approval): terraform init + ECR-only apply ---
# Cost: $0 (ECR repos are free until images are pushed; storage ~$0.10/GB/mo later)
# Region: ap-south-1 | Account: 171743139339 | Profile: edgecloud
terraform -chdir=infra/terraform-new init
terraform -chdir=infra/terraform-new plan -target=aws_ecr_repository.cloud_node `
  -target=aws_ecr_repository.scheduler `
  -target=aws_ecr_repository.orchestrator `
  -target=aws_ecr_repository.edge_node `
  -out=tfplan-ecr
# >>> show plan summary to user, then on approval:
terraform -chdir=infra/terraform-new apply tfplan-ecr

# --- Local prerequisites (user, before later stages) ---
# Stage 4: start Docker Desktop
# Stage 7+: winget install Amazon.SessionManagerPlugin
```

---

## Log

- **2026-11-26** — Stage 0/0b complete. Inspection found 9 issues (E1–E9). No AWS operations performed.
- **2026-11-26** — Stage 1 complete: profile `edgecloud` verified against new account `171743139339`, region `ap-south-1`.
- **2026-11-26** — Stage 2 complete: `infra/terraform-new/` created + validated (fmt/validate ✅); E1–E5, E8–E11 fixed; 5 manifests repointed to new ECR registry; scripts hardened (node naming, `node-role=cloud` labeling, placeholder normalization, AWS CLI flags); zero public ingress in SG; SSM-first access designed and documented (`docs/SSM_DASHBOARD_ACCESS.md`); checklist gates updated. **0 AWS resource-creating calls made.** Gate 1 (ECR targeted apply) approval requested.
- **2026-11-26** — **Gate 1 complete** (user-approved): `terraform init` (local providers, local backend) + targeted plan (4 creates, 0 change, 0 destroy, verified against config mtimes) + `apply tfplan-ecr` → **4 ECR repositories created** in `171743139339`/`ap-south-1`, confirmed live. Outputs: `ecr_cloud_node_url`, `ecr_scheduler_url`, `ecr_orchestrator_url`. Stopped — awaiting Gate 2 approval (Stage 4: Docker image builds/pushes need Docker Desktop; Gate 2 scope = image push to these repos, ~$0). No EC2/VPC/RDS/IAM resources created.
- **2026-11-26** — **Stage 4 complete (fast track):** Docker Desktop daemon running (28.4.0 + buildx 0.28); all 4 Dockerfiles inspected (build from repo root, no app changes); built `edge-node`/`cloud-node` (torch CPU) + `scheduler`/`orchestrator`; ECR login via profile `edgecloud`; pushed all 4 as `:latest`; digests verified in AWS (cloud-node first push hit 20-min timeout, resumed with layer dedup → success).
- **2026-11-26** — **Gate 2 conditions applied + re-verified:** `rds.tf` hardening (deletion_protection, final snapshot, copy_tags); fmt/validate ✅; `tfplan-full` regenerated (42/0/0), SHA256-verified, fresh refresh-plan identical, exact API pricing → guaranteed **$100.30/mo**.
- **2026-11-26** — **Gate 2 approved & executed (hash-verified `tfplan-full`)** → **PARTIAL APPLY**: 39/42 creates succeeded (VPC/subnets/IGW/routes/SGs+rules/EIPs/IAM/Secrets/CW/db-subnet-group/ECR-lifecycle). **3 FAILED**: both `aws_instance` (t3.medium) — `InvalidParameterCombination: not eligible for Free Tier`; `aws_db_instance` — `FreeTierRestrictionError: backup retention exceeds free tier max`. **Root cause:** `aws freetier get-account-plan-state` → `accountPlanType=FREE` (ACTIVE), **credits $100.00** — AWS post-Jul-2025 credit-based Free plan with hard guardrails (eligible EC2 types only: t3.micro/small, t4g.*, c7i-flex.large, m7i-flex.large; RDS feature limits). Idle EIPs accruing ~$7.30/mo against credits. User chose upgrade to Paid plan.
- **2026-11-26** — **Gate 2 POST-UPGRADE verification (all phases, no apply):** Phase 1 — account `171743139339`/`ap-south-1`, `accountPlanType=PAID` ACTIVE, credits **$100.00**, EC2 `run-instances --dry-run t3.medium` → *would have succeeded* (eligibility restored). Phase 2 — `terraform state list` = 45 entries (6 data + **39 managed**); AWS sweep: **zero orphans** (no instances, no RDS, 2 EIPs allocated-unassociated in state, secret has no versions, CW alarm absent from both state+AWS); 3 failed resources confirmed absent everywhere. Phase 3 — fresh `plan -out=tfplan-post-upgrade` (SHA256 `8DD4F906…AE8E`, readable copy `tfplan-post-upgrade.txt`): **7 create / 0 change / 0 destroy** = 39 no-op (all preserved, zero drift) + creates {2× t3.medium instances, RDS retention7+del_protect+final-snapshot, CW alarm, secret version, 2× EIP associations}; security intact (only 3 ingress rules: 10000/10002 edge-EIP + 5432; **no 30083/8000**, edge SG egress-only, EBS gp3 encrypted, SSM attachments ×2). Phase 4 — cost unchanged **$100.30/mo guaranteed** ($100 credits offset month 1); **no AWS Budgets, no billing alarms exist** (proposed, $0). Phase 5 — STOPPED for approval.
- **2026-11-26** — **Gate 2 cost safeguards implemented (no apply):** new infra/terraform-new/cost_alerts.tf (+ cost_alert_email var = vigneshsekar255@gmail.com, us_east_1 provider alias) = SNS topic edgecloud-cost-alerts (us-east-1, billing alarms only exist there) + email subscription (AWS confirmation email required, alerts silent until clicked) + topic policy (owner + budgets.amazonaws.com w/ aws:SourceAccount) + ws_budgets_budget.monthly ** MONTHLY COST** with **ACTUAL 80%** + **FORECASTED 100%** notifications to SNS + ws_cloudwatch_metric_alarm.billing (**AWS/Billing EstimatedCharges > **, Maximum, 6h, us-east-1). **Safeguard pricing: .00/mo** (budget monitoring+notifications free; 2nd CW alarm within 10-alarm free allowance; SNS email within 1k free tier — verified vs AWS Budgets/CloudWatch/SNS pricing pages 2026-11). fmt+validate ✅. **Plan regenerated 	fplan-post-upgrade: 12 create / 0 change / 0 destroy** — JSON-verified: 39 existing = **no-op (zero drift, preserved)**, 0 update/delete/replace; creates = prior 7 (2×t3.medium, RDS retention-7+protections, CPU alarm, secret version, 2× EIP assoc) + 5 safeguards; **no SG/security changes, frontend untouched**. Readable 	fplan-post-upgrade.txt (40,007-byte plan). **SHA256 DED1DC5272BB705817A63DF910241A964E186431BB8BE59008F7FEFCA880CE80**. ⚠️ Post-apply manual steps: (1) click SNS confirmation email, (2) root Billing preferences → enable *Receive CloudWatch Billing Alerts* (list-metrics AWS/Billing currently empty), (3) verify billing metric appears in us-east-1. **STOPPED — awaiting final approval to apply.**


- **2026-11-26 — Post-upgrade Gate 2 apply attempt (approved original hash DED1DC52…CE80):** Exact saved plan hash verified on VICTOS and matched approval. Terraform apply created the two `t3.medium` EC2 instances, RDS PostgreSQL, both EIP associations, DB secret version, CPU alarm, SNS topic, SNS topic policy, SNS email subscription, and billing alarm. Apply then **failed on `aws_budgets_budget.monthly`** because `limit_unit = "AMOUNT"` was rejected by AWS Budgets (`supported unit set: [USD]`). This is a partial apply; **do not re-run the original saved plan**. Terraform state refresh confirms the created resources are tracked. AWS CLI (profile `edgecloud`) independently confirms account `171743139339`; EC2 `i-0086f3895dc6e18ae` and `i-0b0ded3482cd7c747` are both running as `t3.medium` with EIPs `15.252.13.113` and `16.4.59.240`; RDS `edgecloud-db` is `available`, PostgreSQL, private (`PubliclyAccessible=false`), backup retention 7 days, deletion protection enabled. CPU alarm is `OK`. SNS email subscription is `PendingConfirmation` (user must click AWS confirmation email); billing alarm is `INSUFFICIENT_DATA` until root Billing Preferences enables CloudWatch Billing Alerts and metrics populate. **No AWS Budget exists yet.**
- **2026-11-26 — Budget unit correction + refreshed recovery plan (not applied):** Corrected only `infra/terraform-new/cost_alerts.tf` from `limit_unit = "AMOUNT"` to `limit_unit = "USD"` (AWS Budgets API accepted unit). `terraform fmt -check` passed. Full refresh `terraform plan -refresh=true -out=tfplan-after-partial-apply` shows **1 create / 0 change / 0 destroy**, only `aws_budgets_budget.monthly` with USD 110 monthly limit, actual 80% and forecast 100% notifications to the existing SNS topic. Readable plan saved as `tfplan-after-partial-apply.txt`. New plan SHA256: `A9CF09A1E196529496AE7E7C96586CDECEAE2B9E72D68C33E74889AEC59618FE`. This is a new plan after a partial apply and a config correction; it requires separate explicit approval. **STOPPED — not applied.**

## Live deployment continuation: KubeEdge routing and E2E inference (2026-11-26)

### CloudCore routing repair
- Diagnosed a stalled CloudCore rolling update: the Deployment used host ports 10000-10004, so the surge pod could not schedule on the same cloud node. Preserved the original pod and changed the Deployment update strategy to `Recreate`; rollout then completed with one CloudCore pod Ready.
- Patched the live `cloudcore` ConfigMap: `modules.dynamicController.enable=true` and `modules.router.enable=true`. Verified both values after restart; CloudCore listens on TCP 9443.
- Confirmed the installed KubeEdge v1 RuleEndpoint schema uses `spec.ruleEndpointType` and `spec.properties`, not the older `spec.type`/`spec.rest`/`spec.servicebus` fields. Applied `rest-source` and `servicebus-target` RuleEndpoints in namespace `edgecloud`, plus the existing four Rules: `/health`, `/metrics`, `/detect`, `/detect/video`.
- ServiceBus target port 8000 matches the edge-node deployment's HTTP listener on 8000. Edge node pod is Ready on edge EC2 with host networking.

### Verified end-to-end cloud-to-edge tests
- From Cloud EC2, GET `http://127.0.0.1:9443/edge-ec2-node/edgecloud/health` returned HTTP 200 from the edge-node FastAPI app. Body reported `status=degraded`, `model_loaded=true`, `camera_open=false`; camera is not attached in this EC2 deployment, so the service reports degraded health while remaining responsive.
- GET `/metrics` through the same CloudCore route returned HTTP 200 and edge resource metrics (CPU 0.5%, RAM 26.1%, disk 20.1% at test time).
- POST `/detect` through CloudCore using repository `Sampleimage.jpg` returned HTTP 200, YOLOv8n result with 3 detections (`cup`, `book`, `clock`), model inference 1679.41 ms on the first cold request and HTTP total 1.696 s. This confirms actual REST -> CloudCore Router -> EdgeHub/ServiceBus -> edge application -> response path.
- The KubeEdge REST router and ServiceBus are now functionally proven for health, metrics and image inference. The `/detect/video` Rule is installed but has not yet been exercised with a video fixture.

### Preliminary cloud vs edge inference timing
- Ran four matched POST requests per target with the same repository `Sampleimage.jpg`, confidence 0.25, and identical YOLO request body. Timings below are observed on Cloud EC2 via localhost for cloud inference and via CloudCore REST Router for edge inference.
- Cloud `/infer`: first cold request 6069.9 ms total (5793.9 ms model); warm requests 118.4, 103.7, 105.2 ms total. Warm model times 108.8, 96.3, 98.2 ms.
- Edge `/detect` through KubeEdge: four warm requests 102.7, 105.4, 104.4, 106.3 ms total; model times 88.8, 88.3, 85.9, 86.0 ms.
- Excluding cloud's first cold-start request, warm median total latency: cloud 105.2 ms; edge-through-router 104.9 ms. Warm median model inference: cloud 98.2 ms; edge 87.2 ms. On this single image/sample and short run, edge model time was about 11% lower; total request latency was effectively equal. This is preliminary, not a statistically robust performance claim.

### Current caveats / next validation
- Edge `/health` body is `degraded` because `camera_open=false`; `model_loaded=true` and inference succeeds with supplied images. Do not describe camera capture as verified.
- Direct cloud-to-edge TCP:8000 from Cloud EC2 timed out, as expected under the deliberately restricted security-group policy; KubeEdge router path succeeds without opening that port publicly.
- CloudCore logs show a `DeviceStatus` RBAC forbidden warning and repeated `no kind is registered for type v1.Rule` warnings. Despite these warnings, the actual REST->ServiceBus inference path succeeds. Investigate whether these warnings affect rule status reporting or future restarts.
- Kubernetes API log proxy to edge kubelet port 10350 returned 502 during `kubectl logs`; this did not affect edge pod readiness or routed inference.
- Remaining: exercise `/detect/video` with a real video sample; run a longer benchmark (warm-up + >=30 requests, p50/p95, repeated images); inspect/fix CloudCore RBAC/scheme warnings; verify SNS confirmation and billing-alert prerequisites separately.


### Additional warm-path smoke benchmark (2026-11-26)
- Repeated the cloud-to-edge REST Router /detect request 10 times using the same synthetic 64x64 PNG payload (valid image, blank uniform content; therefore 0 detections expected). All 10 requests returned HTTP 200.
- End-to-end round-trip: min 131.92 ms, mean 137.82 ms, p50 137.53 ms, p95 141.68 ms, max 142.92 ms.
- Edge model inference: mean 127.26 ms, p50 127.78 ms, max 131.31 ms.
- These numbers are a routing/model smoke benchmark only, not a comparison against cloud inference; use the repository sample image and matched payloads for comparative claims.
- Re-verified all four KubeEdge Rules (health-route, metrics-route, detect-route, video-route), both RuleEndpoints, CloudCore 1/1 Running, and all four application deployments 1/1 Running.
- /detect/video remains untested because the repository contains no video fixture. EdgeCore logs show EdgeStream's optional TLS tunnel to CloudCore port 10004 timing out; REST Router + ServiceBus inference continues to work. Keep this as a separate follow-up; do not open additional network ports without checking Terraform SG rules and the need for EdgeStream.

### Extended performance validation and scheduler cache experiment (2026-11-26)
- Completed matched inference benchmark: 100 Cloud and 100 Edge requests using the same Sampleimage.jpg, confidence 0.25; 200/200 HTTP 200; both targets consistently detected book, clock and cup.
- Completed full /orchestrate live-metrics benchmark: 100/100 HTTP 200; all 100 selected Edge; no fallback. Mean scheduler/inference/total latency at C1/C2/C4/C8: 1107.42/116.50/1223.95; 1131.73/122.88/1254.63; 1461.64/211.44/1673.11; 2315.56/568.60/2884.18 ms.
- Completed scheduler-only benchmark from inside orchestrator pod via scheduler.edgecloud.svc:8002: 100/100 successful, all Edge; mean decision latency C1/C2/C4/C8: 1111.89/1303.29/1476.33/2044.66 ms.
- Root cause investigation: scheduler config default metrics_ttl_sec=0.0; live Deployment has no SCHEDULER_METRICS_TTL_SEC env var. Cloud and Edge MetricsCollector.collect() call psutil.cpu_percent(interval=1.0). The metrics client already fetches edge metrics, cloud metrics and Cloud /health latency concurrently; /health is intentionally never cached.
- Isolated in-process A/B inside scheduler pod: TTL 0, 10 decisions mean 1193.53 ms / median 1150.29 ms; TTL 2s, first cold 1182.59 ms then 9 warm decisions mean 66.19 ms / median 85.01 ms. The live Deployment was not changed during this A/B.
- Next: back up the live scheduler Deployment, apply SCHEDULER_METRICS_TTL_SEC=2, verify rollout, repeat full orchestrator benchmark, and retain rollback option. This change is not yet deployed.
- Evidence summaries and validation report saved under docs/benchmarks.

### Scheduler metrics cache deployed and revalidated (2026-11-26)
- Applied SCHEDULER_METRICS_TTL_SEC=2 to live scheduler Deployment after isolated A/B demonstrated that warm decisions could fall from ~1.19 s mean to ~66 ms mean (9 warm requests; isolated process only).
- Scheduler rollout successful: new scheduler pod 1/1 Ready; env verified as SCHEDULER_METRICS_TTL_SEC=2. Local infra/k3s/scheduler-deployment.yaml updated; pre-change local manifest backed up in docs/benchmarks/scheduler-deployment-before-ttl-20261126.yaml; pre-change live Deployment YAML backed up on Cloud EC2 at /tmp/cloud13-scheduler-deployment-before-ttl-20261126.yaml.
- Five-request post-rollout smoke: HTTP 200 for all; Edge selected; 3 detections each; scheduler latency 1191.18 ms cold then 30.31/28.93/29.19/30.43 ms.
- Post-TTL full /orchestrate benchmark: 100/100 HTTP 200, all Edge, no fallback. Scheduler mean 487.85 ms vs pre-TTL 1504.09 ms (-67.6%); total mean 811.88 ms vs 1758.97 ms (-53.8%); total median 497.18 ms vs 1295.94 ms (-61.6%); total p95 2001.96 ms vs 3289.16 ms (-39.1%).
- High concurrency still increases latency (C8 total mean 1464.51 ms); p95 includes cache-refresh spikes. Inference mean increased in the second run, so no claim of faster model execution.
- Post-rollout health: Orchestrator and Cloud ok; Edge responds HTTP 200 but remains degraded because no camera is attached. CloudCore and all application pods are Ready.
- Post-change summaries saved under docs/benchmarks; the live deployment backup and local manifest backup are retained for rollback.

### Cloud-to-Edge video forwarding validation (2026-11-26)
- Confirmed the live KubeEdge Rule video-route exists and maps REST /detect/video to ServiceBus /detect/video.
- Generated a 30-frame, 10 FPS AVI/Motion-JPEG fixture from Sampleimage.jpg (single still image repeated; 1,576,382 bytes).
- POSTed multipart video to CloudCore REST Router /edge-ec2-node/edgecloud/detect/video.
- frame_step=1: HTTP 200; client RTT 2.500 s; Edge service elapsed 2423.0 ms; total_frames=30; frames_processed=30; effective_fps=12.38; detections cup=30, book=30, clock=29.
- frame_step=5: HTTP 200; client RTT 0.693 s; Edge service elapsed 538.1 ms; total_frames=30; frames_processed=6; effective_fps=11.15; detections cup=6, book=6, clock=5.
- Result: multipart batch-video forwarding and frame sampling are verified over CloudCore REST Router / KubeEdge ServiceBus.
- Boundary: the test clip repeats one still image. It does not validate real motion, camera capture, live streaming or video accuracy. Edge health continues to report camera_open=false.
- Evidence summary saved as docs/benchmarks/cloud13_video_forwarding_20261126.json. Test fixture remains temporarily on Cloud EC2 at /tmp/cloud13_test.avi.

### CloudCore DeviceStatus RBAC correction (2026-11-26)
- CloudCore service account kubeedge/cloudcore lacked get/list/watch for devices.kubeedge.io/devicestatuses. This is a separate DeviceStatus CRD used by KubeEdge v1.23.
- Added infra/k3s/cloudcore-devicestatus-rbac.yaml with additive ClusterRole + ClusterRoleBinding granting only get/list/watch on devicestatuses to kubeedge/cloudcore.
- Applied live without restarting CloudCore. Verified kubectl auth can-i get/list/watch = yes; kubectl get devicestatuses returns No resources found rather than Forbidden; after 30 seconds, no new DeviceStatus Forbidden logs observed. Edge health remains HTTP 200.
- Remaining: unknown field failMessages/successMessages warnings continue around UpdateRulestatus successfully. The Rule CRD schema has these status properties; no speculative CRD modification was made because routing works and exact warning origin remains unconfirmed.
- Evidence saved in docs/benchmarks/cloud13_cloudcore_rbac_audit_20261126.json.

### Controlled Cloud-offload branch validation (2026-11-26)
- Submitted 5 full /orchestrate requests with explicit synthetic metrics to force the Cloud branch: Edge CPU/RAM/Disk 95/90/95%; Cloud CPU/RAM/Disk 15/25/30%; network latency 30 ms.
- All 5 requests returned HTTP 200; selected_target=cloud and actual_target=cloud; no fallback; 3 detections each (book, clock, cup).
- Scheduler latency: 14.39, 41.62, 13.03, 13.35, 13.35 ms (mean 19.15 ms).
- First Cloud inference was cold at 2794.35 ms; the following four warm requests averaged 191.92 ms inference and 212.28 ms total.
- Result: Cloud offload through the full orchestrator and Cloud inference service is verified with controlled synthetic metrics. This does not prove live-metrics Cloud selection or automatic failure failover.
- Evidence saved as docs/benchmarks/cloud13_orchestrator_cloud_branch_20261126.json.

### Repository regression validation (2026-11-26)
- Ran python -m pytest -q from the project root after the deployment-manifest and RBAC changes.
- Result: 131 passed in 20.84 seconds; exit code 0.
- YAML parsing succeeded for infra/k3s/scheduler-deployment.yaml (Deployment) and infra/k3s/cloudcore-devicestatus-rbac.yaml (ClusterRole + ClusterRoleBinding).
- git diff --check reported no whitespace errors; Git displayed only line-ending conversion warnings for existing working-copy files.


### Bidirectional inference failover implemented, deployed and validated (2026-11-26)
- Implemented symmetric high-priority failover: Edge -> Cloud and Cloud -> Edge, with health-check of the alternate node. 4xx client errors are never retried; low/medium priority workloads retain the no-failover policy; fallback-target failures return a controlled 503 with both errors.
- Added five regression tests; full repository suite now 136 passed, 0 failed (13.22 seconds).
- Built and pushed ECR immutable tag failover-20261126, digest sha256:3b561a55d8430d853226c28c28f420428657e0ca0870fe129683a27f5629a910. Docker Hub base-image metadata fetch timed out; the code-only layer was built from the already-cached local orchestrator:0.1.0 base (digest sha256:3164699333bf732646c315b0c52be6a4ee9222136b4ed014a6a874c85ee44969), with no dependency changes.
- Deployed to live orchestrator; rollout 1/1 Ready. Local orchestrator manifest updated to immutable tag; prior manifest retained in docs/benchmarks.
- Edge -> Cloud route-failure injection: temporarily changed only the orchestrator Edge URL to 127.0.0.1:9. High-priority workload selected Edge, hit connection refused, health-checked Cloud and succeeded on Cloud. HTTP 200; fallback=true; 3 detections; scheduler 151.62 ms; inference 144.26 ms; total 456.22 ms. Original Edge URL restored and verified.
- Cloud -> Edge route-failure injection: temporarily changed only the orchestrator Cloud URL to 127.0.0.1:9. High-priority workload selected Cloud, hit connection refused, health-checked Edge and succeeded on Edge. HTTP 200; fallback=true; 3 detections; scheduler 194.01 ms; inference 171.63 ms; total 491.78 ms. Original Cloud URL restored and verified.
- Important boundary: the orchestrator's upstream route was made unreachable for each test; the actual Edge and Cloud inference Deployments were not stopped. This validates connection failure and failover logic, not node/process crash recovery.
- Post-restore normal Edge and Cloud requests each returned HTTP 200, no fallback, 3 detections. Orchestrator, Scheduler, Cloud and Edge Deployments are all 1/1 Ready. Edge health continues to report camera_open=false while model_loaded=true.
- Evidence: docs/benchmarks/cloud13_bidirectional_failover_20261126.json and docs/benchmarks/CLOUD13_PERFORMANCE_VALIDATION_20261126.md.

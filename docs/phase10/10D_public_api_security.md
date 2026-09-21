# Phase 10 — Gate 10D: Public Orchestrator API `:30083` Security — NOT IMPLEMENTED

**Date:** 2026-09-02
**Predecessor:** Gate 10C (NOT IMPLEMENTED / PASS WITH LIMITATION, `docs/phase10/10C_tls.md`)
**Gate:** 10D — "investigate public `:30083` NodePort (orchestrator public plain-HTTP API); if closing it needs a new ALB/Route53/Terraform/SG change/cost → STOP for approval."
**Scope:** **Documentation only.** Read-only investigation of live vs desired (Terraform) security posture for the public orchestrator API. **No production change.** The live Security Group / Terraform drift is NOT reconciled; no `terraform apply`; no SG alteration; no ALB/Route53/TLS/auth work begun.

## STATUS: STOPPED / NOT IMPLEMENTED
## VERDICT: PASS WITH LIMITATION

**Reason:** A live Security-Group / Terraform drift was discovered affecting the public orchestrator API. Remediation would modify production security infrastructure, or introduce new public-facing infrastructure, and therefore requires explicit approval outside this investigation-only gate.

---

## Read-only evidence

### 1. Current live Security Group rules

Live SG `edgecloud-ec2-sg` (sg-09aada8e7591efe3e, vpc-085fedc9cda6619be), inbound:

| port | CIDR | description |
|---|---|---|
| 80 | `0.0.0.0/0` | Orchestrator public HTTP API |
| 443 | `0.0.0.0/0` | HTTPS (future TLS) |
| **30083** | **`0.0.0.0/0`** | (empty) — orchestrator NodePort, **whole internet** |
| 10000 | `0.0.0.0/0` | (empty) — CloudHub WS, whole internet |
| 10002 | `0.0.0.0/0` | (empty) — CloudHub HTTPS, whole internet |

Outbound: `-1 0.0.0.0/0` (all).

### 2. Current Terraform configuration for the relevant SG rules

`infra/terraform/security_groups.tf`:
- `ec2_http` → `0.0.0.0/0` :80 ("Orchestrator public HTTP API")
- `ec2_https` → `0.0.0.0/0` :443 ("HTTPS (future TLS)")
- `ec2_orchestrator_nodeport` → **`${var.edge_public_ip}/32`** :30083 ("K8s NodePort orchestrator - edge node only")
- `ec2_kubeedge_ws` → `${var.edge_public_ip}/32` :10000
- `ec2_kubeedge_https` → `${var.edge_public_ip}/32` :10002

(Live uses `var.edge_public_ip` = `103.206.105.83`.)

### 3. Current Terraform state for those rules

`terraform.tfstate` (and `.backup`) agree with source — all three of 30083/10000/10002 are `103.206.105.83/32`; 80/443 are `0.0.0.0/0`. RDS 5432 referenced-SG only.

### 4. Exact difference between desired and live state (the drift)

| rule | Terraform (desired) | Live SG | drift |
|---|---|---|---|
| 30083 | `103.206.105.83/32` | **`0.0.0.0/0`** | broader (public) |
| 10000 | `103.206.105.83/32` | **`0.0.0.0/0`** | broader (public) |
| 10002 | `103.206.105.83/32` | **`0.0.0.0/0`** | broader (public) |
| 80 | `0.0.0.0/0` | `0.0.0.0/0` | in sync |
| 443 | `0.0.0.0/0` | `0.0.0.0/0` | in sync |

=> The live SG is materially broader than Terraform for the three "edge node only" rules. This is **infrastructure/security drift** and requires an explicit decision before remediation.

### 5. Current public exposure of `:30083` (verified from public internet)

- `13.206.229.162:30083/health` → **HTTP 200** (`{"status":"ok","service":"orchestrator",...}`)
- `13.206.229.162:30083/` → **HTTP 200** (`endpoints: ["/health","/orchestrate","/docs"]`)
- `:30083` TCP → **OPEN** from an external client

### 6. Whether `:80` / `:443` have listeners

- `:80` and `:443` → **no listener** (connection refused from public client). The SG allows them, but no service binds them; they are idle/reserved ("future TLS").

### 7. Whether any existing ingress / load-balancer infrastructure exists

- K8s: the **only** NodePort/LoadBalancer service is `edgecloud/orchestrator` (NodePort 30083, `loadBalancer: {}`). **No** Ingress objects; **no** nginx-ingress/traefik/LB/haproxy controller pods.
- Terraform state: no `aws_lb`/`aws_alb`/`aws_lb_listener`/`aws_lb_target_group`/`route53`/ingress resources. Only an EIP + EIP-association (the public `13.206.229.162`) onto the cloud EC2.
- => **No existing ingress/ALB/Route53 infrastructure exists.** The public surface today is simply the NodePort via EIP + the broad SG rule.

### 8. Whether authentication exists on the orchestrator API

- `orchestrator/api/app.py` adds **only** permissive CORS (`allow_origins/methods/headers = ["*"]`). No auth middleware, no login/token/bearer/API-key dependency. `POST /orchestrate`, `/docs`, `/health` are unauthenticated.
- => **No authentication** on the orchestrator API.

### 9. Whether port `9443` remains externally blocked

- `13.206.229.162:9443` → **not reachable** (timeout) from public client. CloudCore Router REST `:9443` remains **internal-only** and is **not** exposed through the Cloud SG (no `9443` inbound rule).

### 10. Whether edge `:8000` remains externally blocked

- `13.206.229.162:8000` (and the edge's own public surface) → **not reachable** (timeout) from public client. Edge `:8000` remains blocked / **internal-only**. Unchanged.

---

## Security impact

- **`:30083` is currently publicly reachable** from the whole internet (`0.0.0.0/0`).
- It is **plain HTTP** (no transport encryption to the public client).
- It has **no authentication** (unauthenticated `/orchestrate`, `/docs`, `/health`).
- **This is a security limitation.** The unauthenticated public API on plain HTTP allows anyone to invoke orchestrations once reachable. Do not minimize this exposure; do **not** claim the public API is secure.
- This is **separate from CloudCore `:9443`.** CloudCore Router REST `:9443` remains **internal-only** (the 10C concern, separate, plaintext-internal, not publicly reachable).
- **edge `:8000` remains blocked** (external), unchanged.
- Secondary finding (same drift family): CloudHub `10000`/`10002` are also `0.0.0.0/0` live vs `/32` in Terraform — same drift, recorded here; their transport is already TLS (CloudHub), but the ingress scope is still broader than Terraform. This is a latency/privacy/abuse exposure (external parties can attempt CloudHub handshakes). Listed for the same future remediation decision.

---

## Options to record for future approval (NOT implemented)

Do not choose among these automatically — each needs explicit approval.

**OPTION A — Restore the intended edge/admin `/32` restriction through Terraform.**
Narrow live SG 30083/10000/10002 from `0.0.0.0/0` → `103.206.105.83/32` and run `terraform apply` to converge state. Removes the public orchestrator API and the CloudHub external exposure. Requires SG + Terraform change.

**OPTION B — Replace direct public NodePort exposure with an approved HTTPS architecture (ALB/443) with authentication, Terraform-managed.**
Keep a public orchestrator API but terminate TLS at an ALB on 443, add authentication, backed by new Terraform (ALB/listener/target-group, possibly Route53) and app auth code. Introduces new infra + recurring cost.

**OPTION C — If the public HTTP endpoint is intentionally required for the demonstration, explicitly approve and document that security tradeoff.**
Accept the current public plain-HTTP unauthenticated `:30083` as the intended demo API (the project docs invoke `curl http://13.206.229.162:30083/orchestrate`), fix Terraform source/state to reflect that intent, and record the explicit security acceptance.

No option was chosen or implemented during 10D.

---

## No-change confirmation

- Live Security Group: **not modified**.
- Terraform: **no `terraform apply`; no code change.**
- ALB / Route53 / listeners / target groups: **none created.**
- Or Security Group / authentication / orchestrator / `:30083` / CloudHub ports: **none changed.**
- CloudCore, scheduler, edge, rules, services: **unchanged.** No rollout, no IAM change.

## Recommended remediation

(Recommendation for the future approval step, not performed now.) **Option A (restore `/32` via Terraform) is the smallest, lowest-cost, no-new-infra path and removes the public unauthenticated API and the CloudHub external exposure.** If the public orchestrator API must remain for the capstone demo, **Option C** (explicit documented approval of the public plain-HTTP no-auth API) or **Option B** (public HTTPS + auth via ALB) apply — both need explicit sign-off and, for B, a cost/architecture review. Given the capstone demo value of a reachable public API, the choice between A and C hinges on whether the demo requires an external (non-edge-IP) client to call `/orchestrate`.

## Rollback considerations

- Because **nothing was changed**, no rollback is required. If a future remediation (A/B/C) is approved and applied, this report documents the exact pre-remediation live rules (SG table above) and Terraform state as the rollback reference.

---

## Decision

**Gate 10D: STOPPED / NOT IMPLEMENTED — PASS WITH LIMITATION.**
Drift (live `0.0.0.0/0` vs Terraform `/32`) documented with read-only evidence; security impact stated without minimization; options A/B/C recorded for future approval; **no production security change made**. Awaiting explicit approval before any SG/Terraform/ALB/auth work.

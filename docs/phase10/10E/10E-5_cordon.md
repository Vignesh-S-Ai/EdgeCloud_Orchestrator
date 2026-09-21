# Gate 10E-5 — Remediation: Cordon `wsl2-edge-node`

**Date:** 2026-09-02
**Gate:** 10E-5 remediation — controlled, minimal, **reversible** cordon of the out-of-scope re-registered `wsl2-edge-node` so a future 10E-5 retry cannot be placed onto a node whose kubelet returns ECR 403 (`ImagePullBackOff`).
**Result:** CORDON COMPLETE. **Only `wsl2-edge-node` was cordoned.** No deletion, no drain, no scheduler/cloud-node deployment, image, environment, Service, Rule, RuleEndpoint, CloudCore, EdgeCore, Terraform, IAM, SG, or ECR change was made. Production health unchanged. **10E-5 NOT retried (per gate).**
**Evidence source:** live `kubectl` via SSM on cloud host `i-07ecfbdd7781c5ef5` (kubeconfig `/etc/rancher/k3s/k3s.yaml`).

---

## A. Reason for the cordon

The 10E-5 rollout was previously STOPPED because the new `scheduler:10e-4` pod was scheduled onto the **re-registered** `wsl2-edge-node` (re-registered 2026-09-02T12:58:59Z), whose kubelet/containerd returned **`403 Forbidden`** on the ECR manifest HEAD, producing `ImagePullBackOff` and a stuck rollout (full record: `10E-5_production_validation.md`). The read-only investigation (`10E-5_remediation_plan.md`) confirmed:

- `wsl2-edge-node` was `Ready`, **taint-free**, `unschedulable` not set → fully schedulable; and
- `scheduler` and `cloud-node` Deployments have **no `nodeSelector`/affinity/tolerations** → a rollout pod can land on any Ready node, hence onto wsl2.

**Cordon** sets `spec.unschedulable=true` → no new pod is placed there, directly preventing the 403-pull blocker for `scheduler`, `cloud-node`, or any future rollout. Because **0 pods ran on wsl2**, no drain/eviction was needed and there was no workload disruption.

---

## B. Before state (captured immediately prior)

- **Nodes:**
  - `edge-ec2-node` → Ready, `unschedulable=<none>`
  - `ip-10-0-1-113` (cloud CP) → Ready, `unschedulable=<none>`
  - `wsl2-edge-node` → Ready, `unschedulable=<none>` (i.e. **schedulable**)
- **wsl2 `spec.unschedulable`:** unset/empty
- **Pods on wsl2-edge-node:** **0** (`kubectl get pods -A --field-selector spec.nodeName=wsl2-edge-node` → "No resources found")
- **Production workload count:** **4** pods, all `Running/Ready`, `RESTARTS=0`:
  - `cloud-node-6d9f488769-c5pph` (1/1, 23h) — cloud node
  - `edge-node-6699b48fb-bxjcw` (1/1, 96m) — edge-ec2-node
  - `orchestrator-5d76f94584-lpx97` (1/1, 24h) — cloud node
  - `scheduler-6dcbffbcdb-2kktm` (1/1, 15d) — cloud node, image `scheduler:latest`, env `SCHEDULER_PORT=8002`/`SCHEDULER_LOG_LEVEL=INFO` only (exact pre-10E-5 state)
- **Scheduler health (before):** `/decision` → **200**, `target=edge`, score 82.2

---

## C. Exact command/action performed

```bash
kubectl cordon wsl2-edge-node
```

Output: `node/wsl2-edge-node cordoned`

**This was the ONLY action.** No other Kubernetes object, AWS resource, file, image, or config was touched (see section G).

---

## D. After state (captured immediately following)

- **Nodes:**
  - `edge-ec2-node` → Ready, `unschedulable=<none>` (**unchanged**)
  - `ip-10-0-1-113` (cloud CP) → Ready, `unschedulable=<none>` (**unchanged**)
  - `wsl2-edge-node` → **Ready, SchedulingDisabled**, `unschedulable=true`
- **wsl2 `spec.unschedulable`:** `true`
- **wsl2 taint (from `kubectl describe node`):** `node.kubernetes.io/unschedulable:NoSchedule`; `Unschedulable: true`
- **Pods on wsl2-edge-node:** still **0**
- **Production workload count:** still **4**, all `Running/Ready`, `RESTARTS=0` (same pod names — no respawn, no eviction)
- **Scheduler pod:** unchanged `scheduler-6dcbffbcdb-2kktm` (1/1, RESTARTS=0, still `:latest`, no cache env)
- **Scheduler health (after):** `/decision` → **200**, `target=edge`, score 81.49

---

## E. Workloads on the node — before / after

| Metric | Before | After |
|--------|--------|-------|
| Pods on `wsl2-edge-node` | 0 | 0 |
| Prod pods total | 4 | 4 |
| Prod pods evicted/drained | — | 0 |

No pod was moved, evicted, or rescheduled by the cordon.

---

## F. Production health — before / after

| Check | Before | After |
|-------|--------|-------|
| cloud-node | 1/1 Running RESTARTS=0 | 1/1 Running RESTARTS=0 |
| edge-node | 1/1 Running RESTARTS=0 | 1/1 Running RESTARTS=0 |
| orchestrator | 1/1 Running RESTARTS=0 | 1/1 Running RESTARTS=0 |
| scheduler | 1/1 Running RESTARTS=0 | 1/1 Running RESTARTS=0 |
| scheduler API `/decision` | 200 | 200 |
| edge-ec2-node | Ready | Ready |
| cloud node | Ready | Ready |

All production components remain healthy and unchanged.

---

## G. Confirmation — no unrequested changes

The intent of this gate was to cordon **only** `wsl2-edge-node`. Confirmed **NOT performed** — no drain, no node deletion, no scheduler source change, no scheduler Deployment change, no scheduler environment change, no cloud-node Deployment change, no `nodeSelector`/`affinity`/`tolerations` added, no Service/Rule/RuleEndpoint change, no CloudCore/EdgeCore change, no WSL2 EdgeCore stop, no Terraform/IAM/SG/ECR change, **no scheduler image deployment, and no benchmark**. `10E-5` was **not retried**; the scheduler remains the exact pre-10E-5 `:latest` image with only `SCHEDULER_PORT`/`SCHEDULER_LOG_LEVEL` env.

---

## H. Reversibility

- **Cordon is fully reversible:** `kubectl uncordon wsl2-edge-node` restores schedulability (`spec.unschedulable` removed, `ready` again). 
- Because no pods were on the node and nothing was drained/deleted, uncordon restores the pre-cordon topology exactly.

---

## I. Note on durability

The cordon is the **immediate, AWS-reachable, reversible** fix for the 10E-5 blocker. It does **not** permanently prevent the WSL2 VM from re-registering if its local EdgeCore is restarted after `uncordon`, or a new node object appears (Phase 9 §9E). The durable fix is out of AWS reach: on the user's WSL2 VM, `sudo systemctl stop edgecore && sudo systemctl disable edgecore` (per `10E-5_remediation_plan.md` §E/F, **not executed** here).

---

10E-5 CORDON STATUS: COMPLETE
File: docs/phase10/10E/10E-5_cordon.md
Production change: wsl2-edge-node cordoned ONLY
Scheduler deployment: NOT RETRIED
Next action: REVIEW CORDON RESULT

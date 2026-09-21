# Gate 10E-5 — Remediation Plan: Stale `wsl2-edge-node` Placement Problem

**Date:** 2026-09-02
**Gate:** 10E-5 remediation — READ-ONLY investigation of why the scheduler deployment was placed on the re-registered `wsl2-edge-node` and the safest remediation before retrying 10E-5.
**Result:** Investigation COMPLETE. **NO production change made (read-only).** Remediation is planned but NOT executed (requires approval per gate).
**Evidence source:** live `kubectl`/SSH inspection on cloud host `i-07ecfbdd7781c5ef5` (kubeconfig `/etc/rancher/k3s/k3s.yaml`), plus `docs/phase10/10E/10E-5_predeploy.md`, `10E-5_production_validation.md`, `10E-4_implementation.md`, `docs/PHASE9_PRODUCTION_HARDENING_REPORT.md` (§9E).

---

## A. Exact root cause of the placement problem

The `scheduler` Deployment has **no `nodeSelector`, no `affinity`, and no `tolerations`** (verified via `kubectl get deploy -n edgecloud scheduler -o json` → `nodeSelector: None`, `affinity: None`, `tolerations: None`). The default k3s scheduler will therefore place a new rolling-update pod on **any Ready, schedulable node**.

On 2026-09-02T12:58:59Z the **`wsl2-edge-node` re-registered** (the local WSL2 VM's EdgeCore process came back — the exact behavior Phase 9 §9E warned about: *"if powered on it will attempt to re-register a node named wsl2-edge-node"*). It is:
- `Ready` / `STATUS=True` with the KubeEdge `EdgeReady` condition,
- **no taints** (`taints: None`), **no `unschedulable`** (`None`), no `providerID` → **fully schedulable**,
- actively posting: lease `renewTime` 2026-09-02T13:45:49Z (≈4 s before capture), `lastHeartbeat` 13:43:43Z, and an **active CloudCore CloudHub WebSocket ESTAB** on `:10000` (one of the two `ESTAB` lines is the WSL2 VM's egress),
- machineID `f70f61b0882a4f9283de05aa17bb59f0` = WSL2 Ubuntu 24.04 VM (same device as Phase 9).

Because `wsl2-edge-node` is Ready and schedulable and the scheduler deployment is unconstrained, the RollingUpdate (maxSurge 25% → 1 surge pod) for `:10e-4` placed the new pod **onto `wsl2-edge-node`**. That node's kubelet/containerd returned **`403 Forbidden`** on the ECR manifest HEAD (`…/v2/edgecloud/scheduler/manifests/10e-4`), producing `ImagePullBackOff` and a stuck rollout. The image itself is fine (pushed + present in ECR; the cloud node pulls ECR normally).

**Root cause summary:** an unconstrained Deployment + a re-registered, tainted-free, schedulable `wsl2-edge-node` whose kubelet cannot authenticate to ECR (403).

---

## B. Current node topology

| Node | Status | Role | Schedulable? | Pins |
|------|--------|------|--------------|------|
| edge-ec2-node (10.0.1.123) | Ready | agent,edge | yes (no taint) | edge-node pinned here via nodeSelector |
| ip-10-0-1-113 (cloud CP) | Ready | control-plane,master | yes (no taint) | orchestrator pinned here via nodeSelector; hosts scheduler, cloud-node, coredns, metrics-server, local-path-provisioner |
| wsl2-edge-node (172.18.125.42) | Ready | agent,edge | **YES** (no taint, no unschedulable) | none; 0 pods |

- Namespaces: `edgecloud`, `kube-system`, `kube-node-lease`, `kube-public`, `default`, `kubeedge` (kubeedge ns has no pods — CloudCore runs as a host systemd service on the cloud node, not in-cluster).
- 2 live CloudCore CloudHub WS `:10000` connections: `13.206.238.62:54284` (edge-ec2-node) and `103.206.105.86:64030` (wsl2 egress) — both edges actively connected.

---

## C. Why wsl2-edge-node became eligible

1. **Unconstrained deployments:** only `orchestrator` (selector `kubernetes.io/hostname: ip-10-0-1-113`) and `edge-node` (selector `kubernetes.io/hostname: edge-ec2-node`) are pinned. **`scheduler` and `cloud-node` have no selector/affinity/tolerations.**
2. **wsl2 is Ready and taint-free** (no taint, `unschedulable` not set), so the kube-scheduler treats it as an equally valid target. It is also underutilized (0 pods) versus the cloud node (5 system pods + 3 app pods), so a fresh pod is naturally favored there.
3. The `wsl2-edge-node` was **re-registered on 2026-09-02T12:58:59Z** — i.e., it appeared as a Ready node just before the 10E-5 rollout (the 10E-2/10E-3/10E-4 topology had it removed per Phase 9 §9E). Its reappearance is the environmental trigger.

---

## D. Is it safe to remove/cordon the stale node?

**Cordon — SAFE and sufficient for the immediate problem:**
- `kubectl cordon wsl2-edge-node` sets `spec.unschedulable=true` → **no new pod is placed there**, directly preventing the 403-pull blocker for `scheduler`, `cloud-node`, or any future rollout.
- **0 pods currently run on wsl2-edge-node** (verified: `kubectl get pods -A --field-selector spec.nodeName=wsl2-edge-node` → "No resources found", count 0), so **no drain/eviction** is needed and there is zero workload disruption.
- Reversible: `kubectl uncordon wsl2-edge-node`.

**Node removal (`kubectl delete node wsl2-edge-node`) — SAFE but NOT permanent by itself:**
- Works (Phase 9 §9E: the k3s `wrangler.cattle.io/node` finalizer resolves cleanup) and no workload depends on it (0 pods).
- **However, the node will re-register** the moment the local WSL2 EdgeCore posts again. Phase 9 §9E and today's live evidence confirm the WSL2 VM re-registers if it is running. Therefore **deletion alone is insufficient** as a durable fix.

**Health/safety:** wsl2 hosts no production workload, is not referenced by any Rule/Service/CloudCore/EdgeCore-on-EC2 config, and removing it does not touch the ServiceBus, the EC2 edge node, the cloud node, or any prod Deployment. Safe to cordon now; delete only after the WSL2 EdgeCore is stopped locally (F).

---

## E. Exact remediation steps (planned, NOT executed)

**Step 1 — Immediate / AWS-reachable / reversible (core fix for 10E-5):**
1. `kubectl cordon wsl2-edge-node` (prevents all future placement onto the stale node; 0 pods, so no drain needed).
2. (Optional hardening) `kubectl uncordon wsl2-edge-node` if ever intentionally wanted back.

**Step 2 — Definitive / requires local WSL2 access (prevents future re-registration):**
3. On the WSL2 VM (user-local, out of AWS reach): `sudo systemctl stop edgecore && sudo systemctl disable edgecore` (and optionally mask: `sudo systemctl mask edgecore`).
4. Verify no `edgecore` process/registration remains.

**Step 3 — Cleanup (after Step 2), optional:**
5. `kubectl delete node wsl2-edge-node` (redundant with EdgeCore stopped; re-registration no longer possible).
6. Optionally pin `scheduler` and `cloud-node` to the cloud control-plane node via `nodeSelector: {kubernetes.io/hostname: ip-10-0-1-113}` for determinism — **this is a Deployment manifest change that is out of the current 10E-5 scope and needs separate approval.**

**Step 4 — Retry 10E-5 (only after Steps 1–3 complete):**
7. Re-apply the exact same immutable rollout: `kubectl set image deploy/scheduler scheduler=…:10e-4 -n edgecloud` + `kubectl set env deploy/scheduler SCHEDULER_METRICS_TTL_SEC=1.0 -n edgecloud`.
8. Wait rollout; confirm the new pod lands on the cloud node, pulls `:10e-4`, Ready/Running/RESTARTS=0; then run the 10E-5 functional gate + benchmark.

No scheduler code change, no rebuild, no ECR/rule/service/CloudCore/EdgeCore-on-EC2/Terraform/IAM/SG change is required.

---

## F. Does remediation require local WSL2 access?

- **Cordon (Step 1): NO.** Fully achievable from the cloud host via `kubectl` (AWS-reachable). This alone resolves the immediate 10E-5 blocker.
- **Permanent prevention (Step 2): YES.** Stopping/disabling the WSL2 VM's `edgecore` service requires the user's local WSL2 shell (`sudo systemctl stop/disable edgecore`), which is **out of AWS reach** (Phase 9 §9E). Without it, a deleted/cordoned node can reappear if the VM is powered on and EdgeCore restarts, so a durable fix needs that local step (or at minimum, cordon + never powering on the VM's EdgeCore).

---

## G. Do any production workloads depend on the WSL2 node?

**No.** Verified:
- `kubectl get pods -A --field-selector spec.nodeName=wsl2-edge-node` → **0 pods**.
- No Rule/Service/CloudCore/EdgeCore-on-EC2 config references `wsl2-edge-node`; CloudCore `:10000`/`:10002` serve both EC2 edges plus the WSL2 edge, but removing WSL2 does not affect the EC2 edge (edge-ec2-node) or cloud data plane.
- Production placement: cloud-node, orchestrator, scheduler on the cloud node; edge-node (YOLO) pinned to edge-ec2-node. None on wsl2.
- The only deployments that could be affected by wsl2 being schedulable are the **unconstrained** `scheduler` and `cloud-node` — which is precisely the risk being mitigated by cordoning.

---

## H. Risks and rollback

**Risks of cordon:**
- Ordering: cordon is a fast, single-object, reversible change; near-zero risk. If uncordoned, the stale node is schedulable again.
- No pod eviction (0 pods on wsl2) → no availability or data-plane impact.

**Risks of node deletion (without Step 2):**
- Node re-registers if WSL2 EdgeCore runs → ineffective long-term; re-creates the same scheduler-placement hazard. Hence deletion should follow Step 2, or be paired with cordon.

**Risk of cloud-node pinning (proposed but out-of-scope):** changing `cloud-node` Deployment template would trigger a cloud-node rollout — out of the authorized 10E-5 image+env scope; requires separate approval and its own rollback. Not performed.

**Rollback procedure:**
- Cordon → `kubectl uncordon wsl2-edge-node`.
- Node delete → re-run EdgeCore join on WSL2 (out of AWS reach) OR it auto-re-registers when powered on.
- If a 10E-5 retry fails again → repeat the 10E-5 rollback (image `:latest`, remove `SCHEDULER_METRICS_TTL_SEC`), as already executed and proven.

---

## I. Exact changes that WOULD be made (NOT made yet)

- [ ] `kubectl cordon wsl2-edge-node`  (Step 1 — the minimal, AWS-reachable, reversible fix)
- [ ] (user, local WSL2) `sudo systemctl stop edgecore && sudo systemctl disable edgecore`  (Step 2 — durable)
- [ ] (optional) `kubectl delete node wsl2-edge-node`  (Step 3, after EdgeCore stopped)
- [ ] (optional, out-of-scope + separate approval) add `nodeSelector: {kubernetes.io/hostname: ip-10-0-1-113}` to `scheduler`/`cloud-node` Deployments
- [ ] Then retry the identical 10E-5 rollout: `kubectl set image deploy/scheduler scheduler=…:10e-4` + `SCHEDULER_METRICS_TTL_SEC=1.0`

None of the above have been executed.

---

## J. Confirmation — NO production changes made

This investigation was **strictly read-only**. I did **not**:
- delete, cordon, or drain any node
- stop EdgeCore on EC2 or on WSL2
- modify Kubernetes, Deployments, Services, Rules, RuleEndpoints, CloudCore (EC2), EdgeCore (EC2), Terraform, IAM, Security Groups, or ECR
- rebuild or redeploy the scheduler; the production scheduler remains the exact pre-10E-5 state (`:latest`, `SHA256 a3d9079d…`, env `SCHEDULER_PORT`/`SCHEDULER_LOG_LEVEL` only), verified serving `/decision` 200.

All commands were `kubectl get`/`kubectl describe`/`ss` reads (plus the documented report reads).

---

10E-5 REMEDIATION STATUS: COMPLETE
File: docs/phase10/10E/10E-5_remediation_plan.md
Production changes: NONE
Next action: REVIEW REMEDIATION PLAN

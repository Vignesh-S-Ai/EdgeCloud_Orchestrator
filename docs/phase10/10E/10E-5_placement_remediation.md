# Gate 10E-5 — Placement Remediation (nodeSelector pin)

**Date:** 2026-09-02
**Gate:** 10E-5 — infrastructure-correctness remediation, approved after the placement investigation, required before retrying the 10E-5 cache deployment.
**Result:** PLACEMENT REMEDIATION COMPLETE. **Only the `scheduler` and `cloud-node` Deployments were changed (each got a `nodeSelector` = cloud control-plane hostname).** Cache deployment NOT retried; benchmark NOT run. Production topology now correct and healthy.
**Evidence source:** live `kubectl` via SSM on cloud host `i-07ecfbdd7781c5ef5` (`/etc/rancher/k3s/k3s.yaml`).

---

## A. Pre-change state

- **scheduler** Deployment: `replicas=1`, `nodeSelector=null` (no affinity/tolerations/topology), image `…/scheduler:10e-4`, env `SCHEDULER_PORT=8002`/`SCHEDULER_LOG_LEVEL=INFO`/`SCHEDULER_METRICS_TTL_SEC=1.0`. Pod `scheduler-58bdb56bf6-fc4l4` on **`edge-ec2-node` (10.244.0.10)** → **unreachable from cloud** (the 10E-5 retry functional failure).
- **cloud-node** Deployment: `replicas=1`, `nodeSelector=null`, image `…/cloud-node:latest`, env `CLOUD_HOST=0.0.0.0`/`CLOUD_PORT=8001`/`CLOUD_LOG_LEVEL=INFO`. Pod `cloud-node-6d9f488769-c5pph` on **cloud CP node `ip-10-0-1-113…` (10.42.0.19)** — working but unpinned (rollout-vulnerable).
- **orchestrator** pinned to cloud CP node (`kubernetes.io/hostname: ip-10-0-1-113…`); **edge-node** pinned to `edge-ec2-node`.
- Nodes: `edge-ec2-node` Ready; `ip-10-0-1-113…` (cloud) Ready; `wsl2-edge-node` Ready,**SchedulingDisabled** (`unschedulable=true`).
- Prod pods: 4/4 Ready, RESTARTS=0 (cloud-node, edge-node, orchestrator, scheduler).
- Services: cloud-node 10.43.45.189:8001, edge-node 10.43.218.215:8000, orchestrator NodePort 10.43.112.251:8003→30083, scheduler 10.43.201.181:8002. Rules: detect/health/metrics/video. RuleEndpoints: rest-source, servicebus-target.

## B. Exact approved changes

Two `nodeSelector` patches (merge-patch on the pod template only):

```bash
# scheduler
kubectl patch deploy scheduler -n edgecloud --type merge -p \
 '{"spec":{"template":{"spec":{"nodeSelector":{"kubernetes.io/hostname":"ip-10-0-1-113.ap-south-1.compute.internal"}}}}}'

# cloud-node
kubectl patch deploy cloud-node -n edgecloud --type merge -p \
 '{"spec":{"template":{"spec":{"nodeSelector":{"kubernetes.io/hostname":"ip-10-0-1-113.ap-south-1.compute.internal"}}}}}'
```

The hostname string **matches the existing `orchestrator` selector exactly**. No affinity/toleration/topology added; image/env/resources/ports unchanged on both. No other field on either Deployment was altered.

## C. Scheduler placement before / after

| | Before | After |
|---|--------|-------|
| Deployment nodeSelector | `null` | `{"kubernetes.io/hostname":"ip-10-0-1-113…"}` |
| Pod | `scheduler-58bdb56bf6-fc4l4` | `scheduler-796d7db85d-4wx77` |
| Node | `edge-ec2-node` (10.244.0.10) | `ip-10-0-1-113…` (10.42.0.20) |
| Image | `:10e-4` | `:10e-4` (unchanged) |

## D. Cloud-node placement before / after

| | Before | After |
|---|--------|-------|
| Deployment nodeSelector | `null` | `{"kubernetes.io/hostname":"ip-10-0-1-113…"}` |
| Pod | `cloud-node-6d9f488769-c5pph` | `cloud-node-64c498d5cf-cvwj8` |
| Node | `ip-10-0-1-113…` (10.42.0.19) | `ip-10-0-1-113…` (10.42.0.21) |
| Image | `:latest` | `:latest` (unchanged) |

Cloud-node moved from 10.42.0.19 → 10.42.0.21 (still same cloud CP node), now pinned so it can never roll onto an edge node.

## E. Health before / after

| Pod | Before | After |
|-----|--------|-------|
| scheduler | Ready=1/1, RESTARTS=0 (but unreachable) | Ready=1/1, RESTARTS=0, **reachable** |
| cloud-node | Ready=1/1, RESTARTS=0 | Ready=1/1, RESTARTS=0 |
| orchestrator | Ready=1/1, RESTARTS=0 | Ready=1/1, RESTARTS=0 (same pod, unchanged) |
| edge-node | Ready=1/1, RESTARTS=0 | Ready=1/1, RESTARTS=0 (same pod, unchanged) |

- No CrashLoopBackOff, no OOMKilled, no unexpected restarts on any pod.

## F. Network verification (all run from the orchestrator pod on the cloud CP node)

| Check | Result |
|-------|--------|
| scheduler `/health` via ClusterIP | **200** (588 ms) — was ConnectTimeout pre-remediation |
| scheduler `/decision` (live edge, drives scheduler→cloud) | **200** (2070 ms), `target=edge`, score 82.38 |
| cloud `/health` via ClusterIP | **200** (594 ms) |
| edge `/metrics` via ServiceBus (`10.0.1.113:9443/…/edgecloud/metrics`) | **200** (1020 ms) |
| edge `/health` via ServiceBus | **200** (23 ms) |
| direct edge pod IP `10.244.0.9:8000` | **blocked** (ConnectTimeout — no direct path introduced) |
| edge-node ClusterIP `:8000` from cloud | **blocked** (ConnectTimeout — edge access remains ServiceBus-only, as designed) |

- **orchestrator → scheduler `/decision` works**; scheduler reaches **cloud services** (ClusterIP) **and** edge (ServiceBus); edge keeps its **ServiceBus-only** access; **no direct edge pod-network access introduced**.

## G. WSL2 remained cordoned

`wsl2-edge-node` remained `Ready,SchedulingDisabled`, `unschedulable=true` throughout. **Not uncordoned, deleted, or drained.**

## H. No unrelated resources changed

Only the two `nodeSelector` patches were applied to `scheduler` and `cloud-node`. Confirmed **NOT modified**: scheduler/cloud-node source & image & environment, orchestrator (deployment + pod unchanged), edge-node (deployment + pod unchanged), ServiceBus, CloudCore, EdgeCore, Services, Rules, RuleEndpoints, hostPort, node labels, node taints, Terraform, IAM, Security Groups, ECR. Existing Services (4), Rules (detect/health/metrics/video) and RuleEndpoints (rest-source, servicebus-target) verified unchanged.

## I. Rollback procedure

To revert this remediation:
```bash
# scheduler
kubectl patch deploy scheduler -n edgecloud --type json -p \
 '[{"op":"remove","path":"/spec/template/spec/nodeSelector"}]'
# cloud-node
kubectl patch deploy cloud-node -n edgecloud --type json -p \
 '[{"op":"remove","path":"/spec/template/spec/nodeSelector"}]'
```
This returns both to the pre-remediation unconstrained placement (each will then re-schedule anywhere a node is Ready+schedulable — note wsl2 is cordoned, so they'd land on the cloud CP node anyway today, but without a durability guarantee). No image/env/service/rule change is needed to roll back; both rollouts are controlled (maxSurge/maxUnavailable 25%).

## J. Why this establishes the required topology (independent of the cache)

The placement investigation proved the cloud control-plane uses the `10.42.x` pod network while edge nodes run pods on the disjoint `10.244.x` KubeEdge network with **no L3 route between them**. `scheduler` and `cloud-node` are consumed via ClusterIP from the cloud-side (by the orchestrator, which is cloud-pinned) and must reach cloud ClusterIP services, so they must live on the cloud control-plane node. This is a **topology/network requirement that is entirely independent of the 10E-4 cache** — the exact same `:latest` image would have failed identically if rolled onto an edge node. Pinning `scheduler` + `cloud-node` (now matching the already-pinned `orchestrator`) makes future rollouts place them deterministically on the reachable network, which is the necessary precondition for a correct 10E-5 cache deployment and benchmark. The cache itself was **not** deployed or benchmarked here.

---

10E-5 PLACEMENT REMEDIATION: COMPLETE
File: docs/phase10/10E/10E-5_placement_remediation.md
Production changes: SCHEDULER + CLOUD-NODE NODESELECTOR ONLY
Cache deployment: NOT RETRIED
Benchmark: NOT RUN
Next action: REVIEW REMEDIATION RESULT

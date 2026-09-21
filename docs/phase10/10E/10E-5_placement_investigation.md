# Gate 10E-5 — Placement Architecture Investigation (READ-ONLY)

**Date:** 2026-09-02
**Gate:** 10E-5 — after the retry STOP (scheduler landed on `edge-ec2-node` and became unreachable from the cloud control-plane network), determine the minimum placement constraints required for production correctness.
**Result:** INVESTIGATION COMPLETE. **NO production change made.** All findings below are directly observed via live `kubectl` / host inspection on cloud host `i-07ecfbdd7781c5ef5` (`/etc/rancher/k3s/k3s.yaml`).

---

## A. Current node topology

| Node | Role | Internal-IP | Status | Node's declared podCIDR | Actual pod IPs observed | nodeSelector pins (current) |
|------|------|-------------|--------|------------------------|------------------------|-----------------------------|
| `edge-ec2-node` | agent,edge (KubeEdge) | 10.0.1.123 | Ready | `10.42.2.0/24` | **`10.244.0.x`** (edge-node 10.244.0.9, scheduler 10.244.0.10) | edge-node → this node |
| `ip-10-0-1-113.ap-south-1.compute.internal` (cloud CP) | control-plane,master (k3s) | 10.0.1.113 | Ready | `10.42.0.0/24` | `10.42.0.x` (orchestrator .18, cloud-node .19, coredns .3, metrics-server .2, local-path .4) | orchestrator → this node |
| `wsl2-edge-node` | agent,edge (KubeEdge) | 172.18.125.42 | Ready,SchedulingDisabled | `10.42.3.0/24` | 0 pods | none |

- `kube-system`: no network DaemonSet (no flannel/calico controller pods). Only `coredns`, `local-path-provisioner`, `metrics-server`, all on the cloud CP node.
- `kubeedge` ns has no pods (CloudCore runs as a host systemd service on the cloud node, not in-cluster).
- 4 prod pods (ns `edgecloud`): orchestration pinned to cloud CP, edge-node pinned to edge-ec2-node, **scheduler on edge-ec2-node (10.244.0.10)**, **cloud-node on cloud CP (10.42.0.19)**.

## B. Scheduler placement requirements

- The scheduler is consumed **via ClusterIP** (`scheduler.edgecloud.svc:8002`, clusterIP `10.43.201.181`) by the **orchestrator**, which is **pinned to the cloud control-plane node** (`nodeSelector kubernetes.io/hostname: ip-10-0-1-113...`). kube-proxy DNATs the ClusterIP to the endpoint's **pod IP** — so the endpoint pod must sit on a pod network the cloud node can route to.
- The scheduler must also **reach Cloud ClusterIP services** to collect metrics (e.g. `cloud-node.edgecloud.svc:8001` → `10.42.0.19`), i.e. it must be on the cloud pod network (10.42.0.x).
- **Minimum requirement:** the scheduler pod must live on a node whose pod network is the **cloud CP node's 10.42.0.0/24** (i.e. on the cloud control-plane node). Any edge node (10.244.x) fails both directions (see D/E).

## C. Cloud-node placement requirements

- `cloud-node` is also consumed **via ClusterIP** (`cloud-node.edgecloud.svc:8001`, `10.43.45.189` → `10.42.0.19`) by the orchestrator (cloud-pinned) and by the scheduler (when collecting cloud `/metrics`).
- It must be reachable on the cloud pod network. Today it happens to be on the cloud CP node (10.42.0.19), but it has **no nodeSelector**, so a rollout could land it on an edge node → identical unreachability.
- **Minimum requirement:** `cloud-node` must live on the cloud pod network → the cloud control-plane node.

## D. Exact observed network reachability constraints

Directly observed from the cloud CP host (10.0.1.113, `ip route` + `ping`):

- Cloud host route table contains **only one pod-network route**: `10.42.0.0/24 dev cni0` (the cloud node's own k3s bridge, src 10.42.0.1).
- **No route** to `10.244.0.0/24` (edge pod network) and no route to `10.42.2.0/24` (edge-ec2-node's declared podCIDR).
- `ping 10.42.0.3` (cloud pod) → **0% packet loss** (routable).
- `ping 10.244.0.9` (edge pod) → **100% packet loss** (not routable from cloud host).
- From the orchestrator pod (cloud node): `cloud-node.edgecloud.svc` → **200 (~12 ms)**; `scheduler.edgecloud.svc` (→10.244.0.10) → **ConnectTimeout**; direct `10.244.0.10:8002` → **ConnectTimeout**.
- `edge-node` ClusterIP (`10.43.218.215`) → endpoint `10.244.0.9` (edge pod net) → **also not directly reachable via ClusterIP from the cloud node**. This is why the edge app is reached **via ServiceBus/CloudCore** (`http://10.0.1.113:9443/edge-ec2-node/edgecloud`), a **host-network** hop over the VPC (10.0.1.x) — NOT via ClusterIP. That ServiceBus path is the correct, working pattern for edge-access.
- Node **podCIDR mismatch**: `edge-ec2-node` declares `10.42.2.0/24` but its actual pods are `10.244.0.x` (KubeEdge edge CNI IPAM), disjoint from the k3s control-plane bridge `10.42.0.0/24`.

Conclusion (observed): the cloud control-plane and the edge nodes have **two mutually disjoint pod networks** with no L3 route between them. ClusterIP DNATs to the endpoint pod IP; a service whose pod lives on the other network is unreachable from the consumer's network.

## E. Why the scheduler on edge-ec2-node failed

- Rollout placed `scheduler-58bdb56bf6-fc4l4` on `edge-ec2-node` (IP `10.244.0.10`), because the Deployment has **no nodeSelector/affinity/tolerations** and wsl2 was cordoned, leaving edge-ec2-node as the other schedulable target.
- Local kubelet readiness probes on the edge node passed (`Ready=True`, `RESTARTS=0`) — the pod itself ran fine.
- But the orchestrator (cloud CP node) reaches the scheduler **via ClusterIP `10.43.201.181` → DNAT → `10.244.0.10:8002`**. The cloud node has **no route into `10.244.0.0/24`** → every request `ConnectTimeout`. Also, the edge-hosted scheduler cannot reach cloud ClusterIP metrics (`10.42.0.19`) from its disjoint network.
- Net: the scheduler was both **unreachable from the cloud** and (in a live run) **unable to reach cloud ClusterIP services** — a fundamental two-directional network partition, not a code/cache issue.

## F. Minimum safe placement remediation

Pin the two unpinned **cloud-side** Deployments to the cloud control-plane node, matching the established pattern already used by `orchestrator`:

- `scheduler` → `nodeSelector: {kubernetes.io/hostname: ip-10-0-1-113.ap-south-1.compute.internal}`
- `cloud-node` → `nodeSelector: {kubernetes.io/hostname: ip-10-0-1-113.ap-south-1.compute.internal}`

This forces their pods onto `10.42.0.0/24` so ClusterIP endpoints are reachable from the orchestrator and so they can reach each other's ClusterIP services. `edge-node` keeps its existing pin to `edge-ec2-node`; `orchestrator` keeps its existing pin. wsl2 remains cordoned. No pin is needed (and none should be added) to the edge-side workloads.

## G. Whether scheduler ALONE should be pinned

Pinning **only** the scheduler is the **immediate** fix for the current outage (the scheduler is the live failing pod). It restores `/decision` reachability. **However**, it leaves `cloud-node` unpinned and equally exposed: any future `cloud-node` rollout could land it on an edge node and break cloud `/metrics` / ClusterIP reachability the same way. So scheduler-alone is sufficient to unblock now but is **incomplete** for production correctness.

## H. Whether scheduler + cloud-node should both be pinned, with evidence

**Yes — both should be pinned.** Evidence:
- Both are the only two Deployments that are **unconstrained** (**no** nodeSelector — verified `nodeSelector=null` for both, while `orchestrator` and `edge-node` are pinned).
- Both are consumed via ClusterIP by the **cloud-pinned orchestrator** and must reach cloud ClusterIP services, i.e. both must reside on the cloud pod network `10.42.0.0/24` (D).
- `cloud-node` currently happens to be on the cloud CP node (10.42.0.19) only by schedule luck (it predates edge-node re-registration / had capacity there); it has **no guarantee** of staying there, and would fail identically to the scheduler if rolled onto an edge node.
- Pinning both is the minimal set that fully eliminates the class of bug (an unpinned cloud-side Deployment landing on a disjoint-network edge node). Both already effectively operate as cloud-DP services (orchestrator's twin dependencies), so this is correctness, not scope-creep.

## I. Exact proposed nodeSelector / affinity configuration

Add a `nodeSelector` to each Deployment's pod template (no affinity/tolerations needed — no other node type is a valid target, and the target node has no taint):

```yaml
# both scheduler and cloud-node
spec:
  template:
    spec:
      nodeSelector:
        kubernetes.io/hostname: ip-10-0-1-113.ap-south-1.compute.internal
```

Equivalent imperative (for the approved remediation, not run here):
`kubectl patch deploy -n edgecloud scheduler -p '{"spec":{"template":{"spec":{"nodeSelector":{"kubernetes.io/hostname":"ip-10-0-1-113.ap-south-1.compute.internal"}}}}}'`
`kubectl patch deploy -n edgecloud cloud-node -p '{"spec":{"template":{"spec":{"nodeSelector":{"kubernetes.io/hostname":"ip-10-0-1-113.ap-south-1.compute.internal"}}}}}'`

This mirrors the existing `orchestrator` pin verbatim (same hostname label string).

## J. Risks and rollback

- **Risks:** Low. The target node (cloud CP) has capacity (it already hosts orchestrator, cloud-node, and 3 system pods; load was idle, ~1375 MB / 3835 MB used at baseline). Both pods are 1-replica; the pin triggers a rollout. If the cloud node were saturated the rollout would Pending, but it is not. Cordon already excludes wsl2.
- **Rollback:** remove the `nodeSelector` (`kubectl patch` → null, or `kubectl set`/`edit`) → returns to current unconstrained behavior. Because the pin uses a static existing label (`kubernetes.io/hostname`), it remains valid unless the node is recreated with a different name (in which case re-pin).
- Pinning is reversible and does not affect `edge-node`, `orchestrator`, Services, Rules, RuleEndpoints, CloudCore, EdgeCore, ECR, IAM, SG, or Terraform.

## K. Why this remediation is infrastructure correctness, not a cache optimization

The 10E optimization (short-TTL cache) is complete, tested, and its image (`:10e-4`, digest `sha256:a3aa6fbc…`) is ready. It is **not** the cause of the failure — the same exact image+`SCHEDULER_METRICS_TTL_SEC=1.0` rollout would have failed with `:latest` too, purely because the rollout landed on a disjoint-network edge node. The blocker is **node placement / two disjoint pod networks** (an infrastructure topology property), independent of any scheduler code or cache setting. Therefore the required change is a **placement pin** (Deployment manifest change), not a code/cache/optimization change. This is infrastructure correctness and must be evaluated/handled as such (and per the prior gates, it is out of the "image + env only" scope unless explicitly approved).

## L. Confirmation — NO production changes made

This investigation was **strictly read-only**. I did **not** modify any Deployment, Service, Rule, RuleEndpoint, CloudCore, EdgeCore, Terraform, IAM, Security Group, ECR, node taint, node label, or any scheduler/cloud-node/orchestrator source. I did **not** run `kubectl patch`, `kubectl apply`, `kubectl set image`, `kubectl delete`/`drain`, or `uncordon`. No cordon was undone; wsl2 remains `Ready,SchedulingDisabled`. All commands were `kubectl get`/`describe`, `ip route`/`ping` reads, and the documented report/file reads.

---

10E-5 PLACEMENT INVESTIGATION: COMPLETE
File: docs/phase10/10E/10E-5_placement_investigation.md
Production changes: NONE
Next action: REVIEW PLACEMENT REMEDIATION

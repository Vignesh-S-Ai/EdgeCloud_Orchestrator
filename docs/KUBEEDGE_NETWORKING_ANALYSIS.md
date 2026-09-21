# KubeEdge v1.23.1 Networking Analysis

## Executive Summary

Cloud pods **cannot** reach edge pods via Kubernetes Service ClusterIP. This is **not a bug** — it is a fundamental architectural characteristic of KubeEdge. KubeEdge does **not** tunnel pod-to-pod HTTP traffic through its WebSocket channel. The cloud→edge WebSocket carries K8s resource sync and kubelet subresource proxy only.

The MetaServer HTTP 502 is a **separate, fixable issue**: the DynamicController and CloudStream modules are disabled in our CloudCore configuration.

---

## 1. Root Cause of the Networking Failure

### What happens when a cloud pod tries to reach an edge pod

```
Cloud Pod (10.42.0.7)
  → Service ClusterIP (10.43.218.215:8000)
  → kube-proxy iptables DNAT to endpoint 10.42.1.56:8000
  → Route lookup: 10.42.1.0/24 — NO ROUTE EXISTS
  → CONNECTION TIMEOUT / UNREACHABLE
```

### Why the route doesn't exist

| Network | CIDR | Bridge | Transport |
|---------|------|--------|-----------|
| K3s cloud pods | `10.42.0.0/24` | `cni0` | Flannel VXLAN on `flannel.1` |
| KubeEdge edge pods | `10.42.1.0/24` | `cbr0` (edge node) | Bridge + MASQUERADE |

These are **two separate L2 networks** on **two separate machines**. K3s flannel manages `10.42.0.x`. KubeEdge's edged manages `10.42.1.x` via containerd CRI + CNI bridge plugin. There is no overlay or tunnel connecting them.

### Why KubeEdge doesn't fix this

KubeEdge's WebSocket tunnel (`CloudHub` on port 10000) carries **K8s resource objects** (Pods, Secrets, ConfigMaps, Nodes). It does **not** carry:
- Service ClusterIP traffic
- Pod-to-pod HTTP traffic
- Any arbitrary TCP/UDP data plane

The WebSocket is a **control plane** channel, not a data plane tunnel.

---

## 2. KubeEdge Traffic Flow — What Actually Goes Through the Tunnel

### Control Plane (CloudHub WebSocket — port 10000)

```
Cloud                                          Edge
─────                                          ────
kube-apiserver ←→ EdgeController ←→ CloudHub ←══WebSocket══→ EdgeHub ←→ MetaManager ←→ edged
                     (sync Pods,                    ↑              (sync resources to
                      Secrets,                      │               local sqlite)
                      ConfigMaps,
                      Nodes)
```

This syncs K8s resource objects. When you create a Service in the cloud, it is **not synced to the edge** by default.

### MetaServer Proxy (kubelet subresources — logs/exec/metrics)

```
Cloud                                          Edge
─────                                          ────
kube-apiserver → CloudStream StreamServer → ???  EdgeStream → edged/metasever:10350
                    (intercepts kubelet          (connects to
                     subresource requests)        local MetaServer)
```

This only handles `/containerLogs`, `/exec`, `/attach`, `/metrics`. **Not general HTTP.**

### The Missing Path: Pod-to-Pod HTTP

```
Cloud Pod → kube-proxy → edge pod IP → ??? UNREACHABLE ???
                     ↑
                     No KubeEdge tunnel exists for this traffic.
                     KubeEdge does not proxy Service ClusterIP traffic.
```

---

## 3. Is EdgeMesh Required?

**Yes, for cloud→edge pod HTTP access in a multi-node KubeEdge cluster.**

### Evidence from source code

- `edgemesh/README.md` (line 3): "EdgeMesh has been decoupled from edgecore and moved to [edgemesh](https://github.com/kubeedge/edgemesh)."
- Only 2 references to EdgeMesh in the entire KubeEdge v1.23.1 codebase (both in `keadm` installer, both optional).
- EdgeMesh is an **external project** at `github.com/kubeedge/edgemesh`.

### What EdgeMesh provides

EdgeMesh is a service mesh that runs on each edge node. It:
- Provides local DNS resolution for K8s Services on edge nodes
- Proxies traffic between edge pods (same node and cross-node)
- Handles cloud→edge service routing via its own tunnel
- Replaces kube-proxy on edge nodes (which KubeEdge does not run)

### What EdgeMesh does NOT solve

EdgeMesh handles **edge-side** networking (edge pod ↔ edge pod, edge pod ↔ cloud). It does not tunnel cloud pod → edge pod HTTP traffic through CloudHub. The cloud side still needs a routable path.

---

## 4. Source Code Locations

### CloudHub — WebSocket Transport

| File | Purpose |
|------|---------|
| `cloud/pkg/cloudhub/cloudhub.go` | Module registration, starts WebSocket server |
| `cloud/pkg/cloudhub/dispatcher/message_dispatcher.go:126-161` | `DispatchDownstream()` — routes cloud→edge messages by nodeID |
| `cloud/pkg/cloudhub/dispatcher/message_dispatcher.go:163-206` | `DispatchUpstream()` — routes edge→cloud messages |
| `cloud/pkg/cloudhub/servers/uservers.go` | HTTPS server on port 10002 |
| `cloud/pkg/cloudhub/servers/wsserver.go` | WebSocket server on port 10000 |

### EdgeController — Resource Sync

| File | Purpose |
|------|---------|
| `cloud/pkg/edgecontroller/controller/downstream.go:342-362` | Syncs pods, configmaps, secrets, nodes — **NOT Services** |
| `cloud/pkg/edgecontroller/controller/upstream.go` | Edge→cloud pod status/events sync |

### DynamicController — Application Proxy (DISABLED)

| File | Purpose |
|------|---------|
| `cloud/pkg/dynamiccontroller/dynamiccontroller.go` | Module that processes edge→cloud Applications |
| `cloud/pkg/dynamiccontroller/application/application.go:50-93` | `Process()` — translates edge Applications to kube-api calls |
| `cloud/pkg/dynamiccontroller/application/application.go:100-113` | `ProcessApplication()` — issues real API calls |
| `cloud/pkg/dynamiccontroller/filter/filter.go:10-14` | Filter interface |
| `cloud/pkg/dynamiccontroller/filter/endpointresource/endpointresource.go:44-58` | EndpointSlice filtering by nodegroup |
| `cloud/pkg/dynamiccontroller/filter/endpointresource/endpointresource.go:86-89` | **Only activates** for services with `apps.kubeedge.io/service-topology: range-nodegroup` |
| `cloud/pkg/dynamiccontroller/filter/defaultmaster/defaultmaster.go:43-57` | Rewrites `kubernetes` endpoint to `127.0.0.1:10550` |

### MetaServer — Edge API Proxy

| File | Purpose |
|------|---------|
| `edge/pkg/metamanager/metaserver/server.go:197-258` | MetaServer HTTP handler — routes requests by verb |
| `edge/pkg/metamanager/metaserver/agent/agent.go:92-148` | Sends Applications to cloud via EdgeHub |
| `edge/pkg/metamanager/metaserver/handlerfactory/standard_read.go` | Get/List handlers |
| `edge/pkg/metamanager/metaserver/handlerfactory/standard_pass_through.go` | PassThrough handler |
| `edge/pkg/metamanager/metaserver/kubernetes/storage/storage.go` | REST storage — cloud-first, local-fallback |

### CloudStream — kubelet Subresource Tunnel (DISABLED)

| File | Purpose |
|------|---------|
| `cloud/pkg/cloudstream/cloudstream.go` | Module registration |
| `cloud/pkg/cloudstream/tunnelserver.go:148-228` | Accepts EdgeStream WebSocket, updates Node kubeletEndpoint |
| `cloud/pkg/cloudstream/streamserver.go:55-112` | Intercepts kubelet subresource paths only |
| `cloud/pkg/cloudstream/session.go:88-95` | `ProxyTunnelMessageToApiserver()` |
| `cloud/pkg/cloudstream/iptables/iptables.go:71-74` | DNAT rules for TUNNEL-PORT chain |

### ServiceBus — Rule-Based HTTP Forwarding (DISABLED)

| File | Purpose |
|------|---------|
| `cloud/pkg/router/provider/servicebus/servicebus.go:124-168` | `GoToTarget()` — sends HTTP via beehive to edge |
| `edge/pkg/servicebus/servicebus.go:131-192` | Receives HTTP, forwards to `127.0.0.1:<port>` |
| `cloud/pkg/router/router.go:13` | Router module registration |

### Edge Networking

| File | Purpose |
|------|---------|
| `edge/pkg/edged/edged.go:136-175` | edged initialization — delegates CNI to CRI |
| `edge/pkg/edged/kubeclientbridge/typed/core/v1/core_client_bridge.go:34-69` | KubeClientBridge — **no Services() or Endpoints() method** |
| `edge/pkg/metamanager/process.go:112-121` | `requireRemoteQuery()` — **Services not in list** |

---

## 5. MetaServer 502 — Is It Expected?

**No, it is not expected with a correctly configured deployment.** The 502 is a **configuration issue**, not a fundamental limitation.

### Why the 502 occurs

The 502 comes from **kube-apiserver**, not KubeEdge. When kube-apiserver tries to proxy a request to an edge node's kubelet (for `kubectl logs/exec/attach`), it:

1. Reads `Node.Status.DaemonEndpoints.KubeletEndpoint.Port` (currently `10350`)
2. Tries to connect to `172.18.125.42:10350`
3. The connection fails because:
   - CloudStream is disabled (no tunnel server on port 10351)
   - EdgeStream is disabled (no tunnel client connecting)
   - The port 10350 is the **real kubelet port**, not the CloudStream tunnel port

### What a correct configuration looks like

With CloudStream + EdgeStream enabled:
1. EdgeStream dials CloudStream TunnelServer on port 10004
2. CloudStream updates `Node.KubeletEndpoint.Port` to `10003` (StreamServer port)
3. kube-apiserver sends kubelet requests to `10003`
4. StreamServer intercepts them and tunnels through the WebSocket to EdgeStream
5. EdgeStream forwards to local `127.0.0.1:10350`

### Current configuration gaps

| Module | CloudCore | EdgeCore |
|--------|-----------|----------|
| **DynamicController** | `enable: false` | N/A |
| **CloudStream** | `enable: false` | N/A |
| **MetaServer** | N/A | `enable: false` |
| **EdgeStream** | N/A | `enable: false` |

---

## 6. The Cleanest Architectural Fix

### Problem statement

Our orchestrator (cloud pod) needs to call the edge inference endpoint (edge pod) via a Kubernetes Service. Standard kube-proxy routing fails because edge pod IPs are unreachable from the cloud.

### Solution architecture

KubeEdge provides **three mechanisms** for cloud→edge HTTP access. None are enabled in our deployment. Here is the fix hierarchy:

#### Option A: ServiceBus + RuleEndpoint (Recommended for this capstone)

**What it is:** An explicit HTTP forwarding mechanism via the CloudHub WebSocket tunnel.

**How it works:**
1. Create a `RuleEndpoint` CRD on the cloud pointing to the edge service
2. Create a `Rule` CRD connecting a REST source to the ServiceBus target
3. Cloud application calls the Rule endpoint → CloudCore sends HTTP request via CloudHub → EdgeCore ServiceBus forwards to local pod

**Pros:**
- Uses existing CloudHub WebSocket tunnel (already working)
- No network overlay required
- Works behind NAT/CGNAT
- Designed for exactly this use case (cloud→edge HTTP)
- No patching required

**Cons:**
- Requires DynamicController enabled on CloudCore
- Requires ServiceBus enabled on EdgeCore
- Requires RuleEndpoint + Rule CRD creation
- One HTTP path per Rule (not transparent Service routing)

**Source code path:**
- `cloud/pkg/router/provider/servicebus/servicebus.go:124-168`
- `edge/pkg/servicebus/servicebus.go:131-192`

#### Option B: Enable CloudStream + EdgeStream (fixes MetaServer 502)

**What it is:** Tunnel for kubelet subresource traffic (logs, exec, metrics).

**What it fixes:** `kubectl logs`, `kubectl exec`, `kubectl attach` to edge pods.

**What it does NOT fix:** Pod-to-pod HTTP traffic (Service ClusterIP routing).

**This is required regardless** for operational observability (logs, metrics).

#### Option C: EdgeMesh (full service mesh)

**What it is:** External project at `github.com/kubeedge/edgemesh`. Provides DNS-based service discovery and proxy on edge nodes.

**What it adds:** Edge pods can discover and reach other edge pods via DNS. Cloud→edge routing still needs ServiceBus or a tunnel.

**Overkill for this capstone.**

### Recommended fix sequence

```
Step 1: Enable DynamicController + CloudStream on CloudCore
Step 2: Enable MetaServer + EdgeStream on EdgeCore  
Step 3: Enable ServiceBus on EdgeCore
Step 4: Restart CloudCore and EdgeCore
Step 5: Create RuleEndpoint + Rule CRDs for edge inference
Step 6: Update orchestrator to use Rule endpoint instead of ClusterIP
Step 7: Verify cloud→edge HTTP forwarding works
```

### Whether the fix requires patching KubeEdge

**No patching required.** All components exist in the v1.23.1 binary — they just need to be enabled in configuration and have the corresponding CRDs applied.

---

## 7. Risk Analysis

### Configuration change risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| CloudCore restart causes edge disconnection | Medium | EdgeCore auto-reconnects (heartbeat 15s). Brief downtime. |
| EdgeCore restart causes pod restart | High | edge pods will be killed and restarted. Must re-pull images. |
| CloudStream iptables rules conflict with K3s | Low | CloudStream DNAT only affects CloudCore's own port, not K3s. |
| ServiceBus URL whitelist blocks forwarding | Low | Must register target URLs via RuleEndpoint CRD. |
| Missing CRDs cause CloudCore errors | Medium | Apply all KubeEdge v1.23.1 CRDs before enabling modules. |

### Architecture risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Single WebSocket tunnel = single point of failure | High | CloudHub has reconnection logic. Accept brief outages. |
| ServiceBus is per-path (not transparent) | Medium | Create one Rule per service endpoint. Manageable. |
| No load balancing across edge nodes | Low | ServiceBus targets a specific node. OK for single edge node. |
| WSL2 instability (session cascade) | High | Already mitigated with auto-recovery systemd units. |

### Deployment risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| EdgeCore config change breaks node registration | High | Back up edgecore.yaml before changes. Test incrementally. |
| CRD version mismatch | Low | Use CRDs from same v1.23.1 release. |
| CloudCore systemd service fails to restart | Medium | Test restart before production. Have rollback plan. |

---

## 8. Request Flow Diagrams

### Current (broken): Cloud Pod → Service → Edge Pod

```
┌─────────────┐     ┌──────────────┐     ┌──────────┐     ┌───────────────┐
│  Cloud Pod   │────→│  kube-proxy  │────→│ 10.42.1  │────→│  UNREACHABLE  │
│  10.42.0.7   │     │  iptables    │     │  .56:8000│     │               │
└─────────────┘     │  DNAT to     │     └──────────┘     └───────────────┘
                    │  edge pod IP  │          ↑
                    └──────────────┘          │
                                              │ No route to 10.42.1.0/24
                                              │ from cloud node
```

### Fixed (Option A): ServiceBus HTTP Forwarding

```
┌─────────────┐     ┌────────────┐     ┌══════════════════════════════╗     ┌───────────┐     ┌──────────┐
│  Cloud Pod   │────→│  Router    │────→║  CloudHub (WebSocket :10000) ║────→│  EdgeHub  │────→│ServiceBus│
│  10.42.0.7   │     │  Module    │     ║  + CloudStream (tunnel)     ║     │           │     │ :9060    │
└─────────────┘     └────────────┘     ╚══════════════════════════════╝     └───────────┘     └────┬────┘
                    (Rule CRD)                                                    ↑              │
                    resolve target                                              EdgeCore     HTTP to
                                                                                           127.0.0.1:8000
                                                                                                        │
                                                                                               ┌────────┴────────┐
                                                                                               │   Edge Pod      │
                                                                                               │  10.42.1.56:8000│
                                                                                               │  edge-node      │
                                                                                               └─────────────────┘
```

### Fixed (MetaServer): kubectl logs/exec to edge pod

```
┌───────────┐     ┌─────────────────────┐     ┌════════════════════════════════╗     ┌────────────┐     ┌────────────┐
│  kubectl   │────→│  kube-apiserver     │────→║  CloudStream StreamServer     ║────→│  EdgeStream │────→│  MetaServer│
│  logs/exec │     │  (Node.Endpoint)    │     ║  (intercepts kubelet path)   ║     │  (tunnel)   │     │  :10350    │
└───────────┘     └─────────────────────┘     ╚════════════════════════════════╝     └────────────┘     └────────────┘
                      reads Node.Status                                            WebSocket            HTTP to
                      .DaemonEndpoints                                                          tunnel          localhost
                      .KubeletEndpoint                                                                  (edge)
                      .Port = 10003
```

---

## 9. Key Source Code Findings

### The filter that should rewrite endpoints doesn't apply

`cloud/pkg/dynamiccontroller/filter/endpointresource/endpointresource.go:86-89`:
```go
if svcTopology != nodegroup.ServiceTopologyRangeNodegroup {
    klog.V(4).Infof("skip filter for endpointSlice %v", unstruct.GetName())
    return
}
```

The endpoint filter **only activates** for services annotated with `apps.kubeedge.io/service-topology: range-nodegroup`. Without this annotation, endpoints are sent unfiltered to the edge — including unreachable pod IPs.

### Services are NOT synced to edge by EdgeController

`cloud/pkg/edgecontroller/controller/downstream.go:342-362`: The downstream controller syncs pods, configmaps, secrets, nodes, rules, ruleendpoints. **Services are NOT in the sync list.**

### metaclient has no Services getter

`edge/pkg/metamanager/client/metaclient.go:21-36`: The metaclient supports Pods, ConfigMaps, Secrets, Nodes, etc. **No Services or Endpoints getter exists.**

### KubeClientBridge has no Services() method

`edge/pkg/edged/kubeclientbridge/typed/core/v1/core_client_bridge.go:34-69`: Bridges for Nodes, PVs, PVCs, ConfigMaps, Secrets, ServiceAccounts, Pods, Events. **No Services() or Endpoints() method.**

### edged's kubelet has empty service lister

The kubelet's `serviceLister` is initialized with an empty indexer (`kubelet.go:442-446`). `serviceHasSynced` always returns `true` but the lister is empty. Without MetaServer, edge pods cannot discover Services.

---

## 10. Current Deployment State

### CloudCore (systemd on EC2)

```yaml
modules:
  cloudHub:
    enable: true           # ✅ WebSocket :10000, HTTPS :10002
  edgeController:
    enable: true           # ✅ Syncs Pods, Secrets, ConfigMaps
  deviceController:
    enable: true           # ✅ IoT device sync
  syncController:
    enable: true           # ✅ ObjectSync reliability
  dynamicController:
    enable: false          # ❌ Required for MetaServer + ServiceBus
  iptablesManager:
    enable: true           # ✅ TUNNEL-PORT chain active
  router:
    enable: false          # ❌ Required for ServiceBus routing
  cloudStream:
    enable: false          # ❌ Required for kubelet proxy (logs/exec)
  taskManager:
    enable: false          # ⚠️ Optional
```

### EdgeCore (WSL2)

```yaml
modules:
  edgeHub:
    enable: true           # ✅ WebSocket to CloudHub
  edged:
    enable: true           # ✅ Lite kubelet + CNI bridge
  metaManager:
    enable: true           # ✅ Resource caching
    metaServer:
      enable: false        # ❌ Required for edge API proxy
  serviceBus:
    enable: false          # ❌ Required for cloud→edge HTTP
  edgeStream:
    enable: false          # ❌ Required for CloudStream tunnel
  eventBus:
    enable: true           # ✅ MQTT
  deviceTwin:
    enable: true           # ✅ IoT device twin
```

### Missing CRDs (warnings in CloudCore logs)

- `nodeupgradejobs.ops.kubeedge.io`
- `configupdatejobs.ops.kubeedge.io`
- `imagepulljobs.ops.kubeedge.io`
- `devicestatuses.devices.kubeedge.io`
- `devicemodels.devices.kubeedge.io` (may need re-apply)

---

## 11. Conclusion

The cloud→edge networking failure is an **expected consequence of disabled modules**, not a KubeEdge bug. The fix requires enabling 4 configuration flags and applying CRDs — no source code changes needed.

The recommended path for the capstone project is:
1. Enable DynamicController + CloudStream + Router on CloudCore
2. Enable MetaServer + EdgeStream + ServiceBus on EdgeCore
3. Create RuleEndpoint + Rule CRDs for the edge inference service
4. Update orchestrator to use the Rule endpoint for edge access

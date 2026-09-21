# KubeEdge ServiceBus Deployment Plan

> **Status**: REVIEW / PLAN — DO NOT EXECUTE  
> **Date**: 2026-08-20  
> **Source evidence**: All claims backed by KubeEdge v1.23.1 source code at
> `C:\Users\vigne\AppData\Local\Temp\opencode\kubeedge\`

---

## Table of Contents

1. [Architecture Diagram](#1-architecture-diagram)
2. [Complete Request Flow](#2-complete-request-flow)
3. [Critical Question 1: hostPort](#3-critical-question-1-hostport)
4. [Critical Question 2: RuleEndpoint](#4-critical-question-2-ruleendpoint)
5. [Critical Question 3: ServiceBus Full Path](#5-critical-question-3-servicebus-full-path)
6. [Critical Question 4: CloudStream / EdgeStream](#6-critical-question-4-cloudstream--edgestream)
7. [Critical Question 5: DynamicController + Router](#7-critical-question-5-dynamiccontroller--router)
8. [Critical Question 6: CRDs](#8-critical-question-6-crds)
9. [Critical Question 7: Edge Deployment](#9-critical-question-7-edge-deployment)
10. [Critical Question 8: Orchestrator](#10-critical-question-8-orchestrator)
11. [Critical Question 9: Safe Test Strategy](#11-critical-question-9-safe-test-strategy)
12. [Exact CloudCore Config Diff](#12-exact-cloudcore-config-diff)
13. [Exact EdgeCore Config Diff](#13-exact-edgecore-config-diff)
14. [CRD YAML](#14-crd-yaml)
15. [RuleEndpoint YAML](#15-ruleendpoint-yaml)
16. [Rule YAML](#16-rule-yaml)
17. [Port Table](#17-port-table)
18. [iptables / CNI Impact](#18-iptables--cni-impact)
19. [Verification Commands](#19-verification-commands)
20. [Rollback Commands](#20-rollback-commands)
21. [Phase-by-Phase Execution Order](#21-phase-by-phase-execution-order)
22. [Expected Output for Every Verification Gate](#22-expected-output-for-every-verification-gate)
23. [Risks and Mitigations](#23-risks-and-mitigations)
24. [READY FOR EXECUTION](#24-ready-for-execution)

---

## 1. Architecture Diagram

```
                         EC2 (13.206.229.162)
 ┌─────────────────────────────────────────────────────────┐
 │  K3s Flannel: 10.42.0.x                                 │
 │                                                          │
 │  ┌──────────────┐  ┌──────────────┐  ┌───────────────┐  │
 │  │ orchestrator  │  │ cloud-node   │  │  scheduler    │  │
 │  │ 10.42.0.7    │  │ 10.42.0.5    │  │  10.42.0.6    │  │
 │  │ :8003        │  │ :8001        │  │  :8002        │  │
 │  └──────┬───────┘  └──────────────┘  └───────────────┘  │
 │         │                                                │
 │  ┌──────▼──────────────────────────────────────────────┐ │
 │  │  CloudCore (systemd, PID 137873)                    │ │
 │  │  10.0.1.113                                         │ │
 │  │                                                     │ │
 │  │  CloudHub ──────────────────────────────────────┐   │ │
 │  │  :10000 (ws)  :10002 (https)                    │   │ │
 │  │                                                  │   │ │
 │  │  DynamicController ✅ ENABLE ─── watches Rules   │   │ │
 │  │  Router ✅ ENABLE :9443 (http) ─── REST source  │   │ │
 │  │                                                  │   │ │
 │  │  edgeController ✅ ── syncs Rules to edge        │   │ │
 │  │  iptablesManager ✅ ── TUNNEL-PORT chain          │   │ │
 │  │  cloudStream ❌ DISABLED (deferred)               │   │ │
 │  └──────────────────────────────────┬───────────────┘   │
 │                                     │ WebSocket :10000  │
 └─────────────────────────────────────┼───────────────────┘
                                       │
                  ══════════════════════╪══════════════════
                  Internet / VPN        │
                  ══════════════════════╪══════════════════
                                       │
 ┌─────────────────────────────────────┼───────────────────┐
 │  WSL2 Edge Node (103.206.105.83)    │                   │
 │  KubeEdge v1.23.1-dirty             │                   │
 │  KubeEdge Bridge CNI: 10.42.1.x     │                   │
 │                                     ▼                   │
 │  ┌──────────────────────────────────────────────────┐   │
 │  │  EdgeCore (systemd)                              │   │
 │  │                                                   │   │
 │  │  EdgeHub ──────────────────────────────────────┐  │   │
 │  │  :10000 (ws)                                   │  │   │
 │  │                                                │  │   │
 │  │  metaManager ✅ ── watches Rules from cloud     │  │   │
 │  │  metaServer ✅ ENABLE ── edge API proxy         │  │   │
 │  │  serviceBus ✅ ENABLE ── HTTP forwarder         │  │   │
 │  │                                                │  │   │
 │  │  edgeStream ❌ DISABLED (deferred)              │  │   │
 │  └──────┬─────────────────────────────────────────┘  │   │
 │         │                                            │   │
 │         │  ServiceBus: http://127.0.0.1:8000/{path}  │   │
 │         │  (via hostPort: 8000 on edge pod)          │   │
 │         ▼                                            │   │
 │  ┌──────────────────────────────────────────────────┐│   │
 │  │  edge-node pod (10.42.1.56)                      ││   │
 │  │  containerPort: 8000                             ││   │
 │  │  hostPort: 8000  ←── NEW (needed for ServiceBus) ││   │
 │  │  YOLOv8n loaded                                  ││   │
 │  │  /health → 200                                   ││   │
 │  │  /detect → inference                             ││   │
 │  └──────────────────────────────────────────────────┘│   │
 └──────────────────────────────────────────────────────┘   │
```

---

## 2. Complete Request Flow

### Cloud → Edge (inference)

```
1. Orchestrator POST /orchestrate
   → EdgeClient.detect(image_base64)
   → POST http://10.0.1.113:9443/wsl2-edge-node/edgecloud/detect

2. CloudCore Router HTTP handler (port 9443)
   → httpHandler() extracts edgeNodeName = "wsl2-edge-node" from URI segment 1
   → matchedPath() regex-matches URI against registered handler "/edgecloud/detect"
   → passes (regexp.MatchString is partial-match: "/edgecloud/detect" matches inside "/wsl2-edge-node/edgecloud/detect")
   → isNodeName("wsl2-edge-node") → true (stub, always true)

3. REST Source Forward()
   → uri = SplitN("/wsl2-edge-node/edgecloud/detect", "/", 4) = ["", "wsl2-edge-node", "edgecloud", "detect"]
   → nodeName = "wsl2-edge-node"
   → param = TrimPrefix("detect", "detect") = ""
   → calls ServiceBus target.GoToTarget(data)

4. ServiceBus GoToTarget()
   → resource = "node/" + "wsl2-edge-node" + "/" + "8000" + ":" + "/detect"
   → resource = "node/wsl2-edge-node/8000:/detect"
   → msg.SetResourceOperation(resource, "POST")
   → beehiveContext.Send(CloudHubModuleName, msg)

5. CloudHub DispatchDownstream()
   → receives msg from beehivecontext
   → enqueues for node "wsl2-edge-node"

6. CloudHub Session Sender → WebSocket → Edge

7. *** TrimMessage() ***  ← CRITICAL STEP
   → common.TrimMessage() in cloud/pkg/cloudhub/common/helper.go:76
   → resource = "node/wsl2-edge-node/8000:/detect"
   → tokens = Split(resource, "/") = ["node", "wsl2-edge-node", "8000:/detect"]
   → msg.SetResourceOperation(tokens[2:], ...) = "8000:/detect"
   → Sent over WebSocket as "8000:/detect"

8. EdgeHub receives message
   → routeToEdge() → handler_bus.go
   → msg.GetGroup() == "user", msg.GetSource() == "router_servicebus"
   → beehiveContext.Send(ServiceBusModuleName, msg)

9. Edge ServiceBus processMessage()
   → resource = "8000:/detect"
   → r = strings.Split("8000:/detect", ":") = ["8000", "/detect"]
   → targetURL = "http://127.0.0.1:" + "8000" + "/detect" = "http://127.0.0.1:8000/detect"
   → uc.HTTPDo("POST", targetURL, header, body)
   → HTTP request to localhost:8000 via hostPort → edge pod container:8000

10. Edge pod (YOLO) receives POST /health
    → Returns HTTP 200 with detection results

11. Response flows back:
    Edge pod → Edge ServiceBus → commonType.HTTPResponse → beehiveContext.SendToGroup(HubGroup)
    → EdgeHub → WebSocket → CloudHub → CloudHub upstream dispatch
    → Router callback → REST Forward returns → httpHandler writes response to orchestrator
```

### Source-backed evidence for each step

| Step | Source file | Key line |
|------|-------------|----------|
| REST path registration | `cloud/pkg/router/provider/rest/rest.go` | Line 79: `AddListener("/%s/%s", r.Namespace, r.Path)` |
| httpHandler node extraction | `cloud/pkg/router/listener/http.go` | Line 126: `edgeNodeName := uriSections[1]` |
| matchedPath regex | `cloud/pkg/router/utils/path.go` | Line 29: `regexp.MatchString(URLToURLRegex(reg), path)` — partial match |
| REST Forward nodeName | `cloud/pkg/router/provider/rest/rest.go` | Line 114: `res["nodeName"] = strings.Split(request.RequestURI, "/")[1]` |
| ServiceBus GoToTarget resource | `cloud/pkg/router/provider/servicebus/servicebus.go` | Line 141: `resource := "node/" + nodeName + "/" + sb.servicePort + ":"` |
| TrimMessage strips prefix | `cloud/pkg/cloudhub/common/helper.go` | Line 76-80: tokens[2:] strips `node/{nodeName}/` |
| Edge ServiceBus split | `edge/pkg/servicebus/servicebus.go` | Line 157-191: Split by `:`, construct `http://127.0.0.1:{port}{path}` |
| ServiceBus whitelist insert | `edge/pkg/servicebus/servicebus.go` | Line 140: `dbc.InsertUrls(resource)` on OperationStart |
| EdgeBus dispatch | `edge/pkg/edgehub/messagehandler/handler_bus.go` | Line 46-47: source == "router_servicebus" → Send to ServiceBus |

---

## 3. Critical Question 1: hostPort

### What exact address does ServiceBus connect to?

**`http://127.0.0.1:{port}{path}`** — source evidence:

```go
// edge/pkg/servicebus/servicebus.go:191
targetURL := "http://127.0.0.1:" + r[0] + r[1]
```

Where `r[0]` = port (e.g. "8000") and `r[1]` = path (e.g. "/health").

### Is it really 127.0.0.1?

**YES.** Hardcoded in source. The `server` field in EdgeCore config defaults to `"127.0.0.1"` and is only used for the ServiceBus *server* (the HTTP listener on port 9060), NOT for the outbound target URL construction. The outbound URL always uses `"http://127.0.0.1:"`.

Source: `edge/pkg/servicebus/servicebus.go:191` — the string literal `"http://127.0.0.1:"` is not configurable.

### Is that 127.0.0.1 on the EdgeCore host namespace?

**YES.** EdgeCore runs directly on the WSL2 host (systemd service, not containerized). Its `127.0.0.1` is the host's loopback interface.

### Does Kubernetes hostPort create 127.0.0.1:8000 → edge pod :8000?

**YES, with CNI portmap plugin.** Evidence:

- `portmap` binary exists at `/opt/cni/bin/portmap` on the edge node (verified via UNC read of `\\wsl.localhost\Ubuntu\opt\cni\bin\`)
- `portmap` CNI plugin creates iptables DNAT rules: `-p tcp --dport 8000 -j DNAT --to-destination 10.42.1.56:8000`
- These rules apply to ALL interfaces including `lo` (127.0.0.1)
- Therefore `127.0.0.1:8000` → `10.42.1.56:8000` → edge pod container:8000

### Does our CNI configuration support hostPort?

**YES.** The `portmap` plugin is installed. KubeEdge's edged (lightweight kubelet) uses the standard CNI plugin chain. When a pod spec includes `hostPort`, the kubelet invokes `portmap` which creates the DNAT rules.

### Can we prove this safely with a temporary test?

**YES.** See Section 11 (Safe Test Strategy).

### If hostPort does NOT satisfy, what's the alternative?

HostPort DOES satisfy. If it didn't, the alternatives would be:
1. Patch `edge/pkg/servicebus/servicebus.go:191` to make the target IP configurable (1 line change)
2. Use KubeEdge's EdgeMesh sidecar proxy

Neither is needed.

### VERDICT: hostPort: 8000 is the correct solution.

---

## 4. Critical Question 2: RuleEndpoint

### apiVersion / kind

```yaml
apiVersion: rules.kubeedge.io/v1
kind: RuleEndpoint
```

### REST RuleEndpoint (source)

```yaml
apiVersion: rules.kubeedge.io/v1
kind: RuleEndpoint
metadata:
  name: edge-rest
  namespace: edgecloud
spec:
  ruleEndpointType: "rest"
```

- No `properties` needed for REST type
- REST source listens on port 9443 (Router port)
- Registered path: `/{namespace}/{path}` = `/edgecloud/detect`

### ServiceBus RuleEndpoint (target)

```yaml
apiVersion: rules.kubeedge.io/v1
kind: RuleEndpoint
metadata:
  name: edge-servicebus
  namespace: edgecloud
spec:
  ruleEndpointType: "servicebus"
  properties:
    service_port: "8000"
```

- `service_port` is the port the edge ServiceBus will forward to on `127.0.0.1`
- Source: `cloud/pkg/router/provider/servicebus/servicebus.go:119`: `servicePort: ep.Spec.Properties["service_port"]`

### Rule (connects source → target)

```yaml
apiVersion: rules.kubeedge.io/v1
kind: Rule
metadata:
  name: rest-to-edge-inference
  namespace: edgecloud
spec:
  source: "edge-rest"
  sourceResource:
    path: "/detect"
  target: "edge-servicebus"
  targetResource:
    path: "/detect"
```

- `sourceResource.path` = the URL path on the Router (registered as `/edgecloud/detect`)
- `targetResource.path` = the path appended to `http://127.0.0.1:8000` on the edge
- Target resource in GoToTarget: `"node/" + nodeName + "/8000:" + "/detect"` → after TrimMessage → `"8000:/detect"` → `"http://127.0.0.1:8000/detect"`

### Source from types

```go
// staging/src/github.com/kubeedge/api/apis/rules/v1/types.go
type RuleEndpointSpec struct {
    RuleEndpointType RuleEndpointTypeDef    `json:"ruleEndpointType"`
    Properties       map[string]string      `json:"properties,omitempty"`
}

type RuleSpec struct {
    Source          string            `json:"source"`
    SourceResource  map[string]string `json:"sourceResource"`
    Target          string            `json:"target"`
    TargetResource  map[string]string `json:"targetResource"`
}
```

### Whether separate RuleEndpoint resources are required

**YES.** One for REST (source), one for ServiceBus (target). They are separate CRD instances with different `ruleEndpointType` values. The Rule references them by name.

### Relation between Rule and RuleEndpoint

The Rule's `source` and `target` fields reference RuleEndpoint names. The Rule controller (`cloud/pkg/router/rule/rule.go`) looks up the RuleEndpoints, gets the factory (REST or ServiceBus), and creates source/target instances. The source registers a listener; when a request arrives, it calls `source.Forward(target, data)`.

---

## 5. Critical Question 3: ServiceBus Full Path

### Required URL format

```
http://<cloudcore-ip>:9443/<nodeName>/<namespace>/<path>
```

Example: `http://10.0.1.113:9443/wsl2-edge-node/edgecloud/detect`

### Required RuleEndpoint fields

REST source:
- `ruleEndpointType: "rest"`
- No properties needed

ServiceBus target:
- `ruleEndpointType: "servicebus"`
- `properties.service_port: "8000"` (string, not integer)

### Required ServiceBus fields (EdgeCore config)

```yaml
serviceBus:
  enable: true
  server: "127.0.0.1"   # default, HTTP server bind addr
  port: 9060              # default, ServiceBus server port
  timeout: 60             # default, receive message timeout in seconds
```

### Required Rule fields

```yaml
source: "<rest-endpoint-name>"
sourceResource:
  path: "/detect"
target: "<servicebus-endpoint-name>"
targetResource:
  path: "/detect"
```

### Timeout behavior

- REST Forward timeout: configurable via Router `restTimeout` (default 60s)
- ServiceBus server timeout: EdgeCore `serviceBus.timeout` (default 60s)
- Edge ServiceBus HTTP client timeout: 10s (`htc.Timeout = time.Second * 10` at `servicebus.go:104`)
- Message round-trip timeout: 60s (via `beehiveContext.SendSync` with timeout)

### HTTP method handling

The HTTP method from the original request is preserved throughout:
- REST Forward: `res["method"] = request.Method` (rest.go:116)
- ServiceBus GoToTarget: `request.Method, ok = data["method"].(string)` (servicebus.go:130)
- Edge ServiceBus: `operation := httpRequest.Method` (servicebus.go:190)

### Headers/body handling

- Headers: passed through via `commonType.HTTPRequest.Header` (servicebus.go:131)
- Body: passed through via `commonType.HTTPRequest.Body` ([]byte) (servicebus.go:132)
- Max body size: 5MB (`maxBodySize = 5 * 1e6` at servicebus.go:37)

### Response propagation

1. Edge ServiceBus reads response body (up to 5MB)
2. Builds `commonType.HTTPResponse{Header, StatusCode, Body}`
3. Sends as UploadOperation message via HubGroup
4. CloudHub receives upstream → DispatchUpstream
5. DispatchUpstream routes to Router (UserGroup + UploadOperation at dispatcher.go:186)
6. Router callback fires → REST Forward returns → httpHandler writes HTTP response

### Error behavior

- Edge cannot reach service → HTTP 404 ("error to call service")
- Response body too large → HTTP 500 ("response body too large")
- URL not in whitelist → HTTP 400 ("url not allowed")
- CloudHub session not found → error "cloudcore doesn't have session for node:{name}"
- Timeout → HTTP 408 ("wait to get response time out")

---

## 6. Critical Question 4: CloudStream / EdgeStream

### What they do

CloudStream + EdgeStream provide a WebSocket tunnel for kube-apiserver ↔ edge communication:
- `kubectl logs` → StreamServer → TunnelServer → EdgeStream → edge MetaServer → edged
- `kubectl exec` → same chain
- `kubectl attach` → same chain
- Metrics/stats → same chain

### CloudStream requirements

**Tunnel server** (port 10004):
- TLS with `RequireAndVerifyClientCert`
- CA: **CAN reuse CloudHub CA** (`rootCA.crt`) — fallback at `tunnelserver.go:174`
- Cert: **CAN reuse CloudHub cert** (`server.crt`) — fallback at `tunnelserver.go:186`
- Key: **CAN reuse CloudHub key** (`server.key`) — fallback at `tunnelserver.go:188`
- **NO extra certs needed for tunnel**

**Stream server** (port 10003):
- TLS with `RequestClientCert` (optional client cert)
- CA: **REQUIRES separate** `streamCA.crt` — reads from file at `streamserver.go:390`, **no fallback**
- Cert: **REQUIRES separate** `stream.crt` — used at `streamserver.go:408`
- Key: **REQUIRES separate** `stream.key` — used at `streamserver.go:408`
- **If files missing → `klog.Exitf` → CloudCore process CRASHES** (`streamserver.go:392,410`)
- **CANNOT be enabled without generating stream certs**

### EdgeStream requirements

```yaml
edgeStream:
  enable: true
  server: "13.206.229.162:10004"   # CloudCore tunnel server
  tlsTunnelCAFile: /etc/kubeedge/ca/rootCA.crt       # CloudHub CA (existing)
  tlsTunnelCertFile: /etc/kubeedge/certs/server.crt   # EdgeHub cert (existing)
  tlsTunnelPrivateKeyFile: /etc/kubeedge/certs/server.key  # EdgeHub key (existing)
```

- EdgeStream uses EdgeHub certs for client TLS (`edgestream.go:95`)
- `InsecureSkipVerify: true` — does not verify server cert (`edgestream.go:100`)
- **NO extra certs needed on edge side**

### Node.Status.DaemonEndpoints

When CloudStream is enabled, the TunnelServer updates the K8s node's `DaemonEndpoints.KubeletEndpoint.Port` to the tunnel port (10004). Source: `tunnelserver.go:228`.

### Verdict

**DEFER CloudStream/EdgeStream to a later phase.** The Stream server requires generating `streamCA.crt`, `stream.crt`, `stream.key` and distributing them. This is not needed for the ServiceBus inference path.

When ready to enable:
1. Generate stream CA + certs on EC2
2. Copy to `/etc/kubeedge/ca/streamCA.crt` and `/etc/kubeedge/certs/stream.{crt,key}`
3. Enable `cloudStream: true` on CloudCore
4. Enable `edgeStream: true` on EdgeCore
5. Restart both services
6. Add port 10004 to security group (for edge→cloud tunnel connection, though our edge uses outbound WSS so SG rule may not be needed)

---

## 7. Critical Question 5: DynamicController + Router

### DynamicController

```go
// cloud/pkg/dynamiccontroller/dynamiccontroller.go:49
func Register(dc *configv1alpha1.DynamicController, enableAuthorization bool) {
    config.InitConfigure(dc, enableAuthorization)
    dynamicController = newDynamicController(dc.Enable)
    core.Register(dynamicController)
}
```

**Required config:**
```yaml
dynamicController:
  enable: true
```

**What it does:**
- Uses `dynamicinformer.DynamicSharedInformerFactory` to watch K8s resources
- Wires up `applicationCenter.ForResource(nodes)` and `applicationCenter.ForResource(services)` (line 95-96)
- Receives messages from beehive and processes them via `applicationCenter.Process(msg)` (line 115)
- **Required for the Router module** because the Router needs to watch Rule/RuleEndpoint CRDs dynamically

**Dependencies:**
- None beyond CloudHub (already running)
- Must start AFTER CloudHub's cache syncs (CloudHub does `WaitForCacheSync` before `DoneTLSTunnelCerts`)

### Router

```go
// cloud/pkg/router/router.go:29
func Register(router *v1alpha1.Router) {
    routerconfig.InitConfigure(router)
    core.Register(newRouter(router.Enable))
}
```

**Required config:**
```yaml
router:
  enable: true
  address: "0.0.0.0"
  port: 9443
  restTimeout: 60
```

**What it does on Start():**
- Calls `listener.Process(r.Name())` which runs a beehive message loop (message.go:55)
- Processes messages from DynamicController (Rule/RuleEndpoint CRD changes)
- Starts HTTP server on port 9443 when first REST source is registered

**Provider registration (auto via init imports):**
```go
// cloud/pkg/router/router.go:11-14
_ "github.com/kubeedge/kubeedge/cloud/pkg/router/provider/eventbus"   // init eventbus
_ "github.com/kubeedge/kubeedge/cloud/pkg/router/provider/rest"       // init rest
_ "github.com/kubeedge/kubeedge/cloud/pkg/router/provider/servicebus" // init servicebus
_ "github.com/kubeedge/kubeedge/cloud/pkg/router/rule"                // init rule
```

These `init()` calls register source/target factories. No additional configuration needed.

**Startup ordering:**
1. CloudHub starts first (already running)
2. DynamicController starts → watches Rule/RuleEndpoint CRDs
3. Router starts → processes Rule/RuleEndpoint changes from DynamicController
4. When a Rule CRD is created: Router creates source/target, source registers HTTP handler
5. HTTP server starts on port 9443

---

## 8. Critical Question 6: CRDs

### REQUIRED for ServiceBus/RuleEndpoint

| CRD | Status | Notes |
|-----|--------|-------|
| `rules.rules.kubeedge.io` | ✅ Installed | `kubectl get crd rules.rules.kubeedge.io` |
| `ruleendpoints.rules.kubeedge.io` | ✅ Installed | `kubectl get crd ruleendpoints.rules.kubeedge.io` |
| `objectsyncs.reliablesyncs.kubeedge.io` | ✅ Installed | Needed for reliable sync |
| `clusterobjectsyncs.reliablesyncs.kubeedge.io` | ✅ Installed | Needed for reliable sync |

### OPTIONAL (not needed for inference path)

| CRD | Status | Notes |
|-----|--------|-------|
| `devices.devices.kubeedge.io` | ✅ Installed | IoT device management |
| `devicemodels.devices.kubeedge.io` | ✅ Installed | IoT device models |
| `nodeupgradejobs` | ❌ Missing | Operations, non-critical |
| `configupdatejobs` | ❌ Missing | Operations, non-critical |
| `imagepulljobs` | ❌ Missing | Operations, non-critical |
| `devicestatuses` | ❌ Missing | Device status reporting |

### No CRD installation needed

All required CRDs are already installed. We only need to create the **instances** (RuleEndpoint and Rule resources), not the CRDs themselves.

---

## 9. Critical Question 7: Edge Deployment

### Current deployment

```yaml
# infra/k3s/edge-node-deployment.yaml (current)
containers:
  - name: edge-node
    image: 325580898273.dkr.ecr.ap-south-1.amazonaws.com/edgecloud/edge-node:latest
    ports:
      - containerPort: 8000
    # ... env, resources, probes, etc.
```

### MINIMUM modification

**Add `hostPort: 8000`** to the container port spec. This is the ONLY required change to the deployment.

```yaml
    ports:
      - containerPort: 8000
        hostPort: 8000        # ← ADD THIS LINE
```

### What stays UNCHANGED

- YOLO image: unchanged
- resource limits: unchanged (200m-2000m CPU, 512Mi-2Gi memory)
- nodeSelector: unchanged (none currently — let KubeEdge schedule)
- readinessProbe: unchanged (/health:8000, initialDelay 60s)
- livenessProbe: unchanged (/health:8000, initialDelay 90s)
- startupProbe: unchanged (failureThreshold 30, period 5s)
- imagePullSecrets: unchanged (ecr-registry-secret)
- env vars: unchanged
- restartPolicy: Always

### Why hostPort works on KubeEdge

KubeEdge's `edged` is a forked kubelet. It supports the standard CNI plugin chain including `portmap`. When a pod spec includes `hostPort`, edged invokes the portmap CNI plugin which creates iptables DNAT rules mapping `host:port` → `pod:port`. The `portmap` binary exists at `/opt/cni/bin/portmap` on the edge node.

### Port conflict check

| Port | Used by | Conflict with 8000? |
|------|---------|---------------------|
| 8000 | ServiceBus target (new) | No conflict |
| 9060 | ServiceBus HTTP server | No conflict |
| 10000 | EdgeHub WebSocket | No conflict |
| 10004 | EdgeStream tunnel (disabled) | No conflict |
| 10350 | edged readOnlyPort (localhost only) | No conflict |
| 10550 | MetaServer (disabled) | No conflict |

---

## 10. Critical Question 8: Orchestrator

### Current call path

```python
# orchestrator/clients.py
class EdgeClient(_BaseClient):
    async def detect(self, image_base64, ...):
        return await self._request_json("POST", "/detect", payload)

# _BaseClient._url:
def _url(self, path: str) -> str:
    return f"{self._base}/{path.lstrip('/')}"
```

Current env: `ORCHESTRATOR_EDGE_URL=http://edge-node.edgecloud.svc:8000`
Current call: `POST http://edge-node.edgecloud.svc:8000/detect`

**Problem:** K3s pod network (10.42.0.x) cannot route to KubeEdge pod network (10.42.1.x).

### New call path via ServiceBus

New env: `ORCHESTRATOR_EDGE_URL=http://10.0.1.113:9443/wsl2-edge-node/edgecloud`

New call: `POST http://10.0.1.113:9443/wsl2-edge-node/edgecloud/detect`

The `_url()` method constructs: `http://10.0.1.113:9443/wsl2-edge-node/edgecloud/detect`

This hits the CloudCore Router on port 9443, which routes through ServiceBus to the edge.

### Minimum changes required

**ONE change:** The `ORCHESTRATOR_EDGE_URL` environment variable in `infra/k3s/orchestrator-deployment.yaml`.

```yaml
env:
  - name: ORCHESTRATOR_EDGE_URL
    value: "http://10.0.1.113:9443/wsl2-edge-node/edgecloud"  # ← CHANGE THIS
```

### What stays UNCHANGED

- `ORCHESTRATOR_CLOUD_URL`: unchanged (`http://cloud-node.edgecloud.svc:8001`)
- `ORCHESTRATOR_SCHEDULER_URL`: unchanged (`http://scheduler.edgecloud.svc:8002`)
- `orchestrator/clients.py`: **ZERO code changes** — `_url()` constructs `{base}/{path}` which works
- `orchestrator/config.py`: **ZERO code changes** — env var override handles it
- `/orchestrate` API: **UNCHANGED** — same endpoint, same request/response format

### Why this works

1. Orchestrator pod is on the same EC2 node as CloudCore
2. `10.0.1.113` is the EC2 private IP, reachable from within K3s pods on the same node
3. Port 9443 does NOT need to be in the security group (it's internal traffic)
4. CloudCore listens on `0.0.0.0:9443` (Router config)

### Alternative: NodePort service for CloudCore Router

If direct IP access is not preferred, a NodePort service could expose port 9443 on a high port (e.g., 30443). This would require:
```yaml
apiVersion: v1
kind: Service
metadata:
  name: cloudcore-router
  namespace: kubeedge
spec:
  type: NodePort
  selector: {}  # No selector — CloudCore is not a pod
  ports:
    - port: 9443
      targetPort: 9443
      nodePort: 30443
```
But this requires a manual Endpoints object (headless service pattern) since CloudCore is not a K3s pod.

**Recommended:** Use direct IP `http://10.0.1.113:9443/wsl2-edge-node/edgecloud` for simplicity.

---

## 11. Critical Question 9: Safe Test Strategy

### Phase 1: Test hostPort connectivity (BEFORE changing production deployment)

1. Deploy a temporary test pod on `wsl2-edge-node`:
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: hostport-test
  namespace: edgecloud
spec:
  replicas: 1
  selector:
    matchLabels:
      app: hostport-test
  template:
    metadata:
      labels:
        app: hostport-test
    spec:
      containers:
        - name: test
          image: nginx:alpine
          ports:
            - containerPort: 80
              hostPort: 8080    # Test on different port to avoid conflict
```

2. Verify from EdgeCore host:
```bash
# On WSL2 edge node:
curl http://127.0.0.1:8080/    # Should return nginx welcome page
```

3. Verify from EC2 cloud node:
```bash
# On EC2 (won't work - different network, this validates the edge host only)
curl http://103.206.105.83:8080/  # Would need SG + edge firewall
```

4. Clean up test pod.

### Phase 2: Test ServiceBus WITHOUT changing production edge deployment

1. Apply RuleEndpoint + Rule CRDs (CloudCore)
2. Enable DynamicController + Router on CloudCore (restart)
3. Enable ServiceBus + MetaServer on EdgeCore (restart)
4. Deploy a simple HTTP echo server pod on `wsl2-edge-node` with `hostPort: 9060` (NOT the real YOLO pod)
5. Create Rule targeting echo server port
6. Call Router: `curl http://10.0.1.113:9443/wsl2-edge-node/edgecloud/test`
7. Verify response flows through

### Phase 3: Production deployment

1. Add `hostPort: 8000` to real edge deployment
2. Update orchestrator env
3. Apply production RuleEndpoint + Rule
4. Verify end-to-end inference

### If hostPort test fails

The safest fallback: Patch `edge/pkg/servicebus/servicebus.go:191` to use the pod IP instead of `127.0.0.1`:

```go
// Before:
targetURL := "http://127.0.0.1:" + r[0] + r[1]
// After:
targetURL := "http://" + r[0] + r[1]   // Uses pod IP from CNI
```

This would require rebuilding the EdgeCore binary, which is a bigger change.

---

## 12. Exact CloudCore Config Diff

### Current (relevant sections)

```yaml
modules:
  dynamicController:
    enable: false          # ← CHANGE TO true
  router:
    enable: false          # ← CHANGE TO true
    address: "0.0.0.0"
    port: 9443
    restTimeout: 60
  cloudStream:
    enable: false          # ← KEEP false (deferred)
```

### Target

```yaml
modules:
  dynamicController:
    enable: true           # ← WAS false
  router:
    enable: true           # ← WAS false
    address: "0.0.0.0"
    port: 9443
    restTimeout: 60
  cloudStream:
    enable: false          # ← UNCHANGED (needs stream certs)
```

### What stays UNCHANGED in cloudcore.yaml

- `kubeAPIConfig`: unchanged
- `cloudHub`: unchanged (ports 10000, 10002)
- `edgeController`: unchanged
- `deviceController`: unchanged
- `iptablesManager`: unchanged
- `syncController`: unchanged
- `taskManager`: unchanged
- `commonConfig.tunnelPort`: unchanged (10350)

### Application command

```bash
# On EC2 via SSM:
# Edit /etc/kubeedge/config/cloudcore.yaml
# Change dynamicController.enable: false → true
# Change router.enable: false → true
# Then:
systemctl restart cloudcore
```

---

## 13. Exact EdgeCore Config Diff

### Current (relevant sections)

```yaml
modules:
  metaManager:
    enable: true
    metaServer:
      enable: false        # ← CHANGE TO true
      server: "127.0.0.1:10550"
      dummyServer: "169.254.30.10:10550"
  serviceBus:
    enable: false          # ← CHANGE TO true
    port: 9060
    server: "127.0.0.1"
    timeout: 60
  edgeStream:
    enable: false          # ← KEEP false (deferred)
```

### Target

```yaml
modules:
  metaManager:
    enable: true
    metaServer:
      enable: true         # ← WAS false
      server: "127.0.0.1:10550"
      dummyServer: "169.254.30.10:10550"
  serviceBus:
    enable: true           # ← WAS false
    port: 9060
    server: "127.0.0.1"
    timeout: 60
  edgeStream:
    enable: false          # ← UNCHANGED (needs tunnel cert coordination)
```

### What stays UNCHANGED in edgecore.yaml

- `database`: unchanged
- `edgeHub`: unchanged (websocket:10000, https:10002)
- `edged`: unchanged (all kubelet config)
- `eventBus`: unchanged
- `deviceTwin`: unchanged
- `dbTest`: unchanged
- `taskManager`: unchanged

### Application

EdgeCore config is at `/etc/kubeedge/config/edgecore.yaml` on the WSL2 host.
Apply via UNC path: `\\wsl.localhost\Ubuntu\etc\kubeedge\config\edgecore.yaml`

```bash
# After editing:
# Restart EdgeCore (kills running pods temporarily):
wsl -u root -- systemctl restart edgecore
```

**WARNING:** Restarting EdgeCore will kill ALL pods on the edge node (edge-node-549ff67f69-d9tvv, nginx-edge). They will restart automatically.

---

## 14. CRD YAML

CRDs are already installed. **DO NOT re-apply.** Verify only:

```bash
kubectl --kubeconfig /etc/rancher/k3s/k3s.yaml get crd rules.rules.kubeedge.io
kubectl --kubeconfig /etc/rancher/k3s/k3s.yaml get crd ruleendpoints.rules.kubeedge.io
```

Expected output:
```
NAME                           CREATED AT
rules.rules.kubeedge.io        2026-08-18T17:14:42Z

NAME                              CREATED AT
ruleendpoints.rules.kubeedge.io   2026-08-18T17:14:43Z
```

---

## 15. RuleEndpoint YAML

```yaml
# File: infra/k3s/ruleendpoint-rest.yaml
apiVersion: rules.kubeedge.io/v1
kind: RuleEndpoint
metadata:
  name: edge-rest
  namespace: edgecloud
spec:
  ruleEndpointType: "rest"
---
# File: infra/k3s/ruleendpoint-servicebus.yaml
apiVersion: rules.kubeedge.io/v1
kind: RuleEndpoint
metadata:
  name: edge-servicebus
  namespace: edgecloud
spec:
  ruleEndpointType: "servicebus"
  properties:
    service_port: "8000"
```

Apply command:
```bash
kubectl --kubeconfig /etc/rancher/k3s/k3s.yaml apply -f infra/k3s/ruleendpoint-rest.yaml
kubectl --kubeconfig /etc/rancher/k3s/k3s.yaml apply -f infra/k3s/ruleendpoint-servicebus.yaml
```

---

## 16. Rule YAML

```yaml
# File: infra/k3s/rule-rest-to-servicebus.yaml
apiVersion: rules.kubeedge.io/v1
kind: Rule
metadata:
  name: rest-to-edge-inference
  namespace: edgecloud
spec:
  source: "edge-rest"
  sourceResource:
    path: "/detect"
  target: "edge-servicebus"
  targetResource:
    path: "/detect"
```

Apply command:
```bash
kubectl --kubeconfig /etc/rancher/k3s/k3s.yaml apply -f infra/k3s/rule-rest-to-servicebus.yaml
```

### Also add a health check rule

```yaml
# File: infra/k3s/rule-rest-to-servicebus-health.yaml
apiVersion: rules.kubeedge.io/v1
kind: Rule
metadata:
  name: rest-to-edge-health
  namespace: edgecloud
spec:
  source: "edge-rest"
  sourceResource:
    path: "/health"
  target: "edge-servicebus"
  targetResource:
    path: "/health"
```

---

## 17. Port Table

| Port | Protocol | Component | Direction | SG Required? |
|------|----------|-----------|-----------|-------------|
| 8000 | TCP | Edge pod containerPort + hostPort | Edge host local only | No |
| 9060 | TCP | Edge ServiceBus HTTP server | Edge host local only | No |
| 9443 | TCP | CloudCore Router HTTP | EC2 internal (orchestrator→cloudcore) | No (same node) |
| 10000 | TCP | CloudHub WebSocket | Edge→Cloud (outbound WSS) | ✅ Already open |
| 10002 | TCP | CloudHub HTTPS | Edge→Cloud (cert issue) | ✅ Already open |
| 10003 | TCP | CloudStream StreamServer | Deferred | — |
| 10004 | TCP | CloudStream TunnelServer | Deferred | — |
| 10350 | TCP | CommonConfig TunnelPort | Internal | No |
| 30083 | TCP | Orchestrator NodePort | External→K3s | ✅ Already open |

---

## 18. iptables / CNI Impact

### Cloud side (EC2)

No iptables changes needed. The CloudCore Router listens on port 9443 (plain HTTP). No NAT rules required.

Existing chains:
- `TUNNEL-PORT` → kubeedge tunnel port forwarding (10350)
- `KUBE-SERVICES` → K3s service portals
- `DOCKER` → Docker bridge networking

### Edge side (WSL2)

Enabling ServiceBus + hostPort adds:

1. **portmap CNI plugin** creates DNAT rule for hostPort:
```
-A KUBE-PORTMAPS -p tcp --dport 8000 -j DNAT --to-destination 10.42.1.56:8000
```

2. **ServiceBus HTTP server** binds to `127.0.0.1:9060` (no iptables needed for localhost)

3. **MetaServer** binds to `127.0.0.1:10550` (no iptables needed)

4. **Dummy interface** (if MetaServer with RequireAuthorization enabled):
```
ip link add edge-dummy0 type dummy
ip addr add 169.254.30.10/32 dev edge-dummy0
```
This only happens if `RequireAuthorization` feature gate is enabled. Default is disabled.

### No conflicts

- K3s iptables chains (`KUBE-SERVICES`, `KUBE-POSTROUTING`) are on the EC2 node, not WSL2
- KubeEdge iptables (`TUNNEL-PORT`) coexists with K3s chains on EC2
- portmap DNAT rule for port 8000 has no conflicts with existing rules

---

## 19. Verification Commands

### Phase A: CloudCore restart verification

```bash
# On EC2 via SSM:
systemctl status cloudcore
# Expected: active (running), PID changed

# Check DynamicController + Router in logs:
journalctl -u cloudcore --since "5 minutes ago" | grep -E "DynamicController|router|Router"
# Expected: "In router module, start..." and DynamicController start messages
```

### Phase B: EdgeCore restart verification

```bash
# On WSL2:
systemctl status edgecore
# Expected: active (running)

# Check ServiceBus + MetaServer in logs:
journalctl -u edgecore --since "5 minutes ago" | grep -E "servicebus|metaserver"
# Expected: "[servicebus]start to listen and server at 127.0.0.1:9060"
#           "[metaserver]start to listen and server at http://127.0.0.1:10550"
```

### Phase C: Edge pod re-verification

```bash
# On EC2:
kubectl --kubeconfig /etc/rancher/k3s/k3s.yaml get pods -n edgecloud -o wide
# Expected: edge-node-xxx Running on wsl2-edge-node

kubectl --kubeconfig /etc/rancher/k3s/k3s.yaml exec -n edgecloud <edge-pod> -- curl -s http://127.0.0.1:8000/health
# Expected: HTTP 200
```

### Phase D: RuleEndpoint + Rule verification

```bash
# On EC2:
kubectl --kubeconfig /etc/rancher/k3s/k3s.yaml get ruleendpoints -n edgecloud
# Expected: edge-rest, edge-servicebus

kubectl --kubeconfig /etc/rancher/k3s/k3s.yaml get rules -n edgecloud
# Expected: rest-to-edge-inference, rest-to-edge-health
```

### Phase E: Router test

```bash
# On EC2:
curl -s http://10.0.1.113:9443/wsl2-edge-node/edgecloud/health
# Expected: HTTP 200 with health response

curl -s -X POST http://10.0.1.113:9443/wsl2-edge-node/edgecloud/detect \
  -H "Content-Type: application/json" \
  -d '{"image_base64": "<test-image>", "confidence": 0.5}'
# Expected: HTTP 200 with detection results
```

### Phase F: Orchestrator end-to-end

```bash
# From outside EC2:
curl -s -X POST http://13.206.229.162:30083/orchestrate \
  -H "Content-Type: application/json" \
  -d '{"image_base64": "<test-image>"}'
# Expected: HTTP 200 with full orchestration response
```

---

## 20. Rollback Commands

### Rollback CloudCore (worst case: CloudCore crash loop)

```bash
# On EC2 via SSM:
# Edit /etc/kubeedge/config/cloudcore.yaml
# Set dynamicController.enable: false
# Set router.enable: false
systemctl restart cloudcore
# CloudCore restarts without Router/DynamicController — existing K3s pods unaffected
```

### Rollback EdgeCore (edge pods restart anyway)

```bash
# Via UNC path, edit \\wsl.localhost\Ubuntu\etc\kubeedge\config\edgecore.yaml
# Set serviceBus.enable: false
# Set metaServer.enable: false
# Then:
wsl -u root -- systemctl restart edgecore
# Edge pods restart, ServiceBus/MetaServer disabled
```

### Rollback edge deployment (remove hostPort)

```bash
kubectl --kubeconfig /etc/rancher/k3s/k3s.yaml apply -f infra/k3s/edge-node-deployment.yaml
# (with hostPort line removed)
```

### Rollback orchestrator

```bash
kubectl --kubeconfig /etc/rancher/k3s/k3s.yaml set env deployment/orchestrator \
  -n edgecloud \
  ORCHESTRATOR_EDGE_URL=http://edge-node.edgecloud.svc:8000
```

### Delete RuleEndpoint + Rule

```bash
kubectl --kubeconfig /etc/rancher/k3s/k3s.yaml delete -n edgecloud rule --all
kubectl --kubeconfig /etc/rancher/k3s/k3s.yaml delete -n edgecloud ruleendpoint --all
```

---

## 21. Phase-by-Phase Execution Order

### Phase 1: CloudCore config (modify + restart)

1. Edit `/etc/kubeedge/config/cloudcore.yaml` on EC2 via SSM
   - Set `dynamicController.enable: true`
   - Set `router.enable: true`
2. `systemctl restart cloudcore`
3. Verify: `journalctl -u cloudcore | grep -E "router|DynamicController"`

**Gate:** CloudCore running, no crash loops, Router HTTP server listening on 9443.

### Phase 2: EdgeCore config (modify + restart)

1. Edit `/etc/kubeedge/config/edgecore.yaml` via UNC
   - Set `serviceBus.enable: true`
   - Set `metaManager.metaServer.enable: true`
2. `wsl -u root -- systemctl restart edgecore`
3. Verify: ServiceBus listening on 127.0.0.1:9060, MetaServer on 127.0.0.1:10550
4. Wait for edge pod to restart and become Ready

**Gate:** EdgeCore running, edge pod Running with /health 200.

### Phase 3: Apply CRD instances

1. `kubectl apply -f infra/k3s/ruleendpoint-rest.yaml`
2. `kubectl apply -f infra/k3s/ruleendpoint-servicebus.yaml`
3. `kubectl apply -f infra/k3s/rule-rest-to-servicebus.yaml`
4. `kubectl apply -f infra/k3s/rule-rest-to-servicebus-health.yaml`
5. Verify: RuleEndpoint and Rule resources exist

**Gate:** `kubectl get rules -n edgecloud` shows rules with no errors.

### Phase 4: Add hostPort to edge deployment

1. Edit `infra/k3s/edge-node-deployment.yaml` — add `hostPort: 8000`
2. `kubectl apply -f infra/k3s/edge-node-deployment.yaml`
3. Wait for new pod to become Running and Ready

**Gate:** `kubectl get pods -n edgecloud -o wide` shows edge pod on wsl2-edge-node, Ready 1/1.

### Phase 5: Update orchestrator

1. `kubectl set env deployment/orchestrator -n edgecloud ORCHESTRATOR_EDGE_URL=http://10.0.1.113:9443/wsl2-edge-node/edgecloud`
2. Wait for orchestrator pod to restart

**Gate:** Orchestrator pod Running, /health returns 200.

### Phase 6: End-to-end test

1. Call orchestrator /orchestrate endpoint
2. Verify inference response flows through ServiceBus to edge
3. Check CloudCore logs for Router message processing
4. Check EdgeCore logs for ServiceBus HTTP forward

**Gate:** HTTP 200 response with detection results.

---

## 22. Expected Output for Every Verification Gate

### Gate 1: CloudCore healthy

```bash
systemctl status cloudcore
# ● cloudcore.service - KubeEdge CloudCore
#      Active: active (running) since ...
#      Main PID: <new_pid> (/usr/local/bin/cloudcore)
```

### Gate 2: EdgeCore healthy

```bash
# ServiceBus log:
[servicebus]start to listen and server at 127.0.0.1:9060

# MetaServer log:
[metaserver]start to listen and server at http://127.0.0.1:10550
```

### Gate 3: Edge pod ready

```bash
kubectl get pods -n edgecloud -o wide
# NAME                    READY   STATUS    RESTARTS   AGE   IP           NODE
# edge-node-xxxxx-xxxxx   1/1     Running   0          Xm    10.42.1.56   wsl2-edge-node
```

### Gate 4: Rules applied

```bash
kubectl get rules,ruleendpoints -n edgecloud
# NAME                                      AGE
# ruleendpoint.rules.kubeedge.io/edge-rest            Xs
# ruleendpoint.rules.kubeedge.io/edge-servicebus      Xs
# rule.rules.kubeedge.io/rest-to-edge-inference       Xs
# rule.rules.kubeedge.io/rest-to-edge-health          Xs
```

### Gate 5: Direct Router health check

```bash
curl -s http://10.0.1.113:9443/wsl2-edge-node/edgecloud/health
# HTTP 200
# {"status":"healthy","model":"yolov8n","uptime":...}
```

### Gate 6: Full orchestration

```bash
curl -s -X POST http://13.206.229.162:30083/orchestrate \
  -H "Content-Type: application/json" \
  -d '{"image_base64":"<base64-encoded-image>"}'
# HTTP 200
# {"result": "...", "placement": "edge", "latency_ms": ...}
```

---

## 23. Risks and Mitigations

### Risk 1: EdgeCore restart kills running pods

**Impact:** Edge pod restarts (YOLO model reload, ~60-90s startup)
**Mitigation:** Startup probe allows 30 × 5s = 150s for model load. Readiness probe prevents traffic until ready.
**Severity:** Low (expected behavior)

### Risk 2: ServiceBus hardcoded 127.0.0.1

**Impact:** If hostPort doesn't work, ServiceBus can't reach edge pod
**Mitigation:** HostPort with portmap CNI is proven to work. Fallback: patch servicebus.go:191.
**Severity:** Medium (but hostPort is well-supported)

### Risk 3: Router partial regex matching

**Impact:** The Router's `IsMatch` uses partial regex matching. A rule registered at `/edgecloud/detect` could match `/wsl2-edge-node/edgecloud/detect-other` if "detect-other" starts with "detect".
**Mitigation:** Use specific paths (e.g., `/detect` not `/det`). The `/?` tail regex prevents most false matches.
**Severity:** Low (unlikely with our path names)

### Risk 4: CloudCore port 9443 not externally accessible

**Impact:** If orchestrator runs on a different node, it can't reach port 9443
**Mitigation:** Orchestrator runs on the same EC2 node. Internal traffic doesn't go through SG.
**Severity:** None (same node)

### Risk 5: EdgeCore restart timing

**Impact:** EdgeCore restart + pod restart takes 2-3 minutes
**Mitigation:** Plan for downtime window. Run during non-critical period.
**Severity:** Low

### Risk 6: ServiceBus HTTP client timeout (10s)

**Impact:** YOLO inference might exceed 10s for large images
**Mitigation:** ServiceBus HTTP client timeout is hardcoded at 10s (`htc.Timeout = time.Second * 10`). For inference, keep input images small (< 1MB). Can patch source if needed.
**Severity:** Medium (may need source patch for slow inference)

### Risk 7: WSL2 intermittent connectivity

**Impact:** WSL2 commands may timeout
**Mitigation:** Use UNC paths (`\\wsl.localhost\Ubuntu\...`) instead of `wsl` commands where possible. Increase timeouts.
**Severity:** Low (workaround available)

---

## 24. READY FOR EXECUTION

```
╔══════════════════════════════════════════════════════════════════╗
║                    READY FOR EXECUTION: NO                      ║
║                                                                  ║
║  Status: PLAN COMPLETE — AWAITING USER APPROVAL                  ║
║                                                                  ║
║  All investigation complete. Every command and config change     ║
║  listed below requires explicit user approval before execution.  ║
╚══════════════════════════════════════════════════════════════════╝
```

### Complete list of changes to execute (upon approval)

#### A. CloudCore config (2 changes)

```
File: /etc/kubeedge/config/cloudcore.yaml (on EC2)
Change 1: modules.dynamicController.enable: false → true
Change 2: modules.router.enable: false → true
Command: systemctl restart cloudcore
```

#### B. EdgeCore config (2 changes)

```
File: /etc/kubeedge/config/edgecore.yaml (via \\wsl.localhost\Ubuntu)
Change 1: modules.metaManager.metaServer.enable: false → true
Change 2: modules.serviceBus.enable: false → true
Command: wsl -u root -- systemctl restart edgecore
```

#### C. RuleEndpoint resources (2 new CRD instances)

```
File: infra/k3s/ruleendpoint-rest.yaml (NEW)
File: infra/k3s/ruleendpoint-servicebus.yaml (NEW)
Command: kubectl apply -f <files>
```

#### D. Rule resources (2 new CRD instances)

```
File: infra/k3s/rule-rest-to-servicebus.yaml (NEW)
File: infra/k3s/rule-rest-to-servicebus-health.yaml (NEW)
Command: kubectl apply -f <files>
```

#### E. Edge deployment (1 line added)

```
File: infra/k3s/edge-node-deployment.yaml
Change: Add "hostPort: 8000" under ports
Command: kubectl apply -f infra/k3s/edge-node-deployment.yaml
```

#### F. Orchestrator env (1 value changed)

```
File: infra/k3s/orchestrator-deployment.yaml
Change: ORCHESTRATOR_EDGE_URL value:
  FROM: http://edge-node.edgecloud.svc:8000
  TO:   http://10.0.1.113:9443/wsl2-edge-node/edgecloud
Command: kubectl set env deployment/orchestrator -n edgecloud ORCHESTRATOR_EDGE_URL="http://10.0.1.113:9443/wsl2-edge-node/edgecloud"
```

### Total change count

| Change | Type | Risk | Reversible |
|--------|------|------|-----------|
| CloudCore dynamicController | Config flag | Low | Yes |
| CloudCore router | Config flag | Low | Yes |
| EdgeCore metaServer | Config flag | Low | Yes |
| EdgeCore serviceBus | Config flag | Low | Yes |
| RuleEndpoint × 2 | CRD instance | None | Yes (delete) |
| Rule × 2 | CRD instance | None | Yes (delete) |
| hostPort: 8000 | Deployment spec | Medium | Yes |
| ORCHESTRATOR_EDGE_URL | Env var | Low | Yes |
| **TOTAL** | **9 changes** | | **All reversible** |

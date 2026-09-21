# Edge EC2 — Phase 6: KubeEdge ServiceBus Cloud-to-Edge Integration (E10/E11) Report

Date: 2026-09-01
Status: **PASS — awaiting approval**
Repo: `C:\Vignpro\EdgeCloud-Orchestrator`
AWS profile: `edgecloud` · Region: `ap-south-1` (SSO) · Account: `325580898273`
Edges: CloudCore `i-07ecfbdd7781c5ef5` (13.206.229.162 / 10.0.1.113) · Edge EC2 `i-0080aa7404208982c` (10.0.1.123)

## A. Objective
Prove the complete **cloud-to-edge application data path** through the KubeEdge **ServiceBus** tunnel (not direct pod-IP/ClusterIP):

```
Orchestrator/Cloud client → CloudCore REST :9443 → Router → REST source
  → ServiceBus target → CloudHub WebSocket :10000 → EdgeHub → EdgeCore ServiceBus
  → 127.0.0.1:8000 → YOLO FastAPI → /health and /detect
```

Scope: verify `health` + `detect` through CloudCore :9443 targeting `edge-ec2-node`, prove the ServiceBus resource transformation with logs, run a negative test and a 10-min stability gate. **No YOLO/orchestrator/scheduler code changes; no KubeEdge source patches; no public 8000/9060; egress-only edge SG preserved.**

## B. Baseline (Gate E10-A) — PASS
- Nodes: `edge-ec2-node` **Ready** (agent,edge, v1.32.10-kubeedge-v1.23.1-dirty, containerd 2.2.5); `ip-10-0-1-113` Ready (control-plane); `wsl2-edge-node` NotReady (legacy, untouched).
- YOLO pod `edge-node-fc54dc46-6xdd6` **1/1 Running** on `edge-ec2-node` (restarts 0).
- CloudCore `active`; listens on **:9443** (REST router), **:10000** (CloudHub WebSocket), **:10002** (edgeHub HTTPs).
- Existing Rules `detect-route`/`health-route` (10d) and RuleEndpoints `rest-source`/`servicebus-target` (10d) present in `edgecloud`.

## C. Existing Rules / RuleEndpoints (Gate E10-B)
All node-agnostic; the **target node is carried in the request URI**, not in these objects.

| Object | Type | Key spec |
|---|---|---|
| `rest-source` | RuleEndpoint `rest` | `properties: {}` |
| `servicebus-target` | RuleEndpoint `servicebus` | `properties.service_port: "8000"` |
| `health-route` | Rule | `source: rest-source`, `sourceResource.path: /health`, `target: servicebus-target`, `targetResource.path: /health` |
| `detect-route` | Rule | `source: rest-source`, `sourceResource.path: /detect`, `target: servicebus-target`, `targetResource.path: /detect` |

## D. Source-level call graph validation (Gate E10-C)
Local KubeEdge source tree is no longer present on either node (edge node has only config/db; no net source). Validation therefore used: (1) the source-cited architecture doc `docs/KUBEEDGE_SERVICEBUS_DEPLOYMENT.md` (line references), and (2) live config/proof:

- **cloudcore.yaml**: `router.enable: true`, `router.port: 9443`, `router.restTimeout: 60`, `dynamicController.enable: true`.
- **edgecore.yaml**: `hostnameOverride: edge-ec2-node`; `serviceBus: enable true, port 9060, server 127.0.0.1`.
- **Route format (source-cited):** `http://<cloudcore>:9443/<nodeName>/<namespace>/<path>` → e.g. `/edge-ec2-node/edgecloud/health`.
  - REST `AddListener("/%s/%s", namespace, path)` → registers `/edgecloud/health`, `/edgecloud/detect` (rest.go:79).
  - httpHandler extracts `edgeNodeName = uriSections[1]` (http.go:126); partial regex match (path.go:29).
  - REST Forward `res["nodeName"] = Split(RequestURI,"/")[1]` (rest.go:114).
  - ServiceBus GoToTarget `resource = "node/" + nodeName + "/" + servicePort + ":"` (servicebus.go:141).
  - CloudHub TrimMessage `tokens[2:]` strips `node/{nodeName}/` (helper.go:76-80) → `8000:/path`.
  - Edge ServiceBus processMessage splits `:` → `"http://127.0.0.1:" + port + path` (servicebus.go:191).
- **9060 note (verified):** for **REST(source)→ServiceBus(target)**, `RegisterListener()` is NOT called on the target → port 9060 does NOT listen on the edge (confirmed `ss -tlnp` shows no 9060). Cloud→edge uses EdgeHub→EdgeCore `processMessage()`. Consistent with the requirement.
- **hostPort proof:** iptables NAT `-A CNI-DN-… --dport 8000 -j DNAT --to-destination 10.244.0.4:8000` → `127.0.0.1:8000` reaches the YOLO container.

## E. Changes made (Gate E10-D) — **ZERO changes required**
Because the node name comes from the request URI and the existing `rest-source`/`servicebus-target`/`health-route`/`detect-route` objects are **already node-agnostic**, the existing objects directly serve `edge-ec2-node`. Per the "smallest reversible change" directive:
- **No Rule/RuleEndpoint created or modified.**
- Pre-change objects exported to `/tmp/p6_saved/` on the cloud node and diff-confirmed against live (`health-route UNCHANGED`, `detect-route UNCHANGED`).
- To target the new edge, the request URI uses `/edge-ec2-node/...` instead of `/wsl2-edge-node/...`. **No production object touched.**

## F. Health request (Gate E10-E) — PASS
`GET http://127.0.0.1:9443/edge-ec2-node/edgecloud/health`
- **HTTP 200**, `Server: uvicorn`, `Content-Type: application/json`, e2e `time_total ≈ 0.007s`.
- Body: `{"status":"degraded","service":"edge-node","version":"0.1.0","model_loaded":true,"camera_open":false,"timestamp":…}`.
- **`Server: uvicorn` + `model_loaded:true` prove the genuine YOLO FastAPI app on the edge answered** (CloudCore would not emit uvicorn headers).
- Sanity: `GET …/does-not-exist-node/edgecloud/health` → **500** `All attempts fail: failed to get node:does-not-exist-node … not found` → router resolves the node.

## G. Health response path (edge evidence)
- EdgeCore journal: `handler.go:63] try to match the message, source: router_servicebus, group: user, resource: 8000:/health` at the test timestamp → **post-TrimMessage resource `8000:/health`**.
- YOLO pod log: `GET /health 200`.

## H. Detect request (Gate E11-A) — PASS
`POST http://127.0.0.1:9443/edge-ec2-node/edgecloud/detect` with a 137 419-byte `bus.jpg` (b64 payload 183 288 B, <1 MB).
- **HTTP 200**, `Server: uvicorn`, e2e ≈ **0.14 s** (wall clock); `time_total 0.139s`.
- Body: `{"source":"yolov8n.pt","frame_width":810,"frame_height":1080,"inference_ms":118.78,"count":4,…
  detections:[{bus class_id 5 conf 0.873}, {person 0.866}, {person 0.853}, {person 0.825}]}`.

## I. Detect response headers (uvicorn proof)
`HTTP/1.1 200 OK`, `Content-Type: application/json`, `Server: uvicorn` → response from the **edge YOLO app**, not CloudCore.

## J. ServiceBus resource evidence (Gate E11-B) — PASS (critical proof)
- EdgeCore (detect): `… source: router_servicebus, group: user, resource: 8000:/detect` — i.e. CloudHub trimmed `node/edge-ec2-node/` from `node/edge-ec2-node/8000:/detect`.
- YOLO pod: `POST /detect 200`.
- CloudCore upstream response leg: `… router:{Source:servicebus Destination: Group:user Operation:upload Resource:node/edge-ec2-node/}` at both health (18:07:04) and detect (18:08:35) timestamps.
- Complete transformation, edge-side URL `http://127.0.0.1:8000/detect` reached; success fully **traversed the KubeEdge ServiceBus path** — no direct pod-IP/ClusterIP, no public 8000.

## K. End-to-end latency summary
| Request | HTTP | e2e (wall) | inference_ms |
|---|---|---|---|
| health | 200 | ~0.007 s | — |
| detect (bus.jpg 810×1080, warm) | 200 | ~0.14 s | ~119 ms |
| detect (server-measured) | 200 | ~0.146 s | ~127 ms |

## L. Negative test (Gate E11-C) — PASS
- `GET …/edgecloud/does-not-exist` → **404** in ~0.005 s, **no `Server` header**, body `Request error` → answered by **CloudCore router** (no registered Rule path → not forwarded). Router-scoped matching confirmed.
- `GET …/edgecloud/health/zzz` → **reached the edge**: edge FastAPI log `GET /health/zzz 404 Not Found`.
- `POST …/edgecloud/detect` (malformed base64) → **reached the edge**: edge FastAPI log `POST /detect 422 Unprocessable Entity`.
- These prove valid requests genuinely reach the **edge app** (edge-app 4xx/5xx + uvicorn header), while unregistered paths are rejected at the router. (Known benign behavior: the edge's non-2xx status is surfaced by the ServiceBus relay as a 500 to the caller, while the edge app's own log records the true 404/422.)

## M. 10-minute stability (Gate E11-D) — PASS (cloud + edge, 20 samples @ 30 s)
- **edgecore**: active, pid 33990 constant, `NRestarts=0`; **containerd**: active, pid 33962 constant, `NRestarts=0`; pod Ready; `sbErr_lastwin=0` every window.
- **cloudcore**: active, pid 503357 constant, `NRestarts=0`; `edgeReady=True` all windows; edge pod `1/1 Running restarts=0`.
- **No WebSocket disconnect loop**: `disconnect` = 0, keepalive/ws-close = 0, no ServiceBus errors.
- **Benign excludes:** CloudCore periodically logs informer "Unhandled Error … resource not found" for **uninstalled optional CRDs** (`devicestatuses.devices.kubeedge.io`, `nodeupgradejobs/configupdatejobs/imageprepulljobs.operations.kubeedge.io`). These are unrelated to ServiceBus routing, do not affect node Ready/webhook/ServiceBus, and are pre-existing (CloudCore informer factory probes optional CRD groups). No action taken.

## N. Security verification
- Requests went **only** to CloudCore :9443 (tunnel path); **no** direct pod-IP/ClusterIP routing used (confirmed by the negative + uvicorn-header evidence).
- Edge SG `sg-074dd39fb8d93006b` remains **egress-only**; **no public 8000/9060 exposure**; no SG changes.
- **No** WSL2 / RDS / Terraform / CloudCore-K3s objects modified; no YOLO/orchestrator/scheduler source changes; no KubeEdge source patches.

## O. Rollback procedure
- No production objects were changed (Rules/RuleEndpoints untouched; pre-change YAML saved at `/tmp/p6_saved/` on cloud node; live diff confirmed unchanged). Rollback = no-op.
- To stop ServiceBus traffic for testing: `kubectl delete rule health-route -n edgecloud` (or by deployment revert) and re-`apply` the saved YAML; no `edge-ec2-node` infra change required.

## P. Known limitations
1. **Edge non-2xx translation:** the edge app's true 404/422 is relayed to the caller as 500 by the ServiceBus (edge processMessage surfaces non-2xx as error). Edge app's own log records the real status. Cosmetic for this phase; would require upstream inspection only if a client needs the original status.
2. **Optional-CRD informer noise** on CloudCore (benign, see M).
3. **No local source tree** on either node (patches/EdgeCore were built earlier); source behavior validated via source-cited doc + live config + empirical resource logs.
4. `wsl2-edge-node` legacy + its old `edge-node-5cc…` and `nginx-edge-769…` pods remain (out of scope; candidate for approved cleanup later).

## Q. PASS / FAIL / Notes
| Gate | Requirement | Result |
|---|---|---|
| E10 | Rule/RuleEndpoint target edge-ec2-node; :9443 accepts; reaches EdgeCore ServiceBus; edge /health 200; no pod-IP | **PASS** (node from URI; existing rules suffice — ZERO changes) |
| E11 | cloud→edge /detect success; real YOLO inference; valid JSON; traverses ServiceBus; no public 8000; 10-min stability | **PASS** |
| — | Negative test reaches edge app (not CloudCore); no disconnect loop; no source patch | **PASS** |

**Bottom line:** The cloud can invoke the real YOLO application on `edge-ec2-node` **exclusively through the KubeEdge ServiceBus tunnel** — `POST/GET CloudCore :9443 → Router → REST → ServiceBus → CloudHub→EdgeHub → EdgeCore ServiceBus → 127.0.0.1:8000 → FastAPI` — with health HTTP 200, detect HTTP 200 + valid detection JSON (bus + 3 persons), the `node/edge-ec2-node/8000:/path → 8000:/path` transformation logged, and a clean 10-minute stability run. No direct pod networking, no public ports, no production object changes.

**STOP — awaiting Phase 6 approval.**

# KubeEdge Rebuild Blueprint

## Architecture

```
Cloud Node (K3s control-plane)
    |
    +-- CloudCore (Helm chart or keadm)
    |       |
    |       +-- CloudHub (:10000 WS, :10002 TLS)
    |       +-- Router
    |       +-- CloudCore REST (:9443, plain HTTP)
    |
    +-- Rules (detect-route, health-route, metrics-route, video-route)
    +-- RuleEndpoints (rest-source, servicebus-target)

Edge Node (standalone, NOT K3s)
    |
    +-- EdgeCore (manual binary or keadm)
    |       |
    |       +-- CloudHub client (outbound WS to CloudCore :10000)
    |       +-- ServiceBus (proxies to localhost:8000)
    |
    +-- containerd
    +-- Edge pod (hostPort:8000)
```

## CloudCore Installation

**Method:** KubeEdge Helm chart or keadm init

```bash
# On cloud CP node
keadm init --cloudcore-port=10002 --kube-config=/etc/rancher/k3s/k3s.yaml
```

**CloudCore ports:**
- :10000 — CloudHub WebSocket (edge nodes connect here)
- :10002 — CloudHub HTTPS (TLS enabled)
- :9443 — CloudCore REST API (plain HTTP, internal only)

**CloudCore REST behavior (v1.23.1):**
- Plain HTTP, no TLS (code has `// TODO: add tls for router`)
- Endpoint pattern: `http://<CLOUD_PRIVATE_IP>:9443/<node_name>/<namespace>/<service>`
- Example: `http://<CLOUD_PRIVATE_IP>:9443/edge-ec2-node/edgecloud/edge-node`

## EdgeCore Installation

**Method:** Manual binary installation via SSM

```bash
# On edge node via SSM
VERSION=v1.23.1
wget https://github.com/kubeedge/kubeedge/releases/download/${VERSION}/kubeedge-${VERSION}-linux-amd64.tar.gz
tar xzf kubeedge-${VERSION}-linux-amd64.tar.gz
cp kubeedge-${VERSION}-linux-amd64/edge/edgecore /usr/local/bin/
```

**EdgeCore config (/etc/kubeedge/config):**

```yaml
modules:
  edged:
    hostnameOverride: edge-ec2-node
    containerRuntime: containerd
  cloudHub:
    servers:
      - url: wss://<CLOUD_IP>:10000
    token: <GENERATE_VIA_keadm_gettoken>
  deviceTwin:
    enabled: false
  eventBus:
    enabled: false
```

**EdgeCore connection:** Outbound WebSocket to CloudCore :10000. No inbound ports needed.

## Node Registration

After EdgeCore starts, it registers with CloudCore. The node appears in `kubectl get nodes` with `SchedulingDisabled` (KubeEdge default). Enable scheduling:

```bash
kubectl uncordon edge-ec2-node
```

Then label for edge workloads:

```bash
kubectl label node edge-ec2-node kubernetes.io/hostname=edge-ec2-node
```

## Rules and RuleEndpoints

All Rules and RuleEndpoints are now committed as repository files:

- **Rules:** `infra/k3s/edgecloud-kubeedge-rules.yaml` (4 rules: detect-route, health-route, metrics-route, video-route)
- **RuleEndpoints:** `infra/k3s/edgecloud-kubeedge-ruleendpoints.yaml` (2 endpoints: rest-source, servicebus-target)

Apply with:
```bash
kubectl apply -f infra/k3s/edgecloud-kubeedge-ruleendpoints.yaml
kubectl apply -f infra/k3s/edgecloud-kubeedge-rules.yaml
```

Or use the rebuild script: `bash infra/rebuild/scripts/07-configure-rules.sh`

## ServiceBus Path (verified)

```
Cloud application
    -> CloudCore REST :9443
    -> Rule (detect-route / health-route / metrics-route / video-route)
    -> RuleEndpoint (rest-source -> servicebus-target)
    -> CloudHub :10000 (WebSocket)
    -> EdgeCore (outbound WS connection)
    -> ServiceBus (localhost:8000)
    -> Edge pod (hostPort:8000)
```

## Validation

After rebuild, verify the full path:

```bash
# Edge health through ServiceBus
kubectl exec -n edgecloud deployment/orchestrator -- \
  curl -sf http://<CLOUD_PRIVATE_IP>:9443/edge-ec2-node/edgecloud/health

# Edge metrics through ServiceBus
kubectl exec -n edgecloud deployment/orchestrator -- \
  curl -sf http://<CLOUD_PRIVATE_IP>:9443/edge-ec2-node/edgecloud/metrics

# Edge detect through ServiceBus
kubectl exec -n edgecloud deployment/orchestrator -- \
  curl -sf -X POST http://<CLOUD_PRIVATE_IP>:9443/edge-ec2-node/edgecloud/detect \
  -H "Content-Type: application/json" \
  -d '{"image_base64": "<BASE64_JPEG>"}'
```

## hostPort Requirement

The edge pod MUST use `hostPort: 8000`. Removing it breaks ServiceBus connectivity because EdgeCore connects to `localhost:8000` on the host, and the hostPort bridges host network namespace to pod network namespace. This was proven in Phase 9 gate 9D.

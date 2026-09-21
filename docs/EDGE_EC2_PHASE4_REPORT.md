# Edge EC2 Migration — Phase 4 (EdgeCore Install & Join to CloudCore) Report

Date: 2026-08-31
Status: **PASS — awaiting approval**
Repo: `C:\Vignpro\EdgeCloud-Orchestrator`
AWS profile: `edgecloud` · Region: `ap-south-1` · Account: `325580898273`

## Objective
Install the patched KubeEdge **EdgeCore (v1.23.1-dirty)** on the dedicated Edge EC2 node (`i-0080aa7404208982c`, 10.0.1.123) and join it to the existing CloudCore (`13.206.229.162`) as a single `edge-ec2-node`, with containerd as the CRI. **Do NOT modify** CloudCore/K3s/WSL2/RDS/ECR/SGs. Token-based cert bootstrap used; token cleared after join; no YOLO/nginx/Rules yet (out of scope).

---

## A. Scope & Non-Goals
- **In scope:** EdgeCore binary install, `edgecore.yaml` config, one `edgecore.service` systemd unit, token bootstrap certs, node registration, 5-min continuous Ready gate, env verification.
- **Non-goals (unchanged):** no k3s/kubelet/kubeadm/docker on edge; no production CloudCore/K3s/WSL2/RDS/ECR/SG changes; YOLO/nginx/Rules/RuleEndpoints deferred; dashboard/monitoring deferred.

## B. Node Inventory (unchanged baseline)
| Node | ID | Private IP | Public IP | Role | Runtime | State |
|---|---|---|---|---|---|---|
| CloudCore | i-07ecfbdd7781c5ef5 | 10.0.1.113 | 13.206.229.162 | control-plane | containerd 2.1.5-k3s1.32 | Ready (untouched) |
| Edge EC2 (this phase) | i-0080aa7404208982c | 10.0.1.123 | 13.206.238.62 | agent,edge | containerd 2.2.5 | **Ready (joined)** |
| WSL2 legacy edge | — | 172.18.125.42 | — | agent,edge | containerd 1.7.28 | NotReady (broken, untouched) |

## C. Pre-conditions satisfied
- Phase 2 additive Terraform (edge_node.tf) deployed & approved; egress-only SG `sg-074dd39fb8d93006b`.
- Phase 3 runtime (containerd 2.2.5, runc 1.3.5, CNI 1.7.1, crictl 1.31.1, iptables-nft) validated **15/15**.
- Phase 4 Step A: CloudCore baseline captured (cloudcore.service pid 503357, ports 10000/10002, k3s.yaml present).
- Phase 4 Step B: patched EdgeCore binary (v1.23.1-dirty, 100277552 bytes, SHA256 `77b3632d…)`) transferred to edge `/usr/local/bin/edgecore` (0555), checksums verified.

## D. EdgeCore config written
`/etc/kubeedge/config/edgecore.yaml` (replicated from WSL2 known-good, v1alpha2) with:
- `edgecoreVersion: v1.23.1-dirty`
- `hostnameOverride: edge-ec2-node`
- `edgeHub.httpServer: https://13.206.229.162:10002`
- `edgeHub.websocket.server: 13.206.229.162:10000` (enable true)
- `edgeHub.rotateCertificates: true`
- `edgeHub.tlsCaFile/certs/ca/rootCA.crt` + `/etc/kubeedge/certs/server.{crt,key}`
- `projectID: e632aba927ea4ac2b575ec1603d56f10`
- `edged` containerd endpoints `unix:///run/containerd/containerd.sock`, `podSandboxImage: kubeedge/pause:3.6`
- Per-file mode 600. Backup `edgecore.yaml.bak.withtoken` created before token clear, then **deleted** after join.

## E. Token bootstrap (cert issuance)
- Fresh token generated on CloudCore via `keadm gettoken --kube-config /etc/rancher/k3s/k3s.yaml`.
- **Not printed in this report, not committed, not stored in Git.**
- Relayed to edge via short-lived temp S3 object (presigned URL) → decoded on-node → injected into `edgeHub.token` for one-time bootstrap, then cleared.
- EdgeCore `getCurrent()` failed (no certs), invoked `applyCerts()`: fetched CloudCore CA from `https://13.206.229.162:10002`, validated by token, requested & stored edge certs →
  - `/etc/kubeedge/ca/rootCA.crt` (574 B)
  - `/etc/kubeedge/certs/server.crt` (595 B)
  - `/etc/kubeedge/certs/server.key` (227 B)
- Confirmed auto-bootstrap code path in `edge/pkg/edgehub/certificate/certmanager.go` (`GetCACert` + `applyCerts`).

## F. One systemd service
`/etc/systemd/system/edgecore.service`: `ExecStart=/usr/local/bin/edgecore --config /etc/kubeedge/config/edgecore.yaml --v=2`, `Restart=always`, `RestartSec=10`, `LimitNOFILE=65536`, `Requires=containerd.service`. Single unit, enabled.

## G. Registration & Ready
- CloudCore log/API shows node **`edge-ec2-node` Registered**, role `agent,edge`, version `v1.32.10-kubeedge-v1.23.1-dirty`, containerd `2.2.5+unknown`, InternalIP `10.0.1.123`.
- Ready condition: **Ready=True [EdgeReady]**; MemoryPressure/DiskPressure/PIDPressure all False.
- PodCIDR assigned `10.42.2.0/24`.
- Token cleared from config to empty (`token: ""`); EdgeCore restarted and **recovered using certs alone** (`"Node was previously registered"`, `"Successfully registered node"`), NRestarts=0.

## H. 5-min continuous Ready gate (30s sampling) — **PASS**
10/10 samples healthy over 300s:

| Sample | TS | edgecore | edgepid | edge-restart | containerd | ctrdpID | ctrd-restart |
|---|---|---|---|---|---|---|---|
| 1 | 16:57:40Z | active | 31191 | 0 | active | 27259 | 0 |
| 2 | 16:58:10Z | active | 31191 | 0 | active | 27259 | 0 |
| 3 | 16:58:40Z | active | 31191 | 0 | active | 27259 | 0 |
| 4 | 16:59:10Z | active | 31191 | 0 | active | 27259 | 0 |
| 5 | 16:59:40Z | active | 31191 | 0 | active | 27259 | 0 |
| 6 | 17:00:10Z | active | 31191 | 0 | active | 27259 | 0 |
| 7 | 17:00:40Z | active | 31191 | 0 | active | 27259 | 0 |
| 8 | 17:01:10Z | active | 31191 | 0 | active | 27259 | 0 |
| 9 | 17:01:40Z | active | 31191 | 0 | active | 27259 | 0 |
| 10 | 17:02:10Z | active | 31191 | 0 | active | 27259 | 0 |

EdgeCore `lastHeartbeatTime` confirmed continuing (e.g. 17:01:54Z). **CONTINUOUS_READY=PASS**.

## I. CRI verification
- `crictl info`: `RuntimeReady` + `NetworkReady` healthy.
- `crictl version`: RuntimeName `containerd`, RuntimeVersion `2.2.5+unknown`, **RuntimeApiVersion `v1`**.
- `crictl ps -a` / `crictl pods`: no stale containers/pods.

## J. Environment isolation (nothing else on edge)
- Running services: **only** `containerd.service` + `edgecore.service`.
- Processes: only `containerd` (27259) + `edgecore` (31191).
- `k3s`, `kubelet`, `kubeadm`, `docker`, `dockerd` all **absent** (not installed).

## K. Error/pressure scan
- **No PLEG errors, no runtime error, no `rpc error`, no `failed to start`** in EdgeCore logs (5-min window).
- Only benign, non-blocking MQTT reconnect logs (`dial tcp 127.0.0.1:1883: connection refused`) from `eventBus` mqttMode 2 — identical to WSL2 known-good config and non-fatal.

## L. Security cleanup — **done**
- Edge node: removed `/tmp/kubeedge_token.b64` and `/etc/kubeedge/config/edgecore.yaml.bak.withtoken` (plaintext token). Config `token: ""`.
- Cloud node: removed `/tmp/kubeedge_token.txt/.b64/_err.txt`.
- S3 relay bucket `kubeedge-token-relay-20260831222022` + object deleted (404 confirmed).
- Windows relay temp files removed.
- Final post-cleanup health: edgecore+containerd active, NRestarts=0, certs intact, config token empty.

## M. Artifacts (untracked working tree — not committed)
- `infra/terraform/edge_node.tf` + `edge_user_data.sh` (Phase 2, deployed).
- `infra/scripts/ssm-run.ps1` (SSM helper).
- Edge runtime binaries: `/usr/local/bin/edgecore`, crictl, containerd (Phase 3).

## N. Gates (from plan E1–E13)
| Gate | Result |
|---|---|
| Gated/isolated edge node, egress-only | PASS |
| containerd CRI present & healthy | PASS (2.2.5, API v1) |
| Patched EdgeCore v1.23.1-dirty installed | PASS |
| Single edgecore systemd service | PASS |
| Node `edge-ec2-node` joins CloudCore | PASS |
| Node Ready (agent,edge) | PASS |
| No k3s/kubelet/docker on edge | PASS |
| 5-min continuous Ready (30s) | PASS (10/10) |
| crictl RuntimeReady/NetworkReady, API v1 | PASS |
| No PLEG/runtime errors | PASS |
| Token not leaked, cleared post-join | PASS |

## O. Known observations (non-blocking)
- `eventBus` mqttMode 2 emits periodic `127.0.0.1:1883` connect-refused logs (no embedded broker in this mode) — same as WSL2 config, non-fatal; not run in report.
- `edgecore --version` triggers a benign `NodeIP is empty, use default ip` validation warning (uses default NIC IP to reach cloud).
- Legacy `wsl2-edge-node` remains NotReady (unchanged/broken, out of scope).

## V. Next steps (Phase 5+ candidates — NOT started, await approval)
- Optional: schedule/placement verification, YOLO workload deployment (Rule/RuleEndpoint), dashboard/monitoring integration via `edge/api`.
- Update `PROJECT_ROADMAP.md.txt` only upon approval.

**STOP — awaiting Phase 4 approval.**

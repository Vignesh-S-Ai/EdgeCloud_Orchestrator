# Edge EC2 Migration — Phase 5 (YOLO Edge Application Deployed on edge-ec2-node) Report

Date: 2026-08-31
Status: **PASS — awaiting approval**
Repo: `C:\Vignpro\EdgeCloud-Orchestrator`
AWS profile: `edgecloud` · Region: `ap-south-1` · Account: `325580898273`

## Objective
Deploy the existing YOLO edge application (`edgecloud/edge-node`) on the dedicated Edge EC2 node (`i-0080aa7404208982c`, 10.0.1.123) via a KubeEdge-backed K3s Deployment, prove the workload runs (pod Running/Ready, `/health`, `/metrics`, `/detect` all returning valid results), and hold a stability gate. **Do NOT modify** production CloudCore/K3s/WSL2/RDS/ECR/SGs/Rules. Cloud-to-edge ServiceBus tests (E10/E11) are **deferred out of this phase's scope**.

---

## A. Scope & Non-Goals
- **In scope:** ECR auth fix (hosts.toml), deploy `edge-node` with `nodeSelector=edge-ec2-node`, verify pod Running/Ready, verify local endpoints `/health`, `/metrics`, `/detect` (real YOLO inference), 10-min stability gate, ECR auth auto-refresh lifecycle.
- **Non-goals:** no cloud-to-edge ServiceBus/Rule/RuleEndpoint (deferred, E10/E11), no orchestrator/scheduler modification, no dashboard/monitoring, no WSL2 retirement, no production CloudCore/K3s/ECR/SG changes.

## B. Baseline (Step 1 — PASS)
- `edge-ec2-node` **Ready** (agent,edge, v1.32.10-kubeedge-v1.23.1-dirty, containerd 2.2.5+unknown).
- EdgeCore active (pid 31191), containerd active (pid 27259), restarts 0/0; `crictl info` RuntimeReady+NetworkReady; apiVersion v1; 0 errors/5min.
- `cloud ip-10-0-1-113` Ready; `wsl2-edge-node` NotReady (legacy, untouched).

## C. Deployment manifest (Step 2)
- `infra/k3s/edge-node-deployment-edge.yaml` — single change vs original: `nodeSelector kubernetes.io/hostname: edge-ec2-node` (was `wsl2-edge-node`). Everything else identical:
  - image `325580898273.dkr.ecr.ap-south-1.amazonaws.com/edgecloud/edge-node:latest`
  - `imagePullSecrets: ecr-registry-secret`, containerPort/hostPort 8000
  - env `EDGE_HOST=0.0.0.0`, `EDGE_PORT=8000`, `EDGE_LOG_LEVEL=INFO`, `EDGE_MODEL_DEVICE=cpu`, `EDGE_SCHEDULER_ENABLED=true`, `EDGE_SCHEDULER_PRIORITY=medium`
  - resources req 200m/512Mi, limit 2000m/2Gi; startup (30×5s) / readiness (60/10) / liveness (90/15) probes on `/health`
- Image confirmed present in private ECR (tag `latest`).

## D. ECR access (Step 3)
- Edge IAM role `edgecloud-edge-node-role` `get-authorization-token` OK; can describe repo `edgecloud/edge-node`. Image is **private ECR**.

## E. Networking proof on the edge node
- **Step 5 (test workload):** `nginx:alpine` test pod with `nodeSelector=edge-ec2-node` ran `1/1 Running` (IP 10.244.0.3) — CNI/network on the edge node works (`curl http://127.0.0.1:8000/` → 200). Cleanup verified (`crictl pods/ps -a` empty).
- **Cross-node note (expected, non-blocking):** cloud→edge ClusterIP/pod-IP/hostPort are not routed (edge SG `sg-074dd39fb8d93006b` is **egress-only**; pod overlay 10.244.0.x is node-local). Cloud→edge API traffic will be carried by CloudCore ServiceBus (E10/E11) in a later phase — consistent with this phase's scope.

## F. ECR auth fix — the key change (Steps 7–8)
- **Problem:** KubeEdge/edged did not pass the `ecr-registry-secret` imagePullSecret to containerd → first pod attempt hit `ImagePullBackOff: 403 Forbidden`.
- containerd **2.2.5 does not honor inline `credHelpers`** (config dump strips it).
- **Fix:** switched to the containerd **hosts.toml** registry model:
  - `config_path='/etc/containerd/certs.d'` set in the `cri.v1.images.registry` block.
  - `/etc/containerd/certs.d/325580898273.dkr.ecr.ap-south-1.amazonaws.com/hosts.toml` with `[host."https://…".header] Authorization = "Basic <token>"` derived from the **EC2 IAM role** (no dockerconfigjson / no static secret on node).
  - containerd restarted; `crictl pull …edge-node:latest` → **success** (image sha256 `8e4ee2880f63…`, 526MB).
- YOLO pod recovered → `1/1 Running`, `restarts=0`, **`ready=true`**, node `edge-ec2-node`.
- **Config hygiene:** orphaned `credHelpers` block removed from `config.toml` (grep count 0).

## G. Application startup verified (Step 8)
Container logs (crictl, sanitized):
- `Started server process [1]`
- `[edge.ai.detector] Loading model yolov8n.pt on device=cpu … Model loaded: 80 classes`
- `[edge.api.app] Edge Node 'edge-node' started` / `Application startup complete` / `Uvicorn running on http://0.0.0.0:8000`
- `/health` probes returning 200 (startup/readiness/liveness passing).
- No crash loop, no missing dependency, no OOM. (Benign Ultralytics warning only: `/home/appuser/.config` not writable → falls back to `/tmp/Ultralytics`.)

## H. Endpoint tests — all PASS (Step 9, local on edge host 127.0.0.1:8000)
| Endpoint | Result |
|---|---|
| `GET /health` | **200** `{"status":"degraded","service":"edge-node","version":"0.1.0","model_loaded":true,"camera_open":false,…}` (degraded only because no camera; **model_loaded=true**) |
| `GET /metrics` | **200** `cpu_percent:0.5, ram_percent:20.9, ram_used_gb:0.53, disk_percent:18.3,…` |
| `POST /detect` | **200** — real YOLOv8n inference on `bus.jpg` (810×1080): `inference_ms:1577.82`, **4 detections** — 1 `bus` (0.873) + 3 `person` (0.825–0.866). Correct detections. |

An empty-payload `/detect` correctly returned **422** (validation works).

## I. ECR auth auto-refresh lifecycle (added for ongoing operability)
- ECR `GetAuthorizationToken` returns `authorizationToken = Base64("AWS:<pwd>")` → used **directly** as the Basic `Authorization` header (double-encoding caused a 400 and was corrected).
- `/usr/local/sbin/edge-ecr-refresh.sh` (IAM role, rewrites hosts.toml, chmod 700).
- systemd `edge-ecr-refresh.{service,timer}` — runs every 8h (RandomizedDelay 10min, Persistent), well under the 12h token lifetime.
- Verified: manual run OK; `crictl pull …edge-node:latest` → `Image is up to date…` (200 via HEAD) after refresh.

## J. 10-min stability gate (E12) — **PASS**
20 samples @ 30s; edgecore + containerd both stable, PIDs constant, `NRestarts=0`:

| Sample | edgecore | edge PID | containerd | ctrd PID | pod |
|---|---|---|---|---|---|
| 0–20 | active | 33990 | active | 33962 | Ready |
| … | active (constant) | 33990 | active (constant) | 33962 | Ready |

- Pod `edge-node-fc54dc46-6xdd6` Ready, `restarts=0`, aged 35 min at final check.
- Node `edge-ec2-node` conditions: MemoryPressure=False, DiskPressure=False, PIDPressure=False, **Ready=True**.

## K. Error scan
- **No PLEG, no `CRI.*error`, no `failed to start sandbox`, no FATAL** in EdgeCore logs. (Initial non-zero "error window" counts were **false positives** — they matched routine cloudcore→edge `kind:Node` status-sync messages containing the substring `Unknown`, not real errors.)
- Only benign, non-blocking **MQTT** reconnect logs (`dial tcp 127.0.0.1:1883: connection refused`) from `eventBus` `mqttMode: 2` — no embedded broker installed; eventbus module idle. Identical to WSL2 known-good config; non-fatal, does not affect Ready or workload.

## L. Security & cleanup — **done**
- ECR auth handled via IAM role only (permission derived on-demand); **no plaintext ECR secret committed or persisted** on node or in repo.
- Session temp relay files (`p5_*.sh`, `p5_*_b64.txt`) removed from local temp dir.
- `config.toml` orphaned `credHelpers` removed; hosts.toml chmod 600.
- No git changes: only `Architecture.txt` + `README.md` remain tracked (untouched); all `infra/`, `docs/`, `edge/` remain untracked.

## M. Artifacts (untracked working tree — not committed)
- `infra/k3s/edge-node-deployment-edge.yaml` — edge-ec2-node variant (only nodeSelector changed).
- `infra/k3s/edge-node-service.yaml` (unchanged, ClusterIP 8000→8000).
- Edge node: `/usr/local/sbin/edge-ecr-refresh.sh`, `/etc/systemd/system/edge-ecr-refresh.{service,timer}`, `/etc/containerd/certs.d/<repo>/hosts.toml`.

## N. Gates (plan E1–E13)
| Gate | Result |
|---|---|
| E7 YOLO pod 1/1 Running on edge-ec2-node | **PASS** |
| E8 local /health → 200 | **PASS** |
| E9 local /detect → valid detection JSON | **PASS** (4 detections) |
| E12 10-min stability (no restarts, node Ready, no CRI/PLEG errors) | **PASS** (20/20) |
| E10/E11 CloudCore→ServiceBus→edge health/detect | **Deferred to next phase** (out of this phase's scope) |
| E13 Performance measurements | Partial (see below) |

**Deployed state unchanged elsewhere:** `wsl2-edge-node` NotReady (untouched, legacy); cloud node Ready; only pre-existing `edge-node-5cc9b74cb5` RS/pods linger (legacy garbage, not touched — could be cleaned in a follow-up if approved).

## O. Performance snapshot (E13 — preliminary, local on edge)
- `/detect` (810×1080 bus.jpg, CPU): **inference_ms ≈ 1578 ms** on t3.medium (2 vCPU). Typical for YOLOv8n-CPU on a mid-size image.
- `/health` ≈ 1.4 ms; `/metrics` ≈ 1.0 s (psutil gather).
- Runtime, edge node (during stability): edgecore ~27.7 MB RSS; pod within resource limits.

## P. Known observations (non-blocking)
- `eventBus` mqttMode 2 emits periodic `127.0.0.1:1883` connect-refused logs (no embedded broker) — identical to WSL2 config, non-fatal. Could set `mqttMode: 0` only if a config change is explicitly approved later.
- Cross-node (cloud→edge) direct ClusterIP/pod-IP access is not routed by design (egress-only SG; ServiceBus is the intended path, deferred).
- Legacy `wsl2-edge-node` and old `edge-node-5cc…` pods remain (out of scope; candidate for follow-up cleanup on approval).

## Next steps (candidates — NOT started, await approval)
- E10/E11: create node-scoped ServiceBus Rule/RuleEndpoint for `edge-ec2-node` and verify cloud→edge `/health` + `/detect` via CloudCore `:9443`.
- Optional legacy cleanup: remove `edge-node-5cc…` RS/pods; WSL2 retirement plan (post-E13).

**STOP — awaiting Phase 5 approval.**

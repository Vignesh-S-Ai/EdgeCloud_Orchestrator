# Phase 10 — Gate 10B: Release of `edge-node:10b` (frame_step=1 fix)

**Date:** 2026-09-02
**Predecessor:** Gate 10A baseline (PASS, `docs/phase10/10A_baseline.md`)
**Scope:** Deploy the approved 10b image (the `.gitignored` fix for the latent `frame_step=1` video bug) and live-verify. **No other Phase 10 gate touched** (10C TLS, 10D HTTPS, 10E metrics, 10F WSL2 all NOT started).

Also includes an **IAM prerequisite** (scoped ECR push) required to upload the 10b image — see below.

---

## IAM prerequisite (enabling the push)

The cloud build host could not push to ECR (`ecr:InitiateLayerUpload` denied; role only had `edgecloud-ecr-pull`). Per approval, one **additive, scoped** inline policy was added:

- **Role:** `edgecloud-ec2-role` (unchanged otherwise)
- **New inline policy:** `edgecloud-ecr-push`
- **Permissions added (exact):** `ecr:InitiateLayerUpload`, `ecr:UploadLayerPart`, `ecr:CompleteLayerUpload`, `ecr:PutImage`
- **Resource (scoped strictly to one repo):** `arn:aws:ecr:ap-south-1:325580898273:repository/edgecloud/edge-node`
- **Unchanged:** `edgecloud-ecr-pull`, `edgecloud-cloudwatch`, `edgecloud-secrets-read`, attached `AmazonSSMManagedInstanceCore`. No `ecr:*`, no cross-repo grant.

**Image pushed:** `325580898273.dkr.ecr.ap-south-1.amazonaws.com/edgecloud/edge-node:10b`
**Repo tags:** `10b` + `latest` (`10b` kept as the durable release tag)
**Digest:** `sha256:3a13ce5c31090b2fa2fc3dce26a4bbc3f7bb4c3dc597950d6a44eaa0d838e27e`

---

## Pre-deployment baseline (recorded before change)

**Deployment `edge-node` (namespace `edgecloud`):**
- Image: `...edge-node:latest`; running imageID digest `sha256:e995b8a0de55ac8c5de8255ce6d725f65d25aa5fa0ae29afc2dbbe98be756657` (**rollback target**)
- Replicas: 1; strategy RollingUpdate (maxSurge 25% / maxUnavailable 25%)
- Node selector: `kubernetes.io/hostname: edge-ec2-node`
- containerPort 8000 / **hostPort 8000** (present)
- Env: EDGE_HOST=0.0.0.0, EDGE_PORT=8000, EDGE_LOG_LEVEL=INFO, EDGE_MODEL_DEVICE=cpu, EDGE_SCHEDULER_ENABLED=true, EDGE_SCHEDULER_PRIORITY=medium
- Probes: startup (/health, period 5s, fail 30) / readiness (/health, delay 60s, period 10s) / liveness (/health, delay 90s, period 15s)
- Resources: requests 200m/512Mi, limits 2000m/2Gi; imagePullSecrets `ecr-registry-secret`
- Pre-deploy pod `edge-node-fc54dc46-kwfpr`: 1/1 Running, RESTARTS 0, on edge-ec2-node, IP 10.244.0.8

**Pre-deploy live behavior (OLD buggy build) — via ServiceBus:**
| check | result |
|---|---|
| /health | 200 |
| /metrics | 200 |
| /detect (cup.jpg, real YOLO) | 200, detection `scissors`, 115.2 ms |
| **video frame_step=1** | **200, 6 frames, frames_processed=0 (BUG), detections `{}`** |
| video frame_step=3 | 200, 6 frames, 2 processed, `{'scissors':2}` |
| video frame_step=5 | 200, 6 frames, 2 processed, `{'scissors':2}` |
| video frame_step=0 | 500 |
| video frame_step=-1 | 500 |
| video frame_step=100 | 200, 1 processed, `{'scissors':1}` |
| **video frame_step=1.5** | **200, 0 processed (non-integer not rejected — lenient)** |
| orchestrator live | 200, actual=edge, total 2251.8 ms |
| orchestrator snapshot edge / cloud | 200 / 200 (actual=edge / actual=cloud) |
| direct edge :8000 | BLOCKED (timeout) |

---

## Kubernetes change (SMALLEST possible)

Only the container image was changed:

```
kubectl set image deploy/edge-node edge-node=325580898273.dkr.ecr.ap-south-1.amazonaws.com/edgecloud/edge-node:10b -n edgecloud
```

**Not changed:** hostPort, containerPort, Service, Rules, RuleEndpoints, ServiceBus, EdgeCore, CloudCore, scheduler, orchestrator, node selector, probes, env, resources, imagePullSecrets, SG, Terraform, IAM (IAM change above was the pre-push prerequisite only).

---

## Rollout

- Applying the image change immediately created new ReplicaSet `edge-node-6699b48fb` (image `:10b`); the new pod was **Pending**.
- **Root cause:** fixed `hostPort: 8000` + 1-replica RollingUpdate — the old pod still held hostPort 8000 on edge-ec2-node, so the new pod could not schedule (`0/2 nodes ... didn't have free ports`). Not an application failure.
- **Controlled step:** deleted the stale pre-10B pod to release hostPort 8000; the controller then scheduled the new 10b pod. Deployment rolled out successfully (`rollout status` exit 0).

**Resulting pod:** `edge-node-6699b48fb-bxjcw` — 1/1 Running, **RESTARTS 0**, phase Running, node `edge-ec2-node`, IP 10.244.0.9.
- image = `...edge-node:10b`
- imageID digest = `sha256:3a13ce5c31090b2fa2fc3dce26a4bbc3f7bb4c3dc597950d6a44eaa0d838e27e` (matches expected)
- Deployment: replicas 1 / ready 1 / available 1. No CrashLoopBackOff, no ImagePullBackOff. Exactly one live edge pod.

---

## Live frame_step=1 verification (primary acceptance) — via ServiceBus

Synthetic 6-frame `tiny.mp4`, real production ServiceBus path
(orchestrator → CloudCore REST :9443 → video-route → ServiceBus → EdgeCore → edge 127.0.0.1:8000 → hostPort DNAT → edge pod → /detect/video).

**BEFORE 10B:** `frame_step=1` returned HTTP 200 but processed **0 frames**, detections `{}`.
**AFTER 10B:** `frame_step=1` returned HTTP 200, **frames_processed = 6** (all 6 frames), **detections `{'scissors': 6}`**.

| metric (POST-10B, frame_step=1) | value |
|---|---|
| HTTP status | 200 |
| total_frames | 6 |
| frames_processed | **6** (was 0 pre-10B) |
| elapsed_ms | 2224.6 |
| effective_fps | 2.7 |
| detections | `{'scissors': 6}` |
| wall latency | 2244.6 ms |

---

## frame_step regression (POST-10B, all via ServiceBus)

| frame_step | pre-10B | post-10B | status |
|---|---|---|---|
| 1 | 200 (0 frames, BUG) | 200 (6 frames, 6 processed) | ✅ fixed |
| 3 | 200 (2 processed) | 200 (2 processed) | ✅ no regression |
| 5 | 200 (2 processed) | 200 (2 processed) | ✅ no regression |
| 100 | 200 (1 processed) | 200 (1 processed) | ✅ no regression |
| 0 | 500 | 500 | ✅ rejected |
| -1 | 500 | 500 | ✅ rejected |
| 1.5 (non-integer) | **200 (lenient)** | **500** | ✅ now rejected (int-typed contract; CloudCore renders edge 422 as 500) |
| "abc" (non-integer) | — | 500 | ✅ rejected |

---

## Negative video cases (via CloudCore/orchestrator)

- invalid extension (`.txt`) → **500**
- empty upload → **500**
- trailing slash on `/detect/video/` → **500**

Note: CloudCore REST translates upstream edge 4xx (422/400/415) into 500 responses on the ServiceBus path — documented known behavior (consistent with 10A).

---

## Edge regression (POST-10B, via ServiceBus)

| check | result |
|---|---|
| /health | 200 |
| /metrics | 200 |
| /detect (cup.jpg, real YOLO) | 200, detection `scissors`, 101.3 ms |
| live-metrics /orchestrate | 200, actual=edge, total 2214.65 ms, sched 2081.7 ms |
| snapshot edge orchestrate | 200, actual=edge |
| cloud-selected orchestrate | 200, actual=cloud |
| response schema | unchanged (selected/actual/decision_score/latencies/detections/annotated base64) |
| ServiceBus path | unchanged (same Rules/RuleEndpoints) |
| **direct edge :8000** | **BLOCKED (timeout) — expected security behavior** |

Cluster state after deploy: Rules unchanged (`detect-route`, `health-route`, `metrics-route`, `video-route`), RuleEndpoints unchanged (`rest-source`, `servicebus-target`), Services unchanged.

---

## Rollback procedure

If 10B had failed a critical gate, rollback = restore the previous image:
```
kubectl set image deploy/edge-node edge-node=325580898273.dkr.ecr.ap-south-1.amazonaws.com/edgecloud/edge-node:latest -n edgecloud
# then free hostPort if the new pod holds it, and confirm rollout + 10B-gated checks
```
The `:latest` tag in ECR currently points to the **10b** digest, so a durable rollback tag would be needed if ECR `:latest` must stay at the old build — rollback to the pre-10B running digest `sha256:e995b8a0de55ac8c5de8255ce6d725f65d25aa5fa0ae29afc2dbbe98be756657` (untagged image still retained in ECR for this purpose). Rollback is NOT exercised because 10B passed.

---

## Command IDs

- IAM push policy verify / image push: (see Phase push records) — push `1f76f0f5-b060-4509-8197-0152b7166b96` (PUSH_DONE_OK), tag `f4491891-6f8d-4784-8bd3-e546ab1bdb86`
- Pre-deploy baseline harness: `07dc4216-2ef5-468d-a73c-aed632543319` (and deploy/state checks `35d84e70`, `ea2ec225`, `c50ecfb5`)
- Deploy apply + rollout: `acb8f3f1` (state), `efbb6166-40a6-446c-84b9-06c5ae71a6db` (free port + rollout success)
- Post-deploy verification harness: `17dc847e-7e92-4241-a834-4d71acee2aa7`
- Final state check: `ebfa51c6-51ff-46d4-aed9-f255a28271a6`

---

## Verdict

**Gate 10B: PASS.**

- 10b image running, digest matches expected
- rollout succeeded, edge pod Ready on edge-ec2-node, RESTARTS 0
- **frame_step=1 now processes frames (0 → 6) with valid detections** — the important improvement
- frame_step=3 / 5 not regressed; invalid (0, -1, 1.5, non-int) rejected
- /health, /metrics, /detect 200; orchestrator functional; schema unchanged
- ServiceBus architecture, Rules, RuleEndpoints, hostPort:8000 unchanged
- direct edge :8000 remains blocked

**Stopped after 10B. No 10C/10D/10E/10F work begun. Awaiting approval for the next Phase 10 gate.**

# Gate 10E-5 — Pre-Deployment State Snapshot

**Date:** 2026-09-02
**Gate:** 10E-5 = controlled production deployment of the 10E metrics cache + benchmark.
**Phase:** Pre-deployment gate capture (read-only). Capture time ~13:20–13:30 UTC via SSM on `i-07ecfbdd7781c5ef5`.

---

## 1. Current scheduler image / tag / digest

- **Image:** `325580898273.dkr.ecr.ap-south-1.amazonaws.com/edgecloud/scheduler:latest`
- **Pull policy:** `Always`
- **Running digest (pod):** `…/edgecloud/scheduler@sha256:a3d9079d6386fdc5ccc4e1e036951cd1d39a103c85b90cc9944f05fa44cc9d25`

## 2. Current scheduler Deployment configuration

- Namespace `edgecloud`, Deployment `scheduler`, **replicas: 1**
- Strategy: `RollingUpdate` (maxSurge 25% / maxUnavailable 25%)
- Container port 8002; `imagePullSecrets: [ecr-registry-secret]`
- Readiness probe `GET /health` :8002 (initialDelay 10s, period 10s); startup probe `/health` (failureThreshold 15, period 3s)

## 3. Current scheduler environment variables

| Name | Value |
|------|-------|
| `SCHEDULER_PORT` | `8002` |
| `SCHEDULER_LOG_LEVEL` | `INFO` |

No `SCHEDULER_METRICS_TTL_SEC` present (cache disabled in production → default `0.0` inside the running image/config).

## 4. Current scheduler pod name(s)

- `scheduler-6dcbffbcdb-2kktm` (IP 10.42.0.6, on node `ip-10-0-1-113`)

## 5. Current pod readiness

- `READY=1/1`, `STATUS=Running`, `READY=true`

## 6. Current restart counts

- `RESTARTS=0` (scheduler started 2026-08-18T12:30:46Z)
- All other prod pods also `RESTARTS=0`

## 7. Current scheduler image digest

- `sha256:a3d9079d6386fdc5ccc4e1e036951cd1d39a103c85b90cc9944f05fa44cc9d25` (via pod `imageID`)

## 8. Current node readiness

| Node | Status | Role |
|------|--------|------|
| edge-ec2-node | Ready | agent,edge |
| ip-10-0-1-113 (cloud) | Ready | control-plane,master |
| wsl2-edge-node | Ready | agent,edge (re-registered ~13:00 UTC; pre-existing Phase 9 §9E caveat — WSL2 VM re-registered when powered on. Not caused by this gate; monitored, not modified.) |

## 9. Production baseline remains healthy

- Scheduler live `/decision` probe (pre-deploy, `:latest`): **HTTP 200**, `target=edge`, `score 82.6`, reason "Edge resources within capacity (CPU 0.0% ≤ 75.0%, RAM 26.1% ≤ 75.0%, DISK 26.4% ≤ 85.0%) and network latency 13.5ms ≤ 200.0ms; running locally."
- All prod pods `Running/Ready` with `RESTARTS=0` (cloud-node, edge-node, orchestrator, scheduler).

**Rules & RuleEndpoints (pre-deploy, unchanged):**
- Rules (`rules.rules.kubeedge.io`): `detect-route` (/detect), `health-route` (/health), `metrics-route` (/metrics), `video-route` (/detect/video)
- RuleEndpoints: `rest-source` (rest, `{}`), `servicebus-target` (servicebus, `service_port: "8000"`)
- Services: cloud-node ClusterIP 10.43.45.189:8001, edge-node ClusterIP 10.43.218.215:8000, orchestrator NodePort 10.43.112.251:8003→30083, scheduler ClusterIP 10.43.201.181:8002

## 10. Rollback image / digest known

- **Rollback image:** `325580898273.dkr.ecr.ap-south-1.amazonaws.com/edgecloud/scheduler:latest`
- **Rollback digest:** `sha256:a3d9079d6386fdc5ccc4e1e036951cd1d39a103c85b90cc9944f05fa44cc9d25`
- **Rollback env:** remove the `SCHEDULER_METRICS_TTL_SEC` env (or set `0`) → identical to `:latest`, cache disabled by default.
- Rollback procedure (if needed): `kubectl set image deploy/scheduler ...=scheduler:latest -n edgecloud` + clear the added env; verify pod Ready/RESTARTS=0 and `/decision` 200. No other changes.

---

Pre-deployment state captured. **No production change made in this step.**

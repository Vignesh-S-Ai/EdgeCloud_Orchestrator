# Gate 10E-2 — Live-Metrics Scheduling: Baseline

**Date:** 2026-09-02
**Gate:** 10E — live-metrics latency optimization baseline
**Phase:** 10E-2 = baseline capture (read-only). **No production change made.**

This baseline records the CURRENT production scheduler behavior (image `edgecloud/scheduler:latest`, Deployment unchanged) exercising the **live-metrics path** (`edge_url`/`cloud_url` supplied so the scheduler fetches metrics + latency itself).

---

## Benchmark methodology

- **Instrument:** `p10_10e_bench.py` run inside the `edgecloud` namespace from the orchestrator pod (`orchestrator-5d76f94584-lpx97`), posted to the scheduler ClusterIP service:
  - `POST http://scheduler.edgecloud.svc:8002/decision`
  - body: `{"workload":{"workload_id":"bench10e","latency_requirement_ms":100.0,"priority":"medium"}, "edge_url": EDGE, "cloud_url": CLOUD}`
  - `EDGE_URL = http://10.0.1.113:9443/edge-ec2-node/edgecloud` (CloudCore Router REST ServiceBus → edge)
  - `CLOUD_URL = http://cloud-node.edgecloud.svc:8001` (ClusterIP)
- Each request is a full synchronous `decide_remote`: `fetch_edge` (ServiceBus) → `fetch_cloud` → `measure_latency_ms` → policy → decision.
- Measured latency = end-to-end scheduler `/decision` response time (metric collection + policy decision). This is the lever the 10E optimization targets; forwarding/inference are orchestrator-stage steps, not part of `/decision`.
- **Concurrency:** 1, 2, 4, 8; **12 requests per worker** (12/24/48/96 total), single `httpx.AsyncClient(timeout=15.0)` per worker loop, `asyncio.Semaphore` gate.
- Stats: mean / median / min / max / p95 per concurrency level.

---

## Existing /decision baseline results (OLD production scheduler image)

Concurrency × 12 (all HTTP 200, no failures):

| Concurrency | Requests | 200 | Fail | Mean (ms) | Median (ms) | Min (ms) | Max (ms) | p95 (ms) |
|-------------|----------|-----|------|-----------|-------------|----------|----------|----------|
| 1 | 12 | 12 | 0 | 2100.9 | 2097.1 | — | — | 2153.1 |
| 2 | 24 | 24 | 0 | 2201.1 | 2198.5 | — | — | 2306.3 |
| 4 | 48 | 48 | 0 | 2305.8 | 2292.4 | — | — | 2446.5 |
| 8 | 96 | 96 | 0 | 3128.3 | 3342.9 | — | — | 3667.9 |

Observations:
- Baseline is ~2.1 s at concurrency 1 — dominated by the sequential ServiceBus round-trip for edge `/metrics` plus a fresh `httpx.AsyncClient` per request (no reuse/cache).
- Latency grows with concurrency (2.1 s → 3.1 s at 8), consistent with sequential per-request remote metric fetches serializing under load (no in-scheduler caching, one client per call).
- Success rate 100% at every level; no failures/errors.

---

## Infrastructure snapshot (at baseline, via SSM on cloud host i-07ecfbdd7781c5ef5)

**Kubernetes nodes / readiness (all Ready):**

| Node | Role | Version | Internal-IP | Status |
|------|------|---------|-------------|--------|
| edge-ec2-node | agent,edge | v1.32.10-kubeedge-v1.23.1-dirty | 10.0.1.123 | Ready |
| ip-10-0-1-113... (cloud) | control-plane,master | v1.32.13+k3s1 | 10.0.1.113 | Ready |
| wsl2-edge-node | agent,edge | v1.32.10-kubeedge-v1.23.1-dirty | 172.18.125.42 | Ready |

**Node capacity (kubelet):**

| Node | CPU | Memory |
|------|-----|--------|
| edge-ec2-node | 2 cpu | 3931700Ki |
| ip-10-0-1-113 (cloud) | 2 cpu | 3927992Ki |
| wsl2-edge-node | 4 cpu | 2978420Ki |

**Production pods (ns `edgecloud`) — all Running, Ready, RESTARTS=0:**

| Pod | Ready | Status | Restarts | IP | Node |
|-----|-------|--------|----------|----|------|
| cloud-node-6d9f488769-c5pph | 1/1 | Running | 0 | 10.42.0.19 | cloud |
| edge-node-6699b48fb-bxjcw | 1/1 | Running | 0 | 10.244.0.9 | edge-ec2-node |
| orchestrator-5d76f94584-lpx97 | 1/1 | Running | 0 | 10.42.0.18 | cloud |
| scheduler-6dcbffbcdb-2kktm | 1/1 | Running | 0 | 10.42.0.6 | cloud |

**Cloud host (10.0.1.113) load:** up 15d, load avg 0.06/0.09/0.09, 2 cores, Mem 3835 MB total / 1375 used / 2176 available. Idle at capture.

**Edge:** the live production edge reachable by the scheduler is `edge-ec2-node` at 10.0.1.123 via the CloudCore Router REST ServiceBus (`http://10.0.1.113:9443/edge-ec2-node/edgecloud`). Its kubelet capacity is 2 cpu / 3931700Ki, with the `edge-node` pod running on it.

---

## Timestamp

- Infra snapshot: **2026-09-02 13:07:58** (host time, SSM capture).
- Baseline benchmark: **2026-09-02** (pre-change, OLD production scheduler image, Deployment unchanged).

---

## Limitations

- `/decision` latency = metric collection + policy decision; it does **not** include orchestrator forwarding or inference latency (those are separate `/orchestrate` stages in Phase 9, not part of the scheduler lever). For an apples-to-apples comparison of the 10E optimization, the scheduler `/decision` metric is the correct instrument.
- Baseline was a single pass (no warm-up iteration); variance between runs is possible but all 4 concurrency levels were >98% backend (remote metric fetch) cost.
- Edge metrics are psutil snapshots of a mostly-idle demo edge node; latency is dominated by network/ServiceBus round-trip, not by edge compute load at this scale.
- Raw benchmark output raw JSON was not persisted to a file at run time; the summary (above) is the authoritative record. The instrument source (`p10_10e_bench.py`) is preserved and re-runnable for the optimized pass (10E-9).
- No writes/changes made during this baseline capture (read-only).

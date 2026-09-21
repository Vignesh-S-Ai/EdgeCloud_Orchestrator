# Gate 10E-1 — Live-Metrics Scheduling: Source Investigation

**Date:** 2026-09-02
**Gate:** 10E — live-metrics latency optimization (Phase 9 finding: ~80–87% of live edge scheduling latency is the scheduler's per-request metric collection).
**Phase:** 10E-1 = read-only source investigation. **No code changed in this step.**

---

## Live request path (traced)

```
orchestrator POST /orchestrate            (orchestrator/api/routes.py, service.py)
   └─ SchedulerClient.decide(...)         (orchestrator/clients.py)
      └─ POST /decision  {workload, edge_url, cloud_url}
         └─ DecisionEngine.decide_remote  (scheduler/decision_engine.py:61)
            ├─ MetricsClient.fetch_edge(edge_url)        → GET <edge_url>/metrics
            ├─ MetricsClient.fetch_cloud(cloud_url)      → GET <cloud_url>/metrics
            └─ MetricsClient.measure_latency_ms(cloud_url) → GET <cloud_url>/health
            └─ RuleBasedPolicy.decide(...)               (scheduler/policies.py)
```

The `edge_url` in production is the CloudCore ServiceBus base:
`http://10.0.1.113:9443/edge-ec2-node/edgecloud`, so `fetch_edge` does:

```
scheduler → GET http://10.0.1.113:9443/edge-ec2-node/edgecloud/metrics
          → CloudCore Router REST :9443 → ServiceBus → EdgeCore → edge /metrics
```

The `cloud_url` is `http://cloud-node.edgecloud.svc:8001` (ClusterIP, local/fast), so `fetch_cloud` and `measure_latency_ms` hit the cloud-node ClusterIP service directly.

---

## Answers to the 10E-1 questions

### 1. How many metric HTTP calls occur per orchestration (live) request?
**3 sequential HTTP GETs** in `decide_remote`:
1. `fetch_edge` → edge `/metrics` (via CloudCore ServiceBus — the slow hop)
2. `fetch_cloud` → cloud `/metrics`
3. `measure_latency_ms` → cloud `/health`

### 2. Sequential or concurrent?
**Fully sequential** — `decide_remote` awaits `fetch_edge`, then `fetch_cloud`, then `measure_latency_ms` in order (`scheduler/decision_engine.py:65-67`). There is no `asyncio.gather`.

### 3. Timeout values
- Scheduler `metrics_timeout_sec: float = 2.0` (`scheduler/config.py:68`).
- `MetricsClient.__init__` clamps to `max(0.5, ...)`.
- Orchestrator node/inference timeouts are separate (`OrchestratorSettings.timeout_sec`, default large).

### 4. Connection setup cost
Every `_get_json` opens a **new `httpx.AsyncClient`** (`scheduler/metrics_client.py:32-34`) inside the call and closes it on exit. This means a fresh TLS/TCP + connection-per-request each time — no connection pooling, no keep-alive reuse across requests.

### 5. Are HTTP connections reused?
**No.** A brand-new `AsyncClient` is created per `_get_json`. There is no `httpx.AsyncClient` instance kept alive at the `MetricsClient` level, and no `transport`/pool configured in production (the `transport` injection is test-only via `MockTransport`).

### 6. Does MetricsClient create a new client/session per request?
**Yes** — `async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:` inside `_get_json`. Each of the 3 calls per decision, and every decision, spins up a client.

### 7. Can a safe short-lived cache be introduced?
**Yes** — the edge/cloud resource `MetricsClient` snapshots are stable over short windows. A short-TTL in-memory cache keyed by URL would remove repeated `/metrics` fetches within the TTL window. **Latency (`/health`) must NOT be cached** — it is a real network measurement used by the policy and must stay fresh (see 10E-4 design).

### 8. Does the scheduler already have any caching?
**No.** `MetricsClient` has no cache. No memoization exists in the scheduler.

### 9. What happens when metrics are unavailable?
- `fetch_edge`/`fetch_cloud` catch `httpx.HTTPError`/`ValueError` and return `None` (`metrics_client.py:44-45`).
- `measure_latency_ms` returns `None` on failure.
- `decide_remote` passes whatever came back. If `edge is None or cloud is None` → `RuleBasedPolicy.decide` returns `Target.ERROR` with reason "Required metrics are unavailable … cannot decide placement" (`policies.py:109-120`).

### 10. How does stale/missing metrics affect target selection?
- **Missing** metrics → `ERROR` (decision returned; orchestrator surfaces a 503 "Workload not executed now"). Unchanged by any cache.
- **Stale (cached within TTL)** metrics → the policy still computes a decision from the cached snapshot exactly as it would from a fresh one. If the cached snapshot is from ≤TTL ago, this is equivalent to the scheduler seeing that snapshot. No unsafe "not-available" entry is ever cached as a success (only successful payloads are cached), so a failed fetch still yields `None` → `ERROR` as today.

### 11. Minimum safe TTL?
The edge metrics are psutil snapshots on a mostly-idle demo edge node; a small TTL (~1–2 s) keeps decisions fresh enough and is far below any threshold-drift risk. **Start conservatively at 1 s, not 0.** The cache must never store a stale value that persists past the TTL, and must not cache failures.

---

## Bottleneck hypothesis (to confirm in 10E-3)

The dominant cost is the **sequential ServiceBus round-trip for edge `/metrics`** (one full orchestrator→CloudCore→ServiceBus→EdgeCore→edge round trip per request), **multiplied** because every request re-fetches it (no cache) and the fetch happens **sequentially before** cloud metrics and latency. Plus per-request `AsyncClient` creation (no connection reuse). Baseline measured live: ~2.1 s at concurrency 1, degrading to ~3.1 s at concurrency 8 (all HTTP 200). Full numbers recorded under `docs/phase10/10E/`.

---

## Note (no change made)

This step is read-only. The scheduler, orchestrator, CloudCore, ServiceBus, rules, policy thresholds, SG and Terraform were **not modified** during 10E-1. Baseline benchmark of current production is captured separately (10E-2).

"""10E baseline benchmark: scheduler live-metrics /decision at concurrency 1/2/4/8 x12.

Runs inside the edgecloud namespace (from the orchestrator pod) against the
scheduler ClusterIP service, exercising the live-metrics path (edge_url/cloud_url
supplied so the scheduler fetches metrics+latency itself).
"""
import asyncio, json, statistics, time

SCHEDULER = "http://scheduler.edgecloud.svc:8002"
EDGE_URL = "http://10.0.1.113:9443/edge-ec2-node/edgecloud"
CLOUD_URL = "http://cloud-node.edgecloud.svc:8001"

WORKLOAD = {
    "workload_id": "bench10e",
    "latency_requirement_ms": 100.0,
    "priority": "medium",
}

def decision_body():
    return {"workload": WORKLOAD, "edge_url": EDGE_URL, "cloud_url": CLOUD_URL}

async def one_client_once():
    import httpx
    async with httpx.AsyncClient(timeout=15.0) as c:
        t0 = time.perf_counter()
        r = await c.post(f"{SCHEDULER}/decision", json=decision_body())
        dt = (time.perf_counter() - t0) * 1000.0
        return r.status_code, dt, r.text[:120]

async def worker(n, sem, results):
    async with sem:
        for _ in range(n):
            try:
                code, dt, body = await one_client_once()
                results.append((code, dt, body))
            except Exception as e:
                results.append((0, -1.0, f"EXC {e}"))

async def run_concurrency(conc, per=12):
    sem = asyncio.Semaphore(conc)
    results = []
    await asyncio.gather(*[worker(per, sem, results) for _ in range(conc)])
    codes = [r[0] for r in results]
    lats = [r[1] for r in results if r[1] >= 0]
    ok = codes.count(200)
    total = len(codes)
    return {
        "concurrency": conc,
        "requests": total,
        "ok_200": ok,
        "fail": total - ok,
        "codes": {c: codes.count(c) for c in set(codes)},
        "latency_ms_mean": round(statistics.mean(lats), 1) if lats else None,
        "latency_ms_median": round(statistics.median(lats), 1) if lats else None,
        "latency_ms_min": round(min(lats), 1) if lats else None,
        "latency_ms_max": round(max(lats), 1) if lats else None,
        "latency_ms_p95": round(sorted(lats)[int(len(lats)*0.95)-1], 1) if lats else None,
    }

async def main():
    results = []
    for conc in (1, 2, 4, 8):
        r = await run_concurrency(conc, per=12)
        results.append(r)
        print(json.dumps(r))
    print("BENCH_DONE")
    print(json.dumps({"summary": results}))

asyncio.run(main())

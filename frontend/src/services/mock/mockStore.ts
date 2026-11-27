/**
 * Mock data service.
 *
 * This module is the ONLY place where invented values are produced. It is
 * never imported by the live data source, and every screen fed by it carries a
 * visible "DEMO DATA" indicator (see TopBar).
 *
 * Numbers are calibrated against the project's own published benchmarks
 * (docs/FINAL_BENCHMARK_RESULTS.md): edge inference 114-232 ms, cloud ~193 ms,
 * scheduler 66 ms (cached) with occasional live-probe spikes, edge ~14 requests/s
 * worth of traffic. Decision reasons reuse the exact wording of
 * scheduler/policies.py so the UI matches the real Decision.reason strings.
 */
import type {
  ClusterNode,
  Decision,
  InferenceClassCount,
  InferenceRecord,
  LatencyPoint,
  LogLevel,
  LogFeed,
  NodeRole,
  OverviewSnapshot,
  Priority,
  ResourcePoint,
  RequestTotals,
  RoutingRecord,
  RoutingSnapshot,
  ServiceHealth,
  ServiceInfo,
  ServiceItem,
  SystemEvent,
  SystemMetrics,
  Target,
  WorkloadInventory,
  WorkloadItem,
} from '../../types';
import { average, percentile } from '../../lib/format';

// ---------------------------------------------------------------------------
// Deterministic-ish RNG
// ---------------------------------------------------------------------------
function mulberry32(seed: number): () => number {
  let a = seed;
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const clamp = (value: number, min: number, max: number) => Math.min(max, Math.max(min, value));
const round1 = (value: number) => Math.round(value * 10) / 10;

// Mirrors SchedulerSettings defaults (scheduler/config.py).
const POLICY = {
  edgeCpu: 70,
  edgeRam: 70,
  edgeDisk: 85,
  cloudCpu: 80,
  cloudRam: 80,
  cloudDisk: 90,
  maxLatency: 200,
  bias: { low: 0, medium: 5, high: 15 } as Record<Priority, number>,
};

const DETECTION_CLASSES = ['person', 'car', 'truck', 'bus', 'bicycle', 'motorcycle', 'dog'];

interface NodeState {
  edgeCpu: number;
  edgeRam: number;
  edgeDisk: number;
  cloudCpu: number;
  cloudRam: number;
  cloudDisk: number;
  netLatency: number;
  ramUsedGb: number;
  ramTotalGb: number;
  diskUsedGb: number;
  diskTotalGb: number;
}

const NODE_META = {
  edge: { ramTotalGb: 7.6, diskTotalGb: 29.5 },
  cloud: { ramTotalGb: 15.6, diskTotalGb: 78.4 },
};

// ---------------------------------------------------------------------------
// Store
// ---------------------------------------------------------------------------
class MockStore {
  private readonly rng = mulberry32(0xc10d13);
  private lastAdvance = Date.now();

  private state: NodeState = {
    edgeCpu: 33.4,
    edgeRam: 46.8,
    edgeDisk: 41.2,
    cloudCpu: 21.7,
    cloudRam: 37.5,
    cloudDisk: 32.9,
    netLatency: 18.6,
    ramUsedGb: 3.6,
    ramTotalGb: NODE_META.edge.ramTotalGb,
    diskUsedGb: 12.2,
    diskTotalGb: NODE_META.edge.diskTotalGb,
  };

  private latencySeries: LatencyPoint[] = [];
  private resourceSeries: ResourcePoint[] = [];
  private routing: RoutingRecord[] = [];
  private inference: InferenceRecord[] = [];
  private logs: SystemEvent[] = [];

  private lastSeriesT = 0;
  private lastRoutingT = 0;
  private lastInferenceT = 0;
  private lastLogT = 0;

  constructor() {
    this.seed();
  }

  // -- seeding ------------------------------------------------------------
  private seed(): void {
    const now = Date.now();

    // ~6 hours of routing history (about one request every 12 seconds).
    // The metric random-walk runs while seeding so the decision mix mirrors
    // what the rule-based policy would actually produce over a shift.
    this.lastRoutingT = now - 6 * 3600_000;
    while (this.lastRoutingT < now - 20_000) {
      this.lastRoutingT += 12_000 + Math.floor(this.rng() * 8000);
      this.walkState();
      this.routing.unshift(this.makeRoutingRecord(this.lastRoutingT));
    }
    this.routing.reverse();
    this.lastRoutingT = now;

    // ~100 minutes of inference history.
    this.lastInferenceT = now - 100 * 60_000;
    while (this.lastInferenceT < now - 15_000) {
      this.lastInferenceT += 26_000 + Math.floor(this.rng() * 20_000);
      this.walkState();
      this.inference.unshift(this.makeInferenceRecord(this.lastInferenceT));
    }
    this.inference.reverse();
    this.lastInferenceT = now;

    // ~120 minutes of metric / latency series (built after the history walk so
    // it ends at the current node state).
    this.lastSeriesT = now - 120 * 60_000;
    for (let i = 0; i < 121; i += 1) {
      this.walkState();
      this.appendSeriesPoint(this.lastSeriesT + i * 60_000);
    }
    this.lastSeriesT = now;

    // ~3 hours of system events.
    this.lastLogT = now - 3 * 3600_000;
    while (this.lastLogT < now - 30_000) {
      this.lastLogT += 25_000 + Math.floor(this.rng() * 40_000);
      this.logs.unshift(this.makeLogEvent(this.lastLogT));
    }
    this.logs.reverse();
    this.lastLogT = now;
  }

  // -- live advance -------------------------------------------------------
  /** Called on every read so charts/tables move like a real dashboard. */
  advance(): void {
    const now = Date.now();
    const elapsed = now - this.lastAdvance;
    if (elapsed < 500) return;
    this.lastAdvance = now;

    // At most one walk per 4 s no matter how many pages poll concurrently.
    if (elapsed >= 4000) this.walkState();

    if (now - this.lastSeriesT >= 30_000) {
      this.appendSeriesPoint(now);
      this.lastSeriesT = now;
    }

    while (now - this.lastRoutingT >= 9_000) {
      this.lastRoutingT += 9_000 + Math.floor(this.rng() * 6000);
      if (this.lastRoutingT > now) break;
      this.routing.push(this.makeRoutingRecord(this.lastRoutingT));
    }
    while (now - this.lastInferenceT >= 14_000) {
      this.lastInferenceT += 14_000 + Math.floor(this.rng() * 10_000);
      if (this.lastInferenceT > now) break;
      this.inference.push(this.makeInferenceRecord(this.lastInferenceT));
    }
    while (now - this.lastLogT >= 20_000) {
      this.lastLogT += 20_000 + Math.floor(this.rng() * 25_000);
      if (this.lastLogT > now) break;
      this.logs.push(this.makeLogEvent(this.lastLogT));
    }

    if (this.routing.length > 600) this.routing.splice(0, this.routing.length - 600);
    if (this.inference.length > 300) this.inference.splice(0, this.inference.length - 300);
    if (this.logs.length > 500) this.logs.splice(0, this.logs.length - 500);
    if (this.latencySeries.length > 240) this.latencySeries.splice(0, this.latencySeries.length - 240);
    if (this.resourceSeries.length > 240) this.resourceSeries.splice(0, this.resourceSeries.length - 240);
  }

  private walkState(): void {
    const s = this.state;
    // Mean-reverting walk: values hover around a realistic baseline and only
    // occasionally spike past the scheduler thresholds (which is what creates
    // cloud offloads, queued decisions and fallbacks in the history).
    const step = (value: number, target: number, jitter: number, min: number, max: number): number =>
      clamp(value + (target - value) * 0.07 + (this.rng() - 0.5) * jitter, min, max);

    s.edgeCpu = step(s.edgeCpu, 38, 10, 4, 96);
    if (this.rng() < 0.06) s.edgeCpu = clamp(s.edgeCpu + 16 + this.rng() * 28, 4, 97);
    s.edgeRam = step(s.edgeRam, 50, 5, 22, 93);
    s.edgeDisk = step(s.edgeDisk, 42, 0.6, 30, 88);

    s.cloudCpu = step(s.cloudCpu, 26, 8, 5, 88);
    if (this.rng() < 0.04) s.cloudCpu = clamp(s.cloudCpu + 22 + this.rng() * 34, 5, 95);
    s.cloudRam = step(s.cloudRam, 41, 5, 18, 86);
    s.cloudDisk = step(s.cloudDisk, 34, 0.5, 20, 74);

    s.netLatency = step(s.netLatency, 19, 9, 4, 340);
    if (this.rng() < 0.035) s.netLatency = clamp(s.netLatency + 130 + this.rng() * 210, 4, 360);

    s.ramUsedGb = round1((s.edgeRam / 100) * s.ramTotalGb);
    s.diskUsedGb = round1((s.edgeDisk / 100) * s.diskTotalGb);
  }

  private appendSeriesPoint(t: number): void {
    const s = this.state;
    const spike = this.rng() > 0.94;
    this.latencySeries.push({
      t,
      edgeMs: Math.round(clamp(118 + (this.rng() - 0.5) * 45 + (spike ? 70 : 0), 78, 320)),
      cloudMs: Math.round(clamp(196 + (this.rng() - 0.5) * 70, 140, 460)),
      schedulerMs: Math.round(clamp(68 + (this.rng() - 0.5) * 40, 38, 340)),
      totalMs: 0,
    });
    const point = this.latencySeries[this.latencySeries.length - 1];
    point.totalMs = Math.round(point.schedulerMs + point.edgeMs * 0.62 + point.cloudMs * 0.38 + 14);

    this.resourceSeries.push({
      t,
      edgeCpu: round1(s.edgeCpu),
      edgeRam: round1(s.edgeRam),
      edgeDisk: round1(s.edgeDisk),
      cloudCpu: round1(s.cloudCpu),
      cloudRam: round1(s.cloudRam),
      cloudDisk: round1(s.cloudDisk),
    });
  }

  // -- decision (mirrors scheduler/policies.py) ---------------------------
  private decide(priority: Priority): { target: Target; score: number; reason: string } {
    const s = this.state;
    const bias = POLICY.bias[priority];
    const edgeThr = { cpu: POLICY.edgeCpu + bias, ram: POLICY.edgeRam + bias, disk: POLICY.edgeDisk };
    const edgeViolations: string[] = [];
    if (s.edgeCpu > edgeThr.cpu) edgeViolations.push(`CPU ${s.edgeCpu.toFixed(1)}% > ${edgeThr.cpu.toFixed(1)}%`);
    if (s.edgeRam > edgeThr.ram) edgeViolations.push(`RAM ${s.edgeRam.toFixed(1)}% > ${edgeThr.ram.toFixed(1)}%`);
    if (s.edgeDisk > edgeThr.disk) edgeViolations.push(`DISK ${s.edgeDisk.toFixed(1)}% > ${edgeThr.disk.toFixed(1)}%`);

    const cloudViolations: string[] = [];
    if (s.cloudCpu > POLICY.cloudCpu) cloudViolations.push(`CPU ${s.cloudCpu.toFixed(1)}% > ${POLICY.cloudCpu.toFixed(1)}%`);
    if (s.cloudRam > POLICY.cloudRam) cloudViolations.push(`RAM ${s.cloudRam.toFixed(1)}% > ${POLICY.cloudRam.toFixed(1)}%`);
    if (s.cloudDisk > POLICY.cloudDisk) cloudViolations.push(`DISK ${s.cloudDisk.toFixed(1)}% > ${POLICY.cloudDisk.toFixed(1)}%`);

    const latencyOk = s.netLatency <= POLICY.maxLatency;
    const latencyNote = `latency ${s.netLatency.toFixed(1)}ms ${
      latencyOk ? '<=' : '>'
    } ${POLICY.maxLatency.toFixed(1)}ms`;

    const cpuP = Math.min(100, (s.edgeCpu / edgeThr.cpu) * 100);
    const ramP = Math.min(100, (s.edgeRam / edgeThr.ram) * 100);
    const diskP = Math.min(100, (s.edgeDisk / edgeThr.disk) * 100);
    const score = round1(100 - (0.5 * cpuP + 0.3 * ramP + 0.2 * diskP));

    const edgeOk = edgeViolations.length === 0;
    const cloudOk = cloudViolations.length === 0;

    if (!edgeOk && !cloudOk) {
      return {
        target: 'error',
        score,
        reason: `Edge and cloud both saturated (edge: ${edgeViolations.join(', ')}; cloud: ${cloudViolations.join(', ')}); no healthy placement available.`,
      };
    }
    if (edgeOk) {
      return {
        target: 'edge',
        score,
        reason: `Edge resources within capacity (CPU ${s.edgeCpu.toFixed(1)}% <= ${edgeThr.cpu.toFixed(1)}%, RAM ${s.edgeRam.toFixed(1)}% <= ${edgeThr.ram.toFixed(1)}%, DISK ${s.edgeDisk.toFixed(1)}% <= ${edgeThr.disk.toFixed(1)}%) and network ${latencyNote}; running locally.`,
      };
    }
    if (cloudOk && latencyOk) {
      return {
        target: 'cloud',
        score,
        reason: `Edge resource overload (${edgeViolations.join(', ')}) and network ${latencyNote}; offloading to cloud.`,
      };
    }
    if (priority === 'high') {
      return {
        target: 'edge',
        score,
        reason: `Edge resource overload (${edgeViolations.join(', ')}) but cloud offload not viable (${latencyNote}); high-priority workload pinned to edge (best effort).`,
      };
    }
    return {
      target: 'queue',
      score,
      reason: `Edge resource overload (${edgeViolations.join(', ')}) and cloud offload not viable (${latencyNote}); ${priority}-priority workload queued for retry.`,
    };
  }

  // -- record builders ----------------------------------------------------
  private pickPriority(): Priority {
    const r = this.rng();
    if (r < 0.16) return 'high';
    if (r < 0.72) return 'medium';
    return 'low';
  }

  private makeRoutingRecord(t: number): RoutingRecord {
    const priority = this.pickPriority();
    const decision = this.decide(priority);
    const schedulerMs = Math.round(clamp(64 + (this.rng() - 0.5) * 44, 32, 190) + (this.rng() > 0.93 ? 420 : 0));

    let status: RoutingRecord['status'] = 'success';
    let actualTarget: Target | null = decision.target;
    let inferenceMs: number | null = null;
    let fallbackUsed = false;
    let fallbackReason: string | null = null;
    let detectionCount = 0;

    if (decision.target === 'queue') {
      status = 'queued';
      actualTarget = null;
    } else if (decision.target === 'error') {
      status = 'failed';
      actualTarget = null;
    } else if (decision.target === 'cloud' && priority === 'high' && this.rng() < 0.18) {
      // cloud -> edge fallback path (orchestrator/service.py).
      status = 'fallback';
      fallbackUsed = true;
      fallbackReason = 'Cloud inference failed (Upstream error 500); fallback to edge';
      inferenceMs = Math.round(clamp(112 + (this.rng() - 0.5) * 60, 84, 260));
      detectionCount = 1 + Math.floor(this.rng() * 3);
    } else if (decision.target === 'cloud') {
      inferenceMs = Math.round(clamp(196 + (this.rng() - 0.5) * 78, 140, 420));
      detectionCount = Math.floor(this.rng() * 5);
    } else {
      inferenceMs = Math.round(clamp(121 + (this.rng() - 0.5) * 62, 82, 268));
      detectionCount = Math.floor(this.rng() * 5);
    }

    if (decision.target === 'error' && this.rng() > 0.5) {
      status = 'failed';
    }

    const totalMs =
      inferenceMs === null
        ? schedulerMs + Math.round(this.rng() * 18)
        : schedulerMs + inferenceMs + Math.round(6 + this.rng() * 18);

    return {
      id: `wl-${Math.floor(this.rng() * 0xffffff).toString(16).padStart(6, '0')}`,
      t,
      priority,
      workloadType: this.rng() > 0.78 ? 'video_stream' : 'object_detection',
      selectedTarget: decision.target,
      actualTarget,
      score: decision.score,
      reason: decision.reason,
      status,
      schedulerMs,
      inferenceMs,
      totalMs,
      fallbackUsed,
      fallbackReason,
      detectionCount,
    };
  }

  private makeDetections(): InferenceClassCount[] {
    const count = 1 + Math.floor(this.rng() * 3);
    const used = new Set<string>();
    const classes: InferenceClassCount[] = [];
    for (let i = 0; i < count; i += 1) {
      const name = DETECTION_CLASSES[Math.floor(this.rng() * DETECTION_CLASSES.length)];
      if (used.has(name)) continue;
      used.add(name);
      classes.push({ name, count: 1 + Math.floor(this.rng() * 5), confidence: round1(0.42 + this.rng() * 0.53) });
    }
    return classes.sort((a, b) => b.count - a.count);
  }

  private makeInferenceRecord(t: number): InferenceRecord {
    // Mirror the recent decision mix so inference volume agrees with routing.
    const recent = this.routing.slice(-150).filter((r) => r.actualTarget !== null);
    const edgeShare = recent.length
      ? recent.filter((r) => r.actualTarget === 'edge').length / recent.length
      : 0.65;
    const destination: NodeRole = this.rng() < edgeShare ? 'edge' : 'cloud';
    const classes = this.makeDetections();
    const failed = this.rng() < 0.018;
    const inferenceMs =
      destination === 'edge'
        ? Math.round(clamp(120 + (this.rng() - 0.5) * 58, 80, 270))
        : Math.round(clamp(197 + (this.rng() - 0.5) * 80, 140, 430));

    return {
      id: `req-${Math.floor(this.rng() * 0xffffff).toString(16).padStart(6, '0')}`,
      t,
      destination,
      source: destination === 'edge' ? 'camera://edge-ec2-node' : 'upload://orchestrator',
      inferenceMs: failed ? 0 : inferenceMs,
      status: failed ? 'failed' : 'success',
      frameWidth: 640,
      frameHeight: 480,
      classes: failed ? [] : classes,
      detectionCount: failed ? 0 : classes.reduce((sum, item) => sum + item.count, 0),
    };
  }

  private makeLogEvent(t: number): SystemEvent {
    const r = this.rng();
    let level: LogLevel = 'info';
    if (r > 0.965) level = 'error';
    else if (r > 0.885) level = 'warn';
    else if (r < 0.12) level = 'debug';

    const decision = this.decide('medium');
    const sources: SystemEvent['source'][] = ['orchestrator', 'scheduler', 'edge', 'cloud', 'k3s', 'kubeedge'];
    const source = sources[Math.floor(this.rng() * sources.length)];
    const record = this.routing[Math.floor(this.rng() * this.routing.length)];
    const id = record?.id ?? 'wl-000000';

    const bank: Record<SystemEvent['source'], { level?: LogLevel; message: string }[]> = {
      orchestrator: [
        { message: `POST /orchestrate 200 - selected=${record?.selectedTarget ?? 'edge'} total=${record?.totalMs ?? 338}ms` },
        { message: `POST /orchestrate 503 - Inference failed: Upstream error 500 (workload ${id})`, level: 'error' },
        { level: 'warn', message: `Cloud inference failed for ${id}; high-priority fallback to edge engaged` },
        { message: 'GET /health 200 - service=orchestrator v0.1.0' },
        { level: 'debug', message: 'Scheduler round-trip measured; metrics cache warm' },
      ],
      scheduler: [
        { message: `decision ${id} -> ${decision.target} (score ${decision.score}) in ${64 + Math.floor(this.rng() * 40)}ms` },
        { level: 'warn', message: 'edge /metrics probe exceeded 1000 ms via ServiceBus; using cached snapshot' },
        { level: 'error', message: 'edge /metrics probe timed out after 2000 ms; decision returned QUEUE' },
        { level: 'debug', message: `policy=rule_based thresholds edge ${POLICY.edgeCpu}/${POLICY.edgeRam}/${POLICY.edgeDisk} cloud ${POLICY.cloudCpu}/${POLICY.cloudRam}/${POLICY.cloudDisk}` },
        { message: 'GET /health 200 - service=scheduler v0.1.0' },
      ],
      edge: [
        { message: `POST /detect 200 - ${1 + Math.floor(this.rng() * 4)} detections in ${110 + Math.floor(this.rng() * 90)}ms` },
        { level: 'debug', message: 'GET /metrics 200 - cpu sample window 1.0s (psutil)' },
        { message: 'YOLOv8n detector ready on device=cpu (yolov8n.pt 6.2 MB)' },
        { level: 'warn', message: 'camera_open=false - no capture source configured, model-only mode' },
        { message: 'ServiceBus target :8000 registered for rule metrics-route' },
      ],
      cloud: [
        { message: `POST /infer 200 - ${1 + Math.floor(this.rng() * 5)} detections in ${170 + Math.floor(this.rng() * 140)}ms` },
        { message: 'GET /health 200 - model_loaded=true' },
        { level: 'warn', message: 'POST /infer 500 - upstream detector busy; orchestrator may fall back to edge' },
        { level: 'debug', message: 'GET /metrics 200 - cpu sample window 1.0s (psutil)' },
      ],
      k3s: [
        { message: 'pod edge-node-fc54dc46-bs56z Ready (1/1) on edge-ec2-node' },
        { message: 'pod orchestrator-5d76f94584-lpx97 Ready (1/1) NodePort 30083' },
        { level: 'warn', message: 'pod yolo-batch-worker-7c9d4-x2k8p Pending - 0/1 (unschedulable: no node taint match)' },
        { level: 'error', message: 'pod edge-node-5cc9b74cb5-x4ptv Failed - back-off restarting failed container' },
        { message: 'service cloud-node ClusterIP 10.43.104.17:8001 endpoints ready' },
      ],
      kubeedge: [
        { message: 'edge node edge-ec2-node status Ready (EdgeReady)' },
        { message: 'rule detect-route forwarded /detect to edgecore :8000' },
        { level: 'warn', message: 'edgecore heartbeat delayed 4.2s for node edge-ec2-node' },
        { level: 'debug', message: 'cloudcore :9443 ServiceBus rest-source upstream healthy' },
        { level: 'error', message: 'rule video-route target unreachable - edgecore connection reset' },
      ],
    };

    const options = bank[source];
    const chosen = options[Math.floor(this.rng() * options.length)];
    return {
      id: `log-${t}-${Math.floor(this.rng() * 0xffff).toString(16)}`,
      t,
      level: chosen.level ?? level,
      source,
      message: chosen.message,
    };
  }

  // -- public reads -------------------------------------------------------
  private totals(): RequestTotals {
    const windowHours = 6;
    let edge = 0;
    let cloud = 0;
    let failed = 0;
    let queued = 0;
    const since = Date.now() - windowHours * 3600_000;
    for (const record of this.routing) {
      if (record.t < since) continue;
      if (record.actualTarget === 'edge') edge += 1;
      else if (record.actualTarget === 'cloud') cloud += 1;
      if (record.status === 'failed') failed += 1;
      if (record.status === 'queued') queued += 1;
    }
    return { total: edge + cloud + failed + queued, edge, cloud, failed, queued, windowHours };
  }

  private serviceHealth(service: string, extra: Partial<ServiceHealth> = {}): ServiceHealth {
    return {
      status: 'ok',
      service,
      version: '0.1.0',
      timestamp: String(Date.now() / 1000),
      ...extra,
    };
  }

  getOverview(): OverviewSnapshot {
    this.advance();
    const totals = this.totals();
    const since = Date.now() - totals.windowHours * 3600_000;
    const recent = this.routing.filter((r) => r.t >= since);
    const inferenceValues = recent.filter((r) => r.inferenceMs !== null).map((r) => r.inferenceMs as number);
    const schedulerValues = recent.map((r) => r.schedulerMs);

    const now = Date.now();
    const nodeStatus = (role: NodeRole) => ({
      role,
      reachable: true,
      health:
        role === 'edge'
          ? this.serviceHealth('edge-node', { model_loaded: true, camera_open: false, status: 'degraded' })
          : this.serviceHealth('cloud-node', { model_loaded: true }),
      metrics: this.metricsSnapshot(role),
      info: this.serviceInfo(role),
      probeLatencyMs: role === 'edge' ? 13.9 : 8.4,
      probedAt: now,
      error: null,
    });

    return {
      mode: 'demo',
      edge: nodeStatus('edge'),
      cloud: nodeStatus('cloud'),
      orchestrator: this.serviceHealth('orchestrator'),
      scheduler: this.serviceHealth('scheduler'),
      orchestratorInfo: {
        service: 'orchestrator',
        version: '0.1.0',
        uptime_sec: 1729240,
        endpoints: ['/health', '/orchestrate', '/docs'],
        edge_url: 'http://10.0.1.113:9443/edge-ec2-node/edgecloud',
        cloud_url: 'http://cloud-node.edgecloud.svc:8001',
        scheduler_url: 'http://scheduler.edgecloud.svc:8002',
      },
      totals,
      distribution: { edge: totals.edge, cloud: totals.cloud },
      avgInferenceMs: average(inferenceValues),
      avgSchedulerMs: average(schedulerValues),
      p95InferenceMs: percentile(inferenceValues, 95),
      latencySeries: [...this.latencySeries],
      resourceSeries: [...this.resourceSeries],
      recentActivity: [...this.routing].reverse().slice(0, 9),
    };
  }

  getRouting(): RoutingSnapshot {
    this.advance();
    const records = [...this.routing].reverse();
    const targets: Target[] = ['edge', 'cloud', 'queue', 'error'];
    const decisionCounts = targets.map((target) => ({
      target,
      count: this.routing.filter((r) => r.selectedTarget === target).length,
    }));
    const executed = this.routing.filter((r) => r.actualTarget !== null);
    const edge = executed.filter((r) => r.actualTarget === 'edge').length;
    return {
      records,
      decisionCounts,
      avgSchedulerMs: average(this.routing.map((r) => r.schedulerMs)),
      edgeSharePct: executed.length === 0 ? null : round1((edge / executed.length) * 100),
    };
  }

  getNode(role: NodeRole) {
    this.advance();
    const workloads = this.workloads().pods.filter((pod) =>
      role === 'edge' ? pod.node === 'edge-ec2-node' : pod.node !== 'edge-ec2-node',
    );
    const recentInference = [...this.inference].reverse().filter((r) => r.destination === role).slice(0, 40);
    return {
      role,
      reachable: true,
      health:
        role === 'edge'
          ? this.serviceHealth('edge-node', { model_loaded: true, camera_open: false, status: 'degraded' })
          : this.serviceHealth('cloud-node', { model_loaded: true }),
      metrics: this.metricsSnapshot(role),
      info: this.serviceInfo(role),
      probeLatencyMs: role === 'edge' ? 13.9 : 8.4,
      probedAt: Date.now(),
      error: null,
      connectivity:
        role === 'edge'
          ? {
              label: 'KubeEdge ServiceBus',
              baseUrl: 'http://10.0.1.113:9443/edge-ec2-node/edgecloud',
              transport: 'HTTP REST via CloudCore :9443 -> ServiceBus -> edgecore :8000',
              reachable: true,
              probeLatencyMs: 13.9,
              note: 'Rules detect-route / health-route / metrics-route forward to the edge-node pod.',
            }
          : {
              label: 'K3s ClusterIP',
              baseUrl: 'http://cloud-node.edgecloud.svc:8001',
              transport: 'HTTP REST, ClusterIP service in namespace edgecloud',
              reachable: true,
              probeLatencyMs: 8.4,
              note: 'Reached through the in-cluster service; not exposed outside the cluster.',
            },
      utilizationSeries: [...this.resourceSeries],
      inferenceSeries: [...this.latencySeries],
      workloads,
      recentInference,
    };
  }

  getWorkloads(): WorkloadInventory {
    this.advance();
    const pods = this.workloads();
    return pods;
  }

  getInference() {
    this.advance();
    const records = [...this.inference].reverse();
    const ok = this.inference.filter((r) => r.status === 'success');
    const edgeValues = ok.filter((r) => r.destination === 'edge').map((r) => r.inferenceMs);
    const cloudValues = ok.filter((r) => r.destination === 'cloud').map((r) => r.inferenceMs);
    const histogram = new Map<string, number>();
    for (const record of ok) {
      for (const item of record.classes) histogram.set(item.name, (histogram.get(item.name) ?? 0) + item.count);
    }
    return {
      records,
      total: this.inference.length,
      avgMs: average(ok.map((r) => r.inferenceMs)),
      p95Ms: percentile(ok.map((r) => r.inferenceMs), 95),
      edgeAvgMs: average(edgeValues),
      cloudAvgMs: average(cloudValues),
      classHistogram: [...histogram.entries()]
        .map(([name, value]) => ({ name, value }))
        .sort((a, b) => b.value - a.value),
      series: [...this.latencySeries],
    };
  }

  getLogs(): LogFeed {
    this.advance();
    const events = [...this.logs].reverse();
    const counts: Record<LogLevel, number> = { debug: 0, info: 0, warn: 0, error: 0 };
    for (const event of events) counts[event.level] += 1;
    return { events, counts };
  }

  probeDecision(): Decision {
    this.advance();
    const decision = this.decide('medium');
    return {
      workload_id: `wl-demo-${Date.now().toString(36)}`,
      target: decision.target,
      score: decision.score,
      reason: decision.reason,
      priority: 'medium',
      timestamp: new Date().toISOString(),
    };
  }

  // -- static-ish inventories --------------------------------------------
  private metricsSnapshot(role: NodeRole): SystemMetrics {
    const s = this.state;
    const meta = NODE_META[role];
    const cpu = role === 'edge' ? s.edgeCpu : s.cloudCpu;
    const ram = role === 'edge' ? s.edgeRam : s.cloudRam;
    const disk = role === 'edge' ? s.edgeDisk : s.cloudDisk;
    return {
      cpu_percent: round1(cpu),
      ram_percent: round1(ram),
      ram_used_gb: round1((ram / 100) * meta.ramTotalGb),
      ram_total_gb: meta.ramTotalGb,
      disk_percent: round1(disk),
      disk_used_gb: round1((disk / 100) * meta.diskTotalGb),
      disk_total_gb: meta.diskTotalGb,
      timestamp: new Date().toISOString(),
    };
  }

  private serviceInfo(role: NodeRole): ServiceInfo {
    return {
      service: role === 'edge' ? 'edge-node' : 'cloud-node',
      version: '0.1.0',
      uptime_sec: role === 'edge' ? 982144 : 1729240,
      endpoints: role === 'edge' ? ['/health', '/metrics', '/detect', '/detect/video', '/docs'] : ['/health', '/metrics', '/infer', '/docs'],
    };
  }

  private workloads(): WorkloadInventory {
    const pods: WorkloadItem[] = [
      {
        name: 'orchestrator-5d76f94584-lpx97',
        namespace: 'edgecloud',
        role: 'orchestrator',
        status: 'Running',
        ready: '1/1',
        restarts: 0,
        node: 'ip-10-0-1-113',
        image: 'edgecloud/orchestrator:latest',
        age: '41d',
        cpu: '38m',
        memory: '112Mi',
      },
      {
        name: 'scheduler-6dcbffbcdb-2kktm',
        namespace: 'edgecloud',
        role: 'scheduler',
        status: 'Running',
        ready: '1/1',
        restarts: 0,
        node: 'ip-10-0-1-113',
        image: 'edgecloud/scheduler:latest',
        age: '41d',
        cpu: '21m',
        memory: '96Mi',
      },
      {
        name: 'cloud-node-6d9f488769-c5pph',
        namespace: 'edgecloud',
        role: 'cloud',
        status: 'Running',
        ready: '1/1',
        restarts: 0,
        node: 'ip-10-0-1-113',
        image: 'edgecloud/cloud-node:latest',
        age: '41d',
        cpu: '214m',
        memory: '642Mi',
      },
      {
        name: 'edge-node-fc54dc46-bs56z',
        namespace: 'edgecloud',
        role: 'edge',
        status: 'Running',
        ready: '1/1',
        restarts: 0,
        node: 'edge-ec2-node',
        image: 'edgecloud/edge-node:latest',
        age: '41d',
        cpu: '186m',
        memory: '584Mi',
      },
      {
        name: 'yolo-batch-worker-7c9d4-x2k8p',
        namespace: 'edgecloud',
        role: 'batch',
        status: 'Pending',
        ready: '0/1',
        restarts: 0,
        node: 'edge-ec2-node',
        image: 'edgecloud/edge-node:latest',
        age: '4m',
        cpu: '—',
        memory: '—',
      },
      {
        name: 'video-stream-replay-59b8-t7wq2',
        namespace: 'edgecloud',
        role: 'stream',
        status: 'Running',
        ready: '1/1',
        restarts: 3,
        node: 'ip-10-0-1-113',
        image: 'edgecloud/cloud-node:latest',
        age: '6h',
        cpu: '96m',
        memory: '318Mi',
      },
      {
        name: 'edge-node-5cc9b74cb5-x4ptv',
        namespace: 'edgecloud',
        role: 'edge-legacy',
        status: 'Failed',
        ready: '0/1',
        restarts: 12,
        node: 'wsl2-edge-node',
        image: 'edgecloud/edge-node:latest',
        age: '52d',
        cpu: '—',
        memory: '—',
      },
    ];

    const services: ServiceItem[] = [
      { name: 'orchestrator', namespace: 'edgecloud', type: 'NodePort', port: 8003, nodePort: 30083, selector: 'app=orchestrator', endpoints: 1 },
      { name: 'scheduler', namespace: 'edgecloud', type: 'ClusterIP', port: 8002, nodePort: null, selector: 'app=scheduler', endpoints: 1 },
      { name: 'cloud-node', namespace: 'edgecloud', type: 'ClusterIP', port: 8001, nodePort: null, selector: 'app=cloud-node', endpoints: 1 },
      { name: 'edge-node', namespace: 'edgecloud', type: 'ClusterIP', port: 8000, nodePort: null, selector: 'app=edge-node', endpoints: 1 },
    ];

    const nodes: ClusterNode[] = [
      { name: 'ip-10-0-1-113', status: 'Ready', role: 'control-plane', version: 'v1.32.13+k3s1', internalIp: '10.0.1.113', pods: 3 },
      { name: 'edge-ec2-node', status: 'Ready', role: 'agent,edge', version: 'v1.32.10-kubeedge-v1.23.1-dirty', internalIp: '10.0.1.123', pods: 2 },
      { name: 'wsl2-edge-node', status: 'NotReady', role: 'agent (cordoned)', version: 'v1.32.1+k3s1', internalIp: '192.168.64.3', pods: 1 },
    ];

    const running = pods.filter((p) => p.status === 'Running').length;
    const pending = pods.filter((p) => p.status === 'Pending').length;
    const failed = pods.filter((p) => p.status === 'Failed').length;
    const restarts = pods.reduce((sum, p) => sum + p.restarts, 0);

    return { summary: { running, pending, failed, restarts }, pods, services, nodes };
  }
}

export const mockStore = new MockStore();

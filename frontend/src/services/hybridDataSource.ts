/**
 * Hybrid data source used by live mode.
 *
 * - Health, metrics, service info and decision probes come from the real
 *   FastAPI services (edge :8000, cloud :8001, scheduler :8002,
 *   orchestrator :8003).
 * - Views the backend cannot serve yet (routing history, inference history,
 *   workloads, logs, time series) fall back to the mock service so the
 *   dashboard stays fully populated. Those panels are tagged with the
 *   "SAMPLE DATA" chip by the UI, so nothing is presented as live.
 *
 * Only the known sample-only keys are ever filled from the fallback; live
 * health/metrics fields are never replaced, so a failed probe still shows as
 * a failed probe.
 */
import type {
  DataSource,
  DataSourceMode,
  Decision,
  DecisionProbeInput,
  InferenceFeed,
  LogFeed,
  NodeDetail,
  NodeRole,
  OverviewSnapshot,
  RoutingSnapshot,
  WorkloadInventory,
} from '../types';
import { DemoDataSource } from './mock/mockDataSource';
import { LiveDataSource } from './liveDataSource';

const OVERVIEW_SAMPLE_KEYS = [
  'totals',
  'distribution',
  'avgInferenceMs',
  'avgSchedulerMs',
  'p95InferenceMs',
  'latencySeries',
  'resourceSeries',
  'recentActivity',
] as const;

const NODE_SAMPLE_KEYS = [
  'utilizationSeries',
  'inferenceSeries',
  'workloads',
  'recentInference',
] as const;

function fillNulls<T, K extends keyof T>(target: T, fallback: T, keys: readonly K[]): T {
  const out = { ...target };
  for (const key of keys) {
    if (out[key] === null || out[key] === undefined) {
      (out as Record<string, unknown>)[key as string] = fallback[key];
    }
  }
  return out;
}

export class HybridDataSource implements DataSource {
  readonly mode: DataSourceMode = 'live';
  readonly label = 'LIVE BACKEND';
  readonly hint =
    'Health, metrics and decision probes come from the running FastAPI services; views without an endpoint use clearly-labelled sample data.';

  private readonly live = new LiveDataSource();
  private readonly demo = new DemoDataSource();

  async getOverview(): Promise<OverviewSnapshot> {
    const [liveSnapshot, demoSnapshot] = await Promise.all([
      this.live.getOverview(),
      this.demo.getOverview(),
    ]);
    return fillNulls(liveSnapshot, demoSnapshot, OVERVIEW_SAMPLE_KEYS);
  }

  async getRouting(): Promise<RoutingSnapshot | null> {
    return (await this.live.getRouting()) ?? (await this.demo.getRouting());
  }

  async getNode(role: NodeRole): Promise<NodeDetail> {
    const [liveNode, demoNode] = await Promise.all([this.live.getNode(role), this.demo.getNode(role)]);
    return fillNulls(liveNode, demoNode, NODE_SAMPLE_KEYS);
  }

  async getWorkloads(): Promise<WorkloadInventory | null> {
    return (await this.live.getWorkloads()) ?? (await this.demo.getWorkloads());
  }

  async getInference(): Promise<InferenceFeed | null> {
    return (await this.live.getInference()) ?? (await this.demo.getInference());
  }

  async getLogs(): Promise<LogFeed | null> {
    return (await this.live.getLogs()) ?? (await this.demo.getLogs());
  }

  /** Always the real POST /decision against the running scheduler. */
  async probeDecision(input?: DecisionProbeInput): Promise<Decision> {
    return this.live.probeDecision(input);
  }
}

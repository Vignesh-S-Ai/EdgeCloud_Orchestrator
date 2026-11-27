/**
 * Live data source - talks to the real FastAPI services only.
 *
 * Covered endpoints:
 *   orchestrator GET /health          -> service health
 *   scheduler    GET /health          -> service health
 *   edge         GET /health, /metrics, /
 *   cloud        GET /health, /metrics, /
 *   scheduler    POST /decision       -> "decision probe" widget
 *
 * Views with no backing endpoint (routing history, workloads, inference
 * history, logs, time series) return `null` so the UI can render an explicit
 * "no live endpoint" state instead of fabricated metrics.
 */
import { env } from '../config/env';
import type {
  DataSource,
  DataSourceMode,
  Decision,
  DecisionProbeInput,
  InferenceFeed,
  LogFeed,
  NodeDetail,
  NodeRole,
  NodeStatus,
  OverviewSnapshot,
  RoutingSnapshot,
  ServiceInfo,
  WorkloadInventory,
} from '../types';
import { cloudApi, edgeApi, orchestratorApi, schedulerApi, timedGet } from './api';

async function fetchNodeStatus(role: NodeRole): Promise<NodeStatus> {
  const api = role === 'edge' ? edgeApi : cloudApi;
  const [health, metrics] = await Promise.all([api.probeHealth(), api.probeMetrics()]);
  return {
    role,
    reachable: health.ok,
    health: health.data,
    metrics: metrics.data,
    info: null,
    probeLatencyMs: health.latencyMs,
    probedAt: Date.now(),
    error: health.error ?? metrics.error ?? null,
  };
}

export class LiveDataSource implements DataSource {
  readonly mode: DataSourceMode = 'live';
  readonly label = 'LIVE BACKEND';
  readonly hint = 'Reading real /health and /metrics endpoints from the FastAPI services.';

  async getOverview(): Promise<OverviewSnapshot> {
    const [edge, cloud, orchestrator, scheduler, orchestratorInfo] = await Promise.all([
      fetchNodeStatus('edge'),
      fetchNodeStatus('cloud'),
      orchestratorApi.probe(),
      schedulerApi.probe(),
      timedGet<ServiceInfo>(`${env.orchestratorUrl}/`),
    ]);

    return {
      mode: 'live',
      edge,
      cloud,
      orchestrator: orchestrator.data,
      scheduler: scheduler.data,
      orchestratorInfo: orchestratorInfo.data,
      totals: null,
      distribution: null,
      avgInferenceMs: null,
      avgSchedulerMs: null,
      p95InferenceMs: null,
      latencySeries: null,
      resourceSeries: null,
      recentActivity: null,
    };
  }

  async getRouting(): Promise<RoutingSnapshot | null> {
    return null;
  }

  async getNode(role: NodeRole): Promise<NodeDetail> {
    const [status, info] = await Promise.all([
      fetchNodeStatus(role),
      timedGet<ServiceInfo>(`${role === 'edge' ? env.edgeUrl : env.cloudUrl}/`),
    ]);

    const baseUrl = role === 'edge' ? env.edgeUrl : env.cloudUrl;
    const isServiceBus = /:9443/.test(baseUrl) || baseUrl.includes('/edge-ec2-node');

    return {
      ...status,
      info: info.data ?? status.info,
      connectivity: {
        label: isServiceBus ? 'KubeEdge ServiceBus' : 'Direct HTTP',
        baseUrl,
        transport: isServiceBus
          ? 'HTTP REST through CloudCore :9443 -> ServiceBus rules -> edgecore :8000'
          : 'HTTP REST directly against the service base URL',
        reachable: status.reachable,
        probeLatencyMs: status.probeLatencyMs,
        note: status.reachable ? 'Health probe succeeded.' : (status.error ?? 'Unreachable from this browser.'),
      },
      utilizationSeries: null,
      inferenceSeries: null,
      workloads: null,
      recentInference: null,
    };
  }

  async getWorkloads(): Promise<WorkloadInventory | null> {
    return null;
  }

  async getInference(): Promise<InferenceFeed | null> {
    return null;
  }

  async getLogs(): Promise<LogFeed | null> {
    return null;
  }

  /** Real POST /decision against the running scheduler. */
  async probeDecision(input?: DecisionProbeInput): Promise<Decision> {
    return schedulerApi.decision({
      edgeUrl: input?.edgeUrl ?? env.edgeUrl,
      cloudUrl: input?.cloudUrl ?? env.cloudUrl,
    });
  }
}

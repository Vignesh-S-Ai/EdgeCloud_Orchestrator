/**
 * Typed client for the four real FastAPI services.
 *
 * Only endpoints that exist in the repository are called:
 *   orchestrator: GET / , GET /health
 *   scheduler:   GET / , GET /health , POST /decision
 *   edge:        GET / , GET /health , GET /metrics
 *   cloud:       GET / , GET /health , GET /metrics
 */
import { env } from '../config/env';
import type { Decision, DecisionProbeInput, ServiceHealth, ServiceInfo, SystemMetrics } from '../types';
import { getJson, postJson, type RequestOptions } from './http';

export interface ProbeResult<T> {
  ok: boolean;
  data: T | null;
  latencyMs: number | null;
  error: string | null;
  url: string;
}

/** GET with client-side round-trip timing - powers the connectivity cards. */
export async function timedGet<T>(url: string, options?: RequestOptions): Promise<ProbeResult<T>> {
  const started = performance.now();
  try {
    const data = await getJson<T>(url, options);
    return { ok: true, data, latencyMs: round(performance.now() - started), error: null, url };
  } catch (error) {
    return { ok: false, data: null, latencyMs: null, error: (error as Error).message, url };
  }
}

export const orchestratorApi = {
  base: () => env.orchestratorUrl,
  info: (o?: RequestOptions) => getJson<ServiceInfo>(`${env.orchestratorUrl}/`, o),
  health: (o?: RequestOptions) => getJson<ServiceHealth>(`${env.orchestratorUrl}/health`, o),
  probe: (o?: RequestOptions) => timedGet<ServiceHealth>(`${env.orchestratorUrl}/health`, o),
};

export const schedulerApi = {
  base: () => env.schedulerUrl,
  info: (o?: RequestOptions) => getJson<ServiceInfo>(`${env.schedulerUrl}/`, o),
  health: (o?: RequestOptions) => getJson<ServiceHealth>(`${env.schedulerUrl}/health`, o),
  probe: (o?: RequestOptions) => timedGet<ServiceHealth>(`${env.schedulerUrl}/health`, o),
  /**
   * POST /decision - existing endpoint. With edge_url/cloud_url the scheduler
   * fetches live metrics itself and returns a real placement decision.
   */
  decision: (input: DecisionProbeInput, o?: RequestOptions) =>
    postJson<Decision>(
      `${env.schedulerUrl}/decision`,
      {
        workload: {
          workload_id: `dash-${Date.now().toString(36)}`,
          priority: 'medium',
          workload_type: 'object_detection',
          latency_requirement_ms: 200,
        },
        ...(input.edgeUrl && input.cloudUrl ? { edge_url: input.edgeUrl, cloud_url: input.cloudUrl } : {}),
      },
      o,
    ),
};

export const edgeApi = {
  base: () => env.edgeUrl,
  info: (o?: RequestOptions) => getJson<ServiceInfo>(`${env.edgeUrl}/`, o),
  health: (o?: RequestOptions) => getJson<ServiceHealth>(`${env.edgeUrl}/health`, o),
  metrics: (o?: RequestOptions) => getJson<SystemMetrics>(`${env.edgeUrl}/metrics`, o),
  probeHealth: (o?: RequestOptions) => timedGet<ServiceHealth>(`${env.edgeUrl}/health`, o),
  probeMetrics: (o?: RequestOptions) => timedGet<SystemMetrics>(`${env.edgeUrl}/metrics`, o),
};

export const cloudApi = {
  base: () => env.cloudUrl,
  info: (o?: RequestOptions) => getJson<ServiceInfo>(`${env.cloudUrl}/`, o),
  health: (o?: RequestOptions) => getJson<ServiceHealth>(`${env.cloudUrl}/health`, o),
  metrics: (o?: RequestOptions) => getJson<SystemMetrics>(`${env.cloudUrl}/metrics`, o),
  probeHealth: (o?: RequestOptions) => timedGet<ServiceHealth>(`${env.cloudUrl}/health`, o),
  probeMetrics: (o?: RequestOptions) => timedGet<SystemMetrics>(`${env.cloudUrl}/metrics`, o),
};

function round(value: number): number {
  return Math.round(value * 10) / 10;
}

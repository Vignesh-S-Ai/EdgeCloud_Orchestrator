import type { ReactNode } from 'react';
import { Activity, Cloud, Cpu, Gauge, HardDrive, MemoryStick, Radio, Server, ShieldCheck } from 'lucide-react';
import { LatencyTrendChart } from '../components/charts/LatencyTrendChart';
import { UtilizationChart } from '../components/charts/UtilizationChart';
import { Panel } from '../components/ui/Panel';
import { MetricCard, type MetricTone } from '../components/ui/MetricCard';
import { Gauge as GaugeChart } from '../components/ui/Gauge';
import { StatusBadge, toneForStatus } from '../components/ui/StatusBadge';
import { EmptyState, ErrorState, LoadingGrid, NoLiveData } from '../components/ui/States';
import { SourceChips } from '../components/ui/SourceChips';
import { Mono, TableShell, Td, Th, Tr } from '../components/ui/Table';
import { useData } from '../context/DataSourceContext';
import { useAsync } from '../hooks/useAsync';
import { formatGb, formatMs, formatPct, formatUptime, timeAgo } from '../lib/format';
import type { NodeRole } from '../types';

export function NodePage({ role }: { role: NodeRole }) {
  const { source, refreshMs, setMode } = useData();
  const { data, loading, error, reload } = useAsync(() => source.getNode(role), [source, role], {
    intervalMs: refreshMs,
  });

  if (loading && !data) return <LoadingGrid count={6} />;
  if (error && !data) return <ErrorState description={error} onRetry={reload} />;
  if (!data) return null;

  const { health, metrics, info, connectivity, utilizationSeries, inferenceSeries, workloads, recentInference } = data;
  const edge = role === 'edge';
  const tone: MetricTone = data.reachable ? (toneForStatus(health?.status) as MetricTone) : 'bad';

  const edgeLatency = inferenceSeries ? averageMs(inferenceSeries.map((p) => p.edgeMs)) : null;
  const cloudLatency = inferenceSeries ? averageMs(inferenceSeries.map((p) => p.cloudMs)) : null;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <StatusBadge
          label={health?.status ?? (data.reachable ? 'unknown' : 'unreachable')}
          tone={toneForStatus(health?.status)}
          pulse={data.reachable}
        />
        <span className="font-mono text-[11px] text-ink-dim">{connectivity.baseUrl}</span>
        <span className="text-[11px] text-ink-dim">· probed {timeAgo(data.probedAt)}</span>
        <SourceChips views={['health', 'metrics', 'serviceInfo', 'series', 'workloads', 'inference']} />
      </div>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          label={`${edge ? 'Edge' : 'Cloud'} health`}
          icon={edge ? Cpu : Cloud}
          tone={tone}
          value={health?.status ?? (data.reachable ? 'unknown' : 'unreachable')}
          sub={
            health
              ? `service ${health.service} v${health.version}`
              : (data.error ?? 'No response from /health')
          }
          footer={`Probe ${data.probeLatencyMs !== null ? `${data.probeLatencyMs} ms` : '—'} · ${connectivity.label}`}
        />
        <MetricCard
          label="CPU utilisation"
          icon={Gauge}
          tone="brand"
          value={metrics ? formatPct(metrics.cpu_percent) : '—'}
          sub="GET /metrics (psutil, 1s sample window)"
          footer={metrics ? `sampled ${timeAgo(Date.parse(metrics.timestamp))}` : 'metrics unavailable'}
        />
        <MetricCard
          label="RAM utilisation"
          icon={MemoryStick}
          tone="warn"
          value={metrics ? formatPct(metrics.ram_percent) : '—'}
          sub={metrics ? `${formatGb(metrics.ram_used_gb)} of ${formatGb(metrics.ram_total_gb)}` : 'metrics unavailable'}
          footer={edge ? 'Threshold 70% (+5% medium bias)' : 'Threshold 80%'}
        />
        <MetricCard
          label="Disk utilisation"
          icon={HardDrive}
          tone={metrics && metrics.disk_percent > 85 ? 'bad' : 'ok'}
          value={metrics ? formatPct(metrics.disk_percent) : '—'}
          sub={metrics ? `${formatGb(metrics.disk_used_gb)} of ${formatGb(metrics.disk_total_gb)}` : 'metrics unavailable'}
          footer={edge ? 'Threshold 85%' : 'Threshold 90%'}
        />
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        <Panel title="Resource utilisation" subtitle="Current snapshot from GET /metrics">
          {metrics ? (
            <div className="flex flex-wrap items-start justify-around gap-4">
              <GaugeChart label="CPU" value={metrics.cpu_percent} sub={`${metrics.cpu_percent.toFixed(1)}% of 100%`} />
              <GaugeChart
                label="RAM"
                value={metrics.ram_percent}
                sub={`${formatGb(metrics.ram_used_gb)} / ${formatGb(metrics.ram_total_gb)}`}
              />
              <GaugeChart
                label="DISK"
                value={metrics.disk_percent}
                warnAt={80}
                badAt={edge ? 85 : 90}
                sub={`${formatGb(metrics.disk_used_gb)} / ${formatGb(metrics.disk_total_gb)}`}
              />
            </div>
          ) : (
            <EmptyState
              title="Metrics unavailable"
              description={data.error ?? 'The node did not return a /metrics snapshot. Check that the service is running and reachable from this browser.'}
            />
          )}
        </Panel>

        <Panel title="Connectivity" subtitle="How this browser reaches the node">
          <dl className="space-y-3 text-xs">
            <Row label="Transport" value={connectivity.transport} />
            <Row label="Base URL" value={connectivity.baseUrl} mono />
            <Row label="Probe latency" value={connectivity.probeLatencyMs !== null ? `${connectivity.probeLatencyMs} ms` : '—'} mono />
            <Row
              label="State"
              value={
                <StatusBadge
                  label={connectivity.reachable ? 'reachable' : 'unreachable'}
                  tone={connectivity.reachable ? 'ok' : 'bad'}
                />
              }
            />
          </dl>
          <p className="mt-3 border-t border-line pt-3 text-[11px] leading-relaxed text-ink-muted">{connectivity.note}</p>
          <div className="mt-3 flex items-start gap-2 rounded-lg border border-line bg-raised/50 px-3 py-2 text-[11px] text-ink-dim">
            <Radio className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            <span>
              {edge
                ? 'Edge requests travel through KubeEdge ServiceBus rules (detect-route, health-route, metrics-route).'
                : 'Cloud requests use the in-cluster ClusterIP service on port 8001.'}
            </span>
          </div>
        </Panel>

        <Panel title="Service health" subtitle="GET /health">
          <dl className="space-y-3 text-xs">
            <Row label="Status" value={<StatusBadge label={health?.status ?? 'unknown'} tone={toneForStatus(health?.status)} />} />
            <Row label="Model" value={health ? (health.model_loaded ? 'loaded (yolov8n.pt)' : 'not loaded') : '—'} />
            {edge && <Row label="Optional camera" value={health ? (health.camera_status === 'connected' || health.camera_open ? 'connected' : 'not connected · inference unaffected') : '—'} />}
            <Row label="Version" value={health?.version ?? info?.version ?? '—'} mono />
            <Row label="Uptime" value={formatUptime(info?.uptime_sec)} mono />
            <Row label="Endpoints" value={(info?.endpoints ?? []).join(', ') || '—'} />
          </dl>
        </Panel>
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <Panel title="Inference latency" subtitle="Rolling window by execution destination">
          {inferenceSeries ? (
            <LatencyTrendChart data={inferenceSeries} height={220} />
          ) : (
            <NoLiveData onEnableDemo={() => setMode('demo')} />
          )}
          <div className="mt-3 grid grid-cols-3 gap-2 border-t border-line pt-3 text-center">
            <MiniStat label={`${edge ? 'Edge' : 'Cloud'} avg`} value={formatMs(edge ? edgeLatency : cloudLatency)} />
            <MiniStat label="Edge avg" value={formatMs(edgeLatency)} />
            <MiniStat label="Cloud avg" value={formatMs(cloudLatency)} />
          </div>
        </Panel>

        <Panel title="Utilisation history" subtitle="CPU, RAM and disk over time">
          {utilizationSeries ? (
            <UtilizationChart data={utilizationSeries} height={220} />
          ) : (
            <NoLiveData onEnableDemo={() => setMode('demo')} />
          )}
        </Panel>
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        <Panel
          className="xl:col-span-2"
          title={`Workloads on this ${edge ? 'edge' : 'cloud'} node`}
          subtitle="Pods scheduled on the node"
          actions={<Server className="h-3.5 w-3.5 text-ink-dim" />}
          bodyClassName="p-0"
        >
          {workloads && workloads.length > 0 ? (
            <TableShell>
              <thead>
                <tr>
                  <Th>Pod</Th>
                  <Th>Status</Th>
                  <Th>Ready</Th>
                  <Th className="text-right">Restarts</Th>
                  <Th className="text-right">CPU</Th>
                  <Th className="text-right">Memory</Th>
                </tr>
              </thead>
              <tbody>
                {workloads.map((pod) => (
                  <Tr key={pod.name}>
                    <Td>
                      <Mono className="text-ink">{pod.name}</Mono>
                      <div className="text-[10px] text-ink-dim">
                        {pod.namespace} · {pod.image}
                      </div>
                    </Td>
                    <Td>
                      <StatusBadge label={pod.status} tone={toneForStatus(pod.status)} />
                    </Td>
                    <Td>
                      <Mono>{pod.ready}</Mono>
                    </Td>
                    <Td className="text-right">
                      <Mono className={pod.restarts > 0 ? 'text-warn' : 'text-ink-muted'}>{pod.restarts}</Mono>
                    </Td>
                    <Td className="text-right">
                      <Mono>{pod.cpu}</Mono>
                    </Td>
                    <Td className="text-right">
                      <Mono>{pod.memory}</Mono>
                    </Td>
                  </Tr>
                ))}
              </tbody>
            </TableShell>
          ) : (
            <div className="p-5">
              <NoLiveData onEnableDemo={() => setMode('demo')} />
            </div>
          )}
        </Panel>

        <Panel title="Recent inference" subtitle="Latest executions handled by this node">
          {recentInference && recentInference.length > 0 ? (
            <ul className="space-y-2">
              {recentInference.slice(0, 8).map((record) => (
                <li key={record.id} className="flex items-center justify-between gap-3 rounded-lg border border-line bg-raised/50 px-3 py-2">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <StatusBadge label={record.status} tone={toneForStatus(record.status)} />
                      <Mono className="text-ink-dim">{record.id}</Mono>
                    </div>
                    <div className="mt-1 truncate text-[10px] text-ink-dim">
                      {record.detectionCount} detection{record.detectionCount === 1 ? '' : 's'}
                      {record.classes.length ? ` · ${record.classes.map((c) => c.name).join(', ')}` : ''}
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="text-sm font-semibold tabular-nums text-ink">{formatMs(record.inferenceMs)}</div>
                    <div className="text-[10px] text-ink-dim">{timeAgo(record.t)}</div>
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <NoLiveData onEnableDemo={() => setMode('demo')} />
          )}
        </Panel>
      </div>

      <div className="flex items-start gap-2 rounded-lg border border-line bg-panel px-4 py-3 text-[11px] text-ink-dim">
        <ShieldCheck className="mt-0.5 h-3.5 w-3.5 shrink-0 text-ok" />
        <span>
          Health, metrics and connectivity above are read from live endpoints{' '}
          <span className="font-mono text-ink-muted">(/health, /metrics, /)</span> when the dashboard is in Live mode;
          historical series and pod lists fall back to clearly-labelled <span className="font-mono">SAMPLE DATA</span>{' '}
          because those backend endpoints do not exist yet.
        </span>
        <Activity className="ml-auto mt-0.5 h-3.5 w-3.5 shrink-0" />
      </div>
    </div>
  );
}

function Row({ label, value, mono = false }: { label: string; value: ReactNode; mono?: boolean }) {
  return (
    <div className="flex items-start justify-between gap-3 border-b border-line/70 pb-2 last:border-0 last:pb-0">
      <dt className="shrink-0 text-[11px] uppercase tracking-[0.09em] text-ink-dim">{label}</dt>
      <dd className={`min-w-0 text-right ${mono ? 'font-mono text-[11px] text-ink-muted' : 'text-ink-muted'}`}>{value}</dd>
    </div>
  );
}

function MiniStat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-[0.09em] text-ink-dim">{label}</div>
      <div className="mt-0.5 text-sm font-semibold tabular-nums text-ink">{value}</div>
    </div>
  );
}

function averageMs(values: number[]): number | null {
  if (values.length === 0) return null;
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

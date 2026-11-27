import { Activity, ArrowDownUp, Brain, Cloud, Cpu, Network, Server } from 'lucide-react';
import { Gauge } from '../components/ui/Gauge';
import { MetricCard } from '../components/ui/MetricCard';
import { Panel } from '../components/ui/Panel';
import { StatusBadge, toneForStatus } from '../components/ui/StatusBadge';
import { ErrorState, LoadingGrid } from '../components/ui/States';
import { useData } from '../context/DataSourceContext';
import { useAsync } from '../hooks/useAsync';
import { timeAgo } from '../lib/format';
import type { NodeStatus, ServiceHealth } from '../types';

export function OverviewPage() {
  const { source, refreshMs } = useData();
  const { data, loading, error, reload, updated, refreshing } = useAsync(
    () => source.getOverview(),
    [source],
    { intervalMs: refreshMs },
  );

  if (loading && !data) return <LoadingGrid count={6} />;
  if (error && !data) return <ErrorState description={error} onRetry={reload} />;
  if (!data) return null;

  const liveMode = source.mode === 'live';

  return (
    <div className="space-y-5">
      <section className="relative overflow-hidden rounded-2xl border border-line bg-panel p-5 shadow-card sm:p-7">
        <div className="pointer-events-none absolute -right-16 -top-24 h-64 w-64 rounded-full bg-brand/10 blur-3xl" />
        <div className="relative flex flex-wrap items-start justify-between gap-4">
          <div className="max-w-2xl">
            <div className="mb-3 inline-flex items-center gap-2 rounded-full border border-ok/30 bg-ok/10 px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.14em] text-ok">
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-ok" />
              {liveMode ? 'Connected to live AWS services' : 'Demo data mode'}
            </div>
            <h2 className="text-2xl font-semibold tracking-tight text-ink sm:text-3xl">Edge-Cloud Orchestration</h2>
            <p className="mt-2 max-w-xl text-sm leading-relaxed text-ink-muted">
              A live operational view of workload placement, edge and cloud resources, and service health across the CLOUD-13 deployment.
            </p>
          </div>
          <div className="rounded-xl border border-line bg-raised/70 px-4 py-3">
            <div className="flex items-center gap-2 text-xs text-ink-dim">
              <Activity className="h-3.5 w-3.5" /> Dashboard refresh
            </div>
            <div className="mt-1 text-lg font-semibold tabular-nums text-ink">{Math.round(refreshMs / 1000)} sec</div>
            <div className="mt-1 text-[10px] text-ink-dim">
              {refreshing ? 'Refreshing live snapshot…' : updated ? `Updated ${new Date(updated).toLocaleTimeString()}` : 'Waiting for first snapshot'}
            </div>
          </div>
        </div>
        <div className="relative mt-6 grid gap-2 md:grid-cols-[1fr_auto_1fr_auto_1fr] md:items-center">
          <ArchitectureNode icon={Cpu} title="Edge node" subtitle="KubeEdge · remote inference" status={data.edge.health?.status ?? 'unreachable'} />
          <div className="hidden items-center justify-center text-brand md:flex"><ArrowDownUp className="h-5 w-5" /></div>
          <ArchitectureNode icon={Network} title="Orchestrator" subtitle="Placement + inference routing" status={data.orchestrator?.status ?? 'unreachable'} />
          <div className="hidden items-center justify-center text-brand md:flex"><ArrowDownUp className="h-5 w-5" /></div>
          <ArchitectureNode icon={Cloud} title="Cloud node" subtitle="Cloud inference service" status={data.cloud.health?.status ?? 'unreachable'} />
        </div>
        <div className="relative mt-3 flex items-center justify-center gap-2 text-[10px] text-ink-dim">
          <Brain className="h-3.5 w-3.5 text-violet" /> Scheduler evaluates live node and network metrics before placement
        </div>
      </section>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <ServiceCard label="Orchestrator" icon={Network} health={data.orchestrator} detail="POST /orchestrate" />
        <ServiceCard label="Scheduler" icon={Brain} health={data.scheduler} detail="POST /decision" />
        <NodeHealthCard label="Edge node" icon={Cpu} node={data.edge} />
        <NodeHealthCard label="Cloud node" icon={Cloud} node={data.cloud} />
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <ResourcePanel title="Edge node resources" subtitle="Live snapshot via KubeEdge ServiceBus" node={data.edge} />
        <ResourcePanel title="Cloud node resources" subtitle="Live snapshot from the cloud inference service" node={data.cloud} />
      </div>

      <Panel title="Deployment connectivity" subtitle="Endpoints currently configured in this browser session">
        <div className="grid gap-3 sm:grid-cols-2">
          <Endpoint label="Orchestrator" value={data.orchestratorInfo?.service ? 'AWS SSM tunnel · port 30083' : 'AWS SSM tunnel · port 30083'} state={data.orchestrator?.status ?? 'unreachable'} />
          <Endpoint label="Scheduler" value="AWS SSM + K3s port-forward · 18002" state={data.scheduler?.status ?? 'unreachable'} />
          <Endpoint label="Edge metrics" value="AWS SSM + KubeEdge ServiceBus · 9443" state={data.edge.reachable ? 'reachable' : 'unreachable'} />
          <Endpoint label="Cloud metrics" value="AWS SSM + K3s port-forward · 18001" state={data.cloud.reachable ? 'reachable' : 'unreachable'} />
        </div>
        <div className="mt-4 rounded-lg border border-info/25 bg-info/[0.05] px-3 py-2.5 text-xs leading-relaxed text-ink-muted">
          This dashboard uses IAM-authenticated AWS Systems Manager port forwarding. Backend services and Kubernetes management ports remain private and are not exposed to the public internet.
        </div>
      </Panel>

      <div className="flex flex-wrap items-center justify-between gap-2 px-1 text-[10px] text-ink-dim">
        <span>Live resource snapshots are fetched from the deployed Edge and Cloud APIs.</span>
        <span>Edge sample: {metricTime(data.edge)} · Cloud sample: {metricTime(data.cloud)}</span>
      </div>
    </div>
  );
}

function ArchitectureNode({ icon: Icon, title, subtitle, status }: { icon: typeof Cpu; title: string; subtitle: string; status: string }) {
  return (
    <div className="flex items-center gap-3 rounded-xl border border-line bg-raised/70 px-3 py-3 md:block md:text-center">
      <span className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-brand/25 bg-brand/10 text-brand md:mb-2"><Icon className="h-4 w-4" /></span>
      <div className="min-w-0 flex-1">
        <div className="text-xs font-semibold text-ink">{title}</div>
        <div className="mt-0.5 text-[10px] text-ink-dim">{subtitle}</div>
      </div>
      <div className="md:mt-2"><StatusBadge label={status} tone={toneForStatus(status)} /></div>
    </div>
  );
}

function ServiceCard({ label, icon: Icon, health, detail }: { label: string; icon: typeof Server; health: ServiceHealth | null; detail: string }) {
  const status = health?.status ?? 'unreachable';
  return (
    <MetricCard
      label={label}
      icon={Icon}
      tone={toneForStatus(status) as 'ok' | 'warn' | 'bad' | 'neutral'}
      value={<StatusBadge label={status} tone={toneForStatus(status)} pulse={status === 'ok'} />}
      sub={detail}
      footer={health ? `Version ${health.version} · ${timeAgo(Date.parse(health.timestamp) || Number(health.timestamp) * 1000)}` : 'No health response'}
    />
  );
}

function NodeHealthCard({ label, icon: Icon, node }: { label: string; icon: typeof Cpu; node: NodeStatus }) {
  const status = node.health?.status ?? 'unreachable';
  const camera = node.health?.camera_open === false ? 'Camera unavailable (image API remains separate)' : null;
  return (
    <MetricCard
      label={label}
      icon={Icon}
      tone={status === 'ok' ? 'ok' : status === 'degraded' ? 'warn' : 'bad'}
      value={<StatusBadge label={status} tone={toneForStatus(status)} pulse={node.reachable} />}
      sub={node.health?.model_loaded ? 'Inference model loaded' : 'Model status unavailable'}
      footer={camera ?? (node.metrics ? `Probe ${node.probeLatencyMs ?? '—'} ms · ${timeAgo(node.probedAt)}` : node.error ?? 'No node response')}
    />
  );
}

function ResourcePanel({ title, subtitle, node }: { title: string; subtitle: string; node: NodeStatus }) {
  const m = node.metrics;
  return (
    <Panel title={title} subtitle={subtitle} actions={<StatusBadge label={node.reachable ? 'LIVE' : 'OFFLINE'} tone={node.reachable ? 'ok' : 'bad'} pulse={node.reachable} />}>
      {m ? (
        <div className="space-y-4">
          <div className="grid grid-cols-3 gap-2">
            <Gauge label="CPU" value={m.cpu_percent} warnAt={70} badAt={85} />
            <Gauge label="RAM" value={m.ram_percent} warnAt={75} badAt={90} />
            <Gauge label="Disk" value={m.disk_percent} warnAt={80} badAt={90} />
          </div>
          <div className="grid grid-cols-2 gap-3 border-t border-line pt-3 text-xs">
            <div>
              <div className="text-[10px] uppercase tracking-wider text-ink-dim">Memory used</div>
              <div className="mt-1 font-semibold tabular-nums text-ink">{m.ram_used_gb.toFixed(2)} / {m.ram_total_gb.toFixed(2)} GB</div>
            </div>
            <div>
              <div className="text-[10px] uppercase tracking-wider text-ink-dim">Disk used</div>
              <div className="mt-1 font-semibold tabular-nums text-ink">{m.disk_used_gb.toFixed(2)} / {m.disk_total_gb.toFixed(2)} GB</div>
            </div>
          </div>
          <div className="text-right text-[10px] text-ink-dim">Snapshot {timeAgo(Date.parse(m.timestamp))}</div>
        </div>
      ) : (
        <div className="py-8 text-center text-xs text-ink-dim">{node.error ?? 'Live resource metrics unavailable.'}</div>
      )}
    </Panel>
  );
}

function Endpoint({ label, value, state }: { label: string; value: string; state: string }) {
  const reachable = state === 'ok' || state === 'reachable';
  return (
    <div className="flex min-w-0 items-center justify-between gap-3 rounded-lg border border-line bg-raised/40 px-3 py-2.5">
      <div className="min-w-0">
        <div className="text-xs font-medium text-ink">{label}</div>
        <div className="mt-0.5 truncate text-[10px] text-ink-dim">{value}</div>
      </div>
      <StatusBadge label={state} tone={reachable ? 'ok' : 'warn'} />
    </div>
  );
}

function metricTime(node: NodeStatus): string {
  if (!node.metrics?.timestamp) return 'unavailable';
  return timeAgo(Date.parse(node.metrics.timestamp));
}

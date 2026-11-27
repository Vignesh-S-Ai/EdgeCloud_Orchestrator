import { useState } from 'react';
import { Boxes, CircleDot, Layers, Network, RotateCw } from 'lucide-react';
import { Panel } from '../components/ui/Panel';
import { MetricCard } from '../components/ui/MetricCard';
import { StatusBadge, toneForStatus } from '../components/ui/StatusBadge';
import { SearchInput, SegmentedControl } from '../components/ui/Controls';
import { EmptyState, ErrorState, LoadingGrid, NoLiveData } from '../components/ui/States';
import { SourceRow } from '../components/ui/SourceChips';
import { Mono, TableShell, Td, Th, Tr } from '../components/ui/Table';
import { useData } from '../context/DataSourceContext';
import { useAsync } from '../hooks/useAsync';
import type { PodStatus } from '../types';

type StatusFilter = 'all' | PodStatus;

export function WorkloadsPage() {
  const { source, refreshMs, setMode } = useData();
  const { data, loading, error, reload } = useAsync(() => source.getWorkloads(), [source], {
    intervalMs: refreshMs,
  });

  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');
  const [query, setQuery] = useState('');

  if (loading && !data) return <LoadingGrid count={6} />;
  if (error && !data) return <ErrorState description={error} onRetry={reload} />;

  if (!data) {
    return <NoLiveData onEnableDemo={() => setMode('demo')} />;
  }

  const pods = data.pods.filter((pod) => {
    if (statusFilter !== 'all' && pod.status !== statusFilter) return false;
    if (query && !pod.name.toLowerCase().includes(query.toLowerCase())) return false;
    return true;
  });

  return (
    <div className="space-y-4">
      <SourceRow
        views={['workloads']}
        note="No backend endpoint for this view - shown with clearly-labelled sample data (real cluster: kubectl get pods -n edgecloud)."
      />
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          label="Running pods"
          icon={CircleDot}
          tone="ok"
          value={data.summary.running}
          sub={`${data.pods.length} pods total in namespace edgecloud`}
          footer="kubectl get pods --namespace edgecloud"
        />
        <MetricCard
          label="Pending pods"
          icon={Layers}
          tone={data.summary.pending > 0 ? 'warn' : 'ok'}
          value={data.summary.pending}
          sub="Waiting for scheduling or image pull"
          footer={data.summary.pending > 0 ? 'Needs attention' : 'Nothing queued'}
        />
        <MetricCard
          label="Failed pods"
          icon={Boxes}
          tone={data.summary.failed > 0 ? 'bad' : 'ok'}
          value={data.summary.failed}
          sub="Crash loop / back-off restarts"
          footer={data.summary.failed > 0 ? 'Legacy workload on cordoned node' : 'All healthy'}
        />
        <MetricCard
          label="Total restarts"
          icon={RotateCw}
          tone={data.summary.restarts > 5 ? 'warn' : 'ok'}
          value={data.summary.restarts}
          sub="Across all pods"
          footer="Zero restarts on the four core services"
        />
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        <Panel
          className="xl:col-span-2"
          title="Pods"
          subtitle={`${pods.length} of ${data.pods.length} shown`}
          actions={
            <div className="flex flex-wrap items-center gap-2">
              <SearchInput value={query} onChange={setQuery} placeholder="Search pod…" />
              <SegmentedControl<StatusFilter>
                value={statusFilter}
                onChange={setStatusFilter}
                size="sm"
                options={[
                  { value: 'all', label: 'All' },
                  { value: 'Running', label: 'Running' },
                  { value: 'Pending', label: 'Pending' },
                  { value: 'Failed', label: 'Failed' },
                ]}
              />
            </div>
          }
          bodyClassName="p-0"
        >
          {pods.length === 0 ? (
            <div className="p-5">
              <EmptyState
                title="No pods match"
                description="Clear the search or select a different status filter."
              />
            </div>
          ) : (
            <TableShell>
              <thead>
                <tr>
                  <Th>Pod</Th>
                  <Th>Role</Th>
                  <Th>Status</Th>
                  <Th>Ready</Th>
                  <Th className="text-right">Restarts</Th>
                  <Th>Node</Th>
                  <Th className="text-right">CPU</Th>
                  <Th className="text-right">Memory</Th>
                  <Th className="text-right">Age</Th>
                </tr>
              </thead>
              <tbody>
                {pods.map((pod) => (
                  <Tr key={pod.name}>
                    <Td>
                      <Mono className="text-ink">{pod.name}</Mono>
                      <div className="text-[10px] text-ink-dim">{pod.image}</div>
                    </Td>
                    <Td>
                      <span className="text-[11px] uppercase tracking-wider text-ink-dim">{pod.role}</span>
                    </Td>
                    <Td>
                      <StatusBadge label={pod.status} tone={toneForStatus(pod.status)} />
                    </Td>
                    <Td>
                      <Mono className={pod.ready === '1/1' ? 'text-ok' : 'text-warn'}>{pod.ready}</Mono>
                    </Td>
                    <Td className="text-right">
                      <Mono className={pod.restarts > 0 ? 'text-warn' : 'text-ink-muted'}>{pod.restarts}</Mono>
                    </Td>
                    <Td>
                      <Mono>{pod.node}</Mono>
                    </Td>
                    <Td className="text-right">
                      <Mono>{pod.cpu}</Mono>
                    </Td>
                    <Td className="text-right">
                      <Mono>{pod.memory}</Mono>
                    </Td>
                    <Td className="text-right">
                      <Mono>{pod.age}</Mono>
                    </Td>
                  </Tr>
                ))}
              </tbody>
            </TableShell>
          )}
        </Panel>

        <div className="space-y-4">
          <Panel title="Cluster nodes" subtitle="K3s + KubeEdge node status" actions={<Network className="h-3.5 w-3.5 text-ink-dim" />} bodyClassName="p-0">
            <TableShell>
              <thead>
                <tr>
                  <Th>Node</Th>
                  <Th>Status</Th>
                  <Th className="text-right">Pods</Th>
                </tr>
              </thead>
              <tbody>
                {data.nodes.map((node) => (
                  <Tr key={node.name}>
                    <Td>
                      <Mono className="text-ink">{node.name}</Mono>
                      <div className="text-[10px] text-ink-dim">
                        {node.internalIp} · {node.role}
                      </div>
                    </Td>
                    <Td>
                      <StatusBadge label={node.status} tone={toneForStatus(node.status)} />
                    </Td>
                    <Td className="text-right">
                      <Mono>{node.pods}</Mono>
                    </Td>
                  </Tr>
                ))}
              </tbody>
            </TableShell>
          </Panel>

          <Panel title="Version matrix" subtitle="Components running in the cluster">
            <ul className="space-y-2 text-[11px]">
              {[
                { k: 'K3s', v: 'v1.32.13+k3s1 (control-plane)' },
                { k: 'KubeEdge', v: 'v1.23.1 (edgecore + cloudcore)' },
                { k: 'Images', v: 'edgecloud/{orchestrator,scheduler,cloud-node,edge-node}' },
                { k: 'Namespace', v: 'edgecloud' },
                { k: 'Policy', v: 'rule_based (scheduler/config.py)' },
              ].map((item) => (
                <li key={item.k} className="flex items-start justify-between gap-3 border-b border-line/70 pb-2 last:border-0 last:pb-0">
                  <span className="shrink-0 uppercase tracking-wider text-ink-dim">{item.k}</span>
                  <span className="text-right font-mono text-[10px] text-ink-muted">{item.v}</span>
                </li>
              ))}
            </ul>
          </Panel>
        </div>
      </div>

      <Panel title="Services" subtitle="Kubernetes services in namespace edgecloud" bodyClassName="p-0">
        <TableShell>
          <thead>
            <tr>
              <Th>Service</Th>
              <Th>Type</Th>
              <Th className="text-right">Port</Th>
              <Th className="text-right">Node port</Th>
              <Th>Selector</Th>
              <Th className="text-right">Endpoints</Th>
            </tr>
          </thead>
          <tbody>
            {data.services.map((service) => (
              <Tr key={service.name}>
                <Td>
                  <Mono className="text-ink">{service.name}</Mono>
                  <div className="text-[10px] text-ink-dim">{service.namespace}</div>
                </Td>
                <Td>
                  <StatusBadge label={service.type} tone={service.type === 'NodePort' ? 'brand' : 'neutral'} />
                </Td>
                <Td className="text-right">
                  <Mono>{service.port}</Mono>
                </Td>
                <Td className="text-right">
                  <Mono className={service.nodePort ? 'text-brand' : 'text-ink-dim'}>{service.nodePort ?? '—'}</Mono>
                </Td>
                <Td>
                  <Mono>{service.selector}</Mono>
                </Td>
                <Td className="text-right">
                  <Mono className="text-ok">{service.endpoints}</Mono>
                </Td>
              </Tr>
            ))}
          </tbody>
        </TableShell>
      </Panel>
    </div>
  );
}

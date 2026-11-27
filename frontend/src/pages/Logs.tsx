import { useMemo, useState } from 'react';
import { AlertTriangle, Bug, Info, SearchX, ShieldAlert } from 'lucide-react';
import { Panel } from '../components/ui/Panel';
import { MetricCard } from '../components/ui/MetricCard';
import { Select, SearchInput, SegmentedControl } from '../components/ui/Controls';
import { EmptyState, ErrorState, LoadingGrid, NoLiveData } from '../components/ui/States';
import { SourceRow } from '../components/ui/SourceChips';
import { Mono, TableShell, Td, Th, Tr } from '../components/ui/Table';
import { useData } from '../context/DataSourceContext';
import { useAsync } from '../hooks/useAsync';
import { formatDateTime, formatNumber } from '../lib/format';
import type { LogLevel, SystemEvent } from '../types';

type LevelFilter = 'all' | LogLevel;
type SourceFilter = 'all' | SystemEvent['source'];
type RangeFilter = '15m' | '1h' | '3h' | 'all';

const RANGES: Record<Exclude<RangeFilter, 'all'>, number> = {
  '15m': 15 * 60_000,
  '1h': 60 * 60_000,
  '3h': 3 * 60 * 60_000,
};

export function LogsPage() {
  const { source, refreshMs, setMode } = useData();
  const { data, loading, error, reload } = useAsync(() => source.getLogs(), [source], {
    intervalMs: refreshMs,
  });

  const [level, setLevel] = useState<LevelFilter>('all');
  const [eventSource, setEventSource] = useState<SourceFilter>('all');
  const [range, setRange] = useState<RangeFilter>('all');
  const [query, setQuery] = useState('');

  const filtered = useMemo(() => {
    if (!data) return [];
    const cutoff = range === 'all' ? 0 : Date.now() - RANGES[range];
    const needle = query.trim().toLowerCase();
    return data.events.filter((event) => {
      if (event.t < cutoff) return false;
      if (level !== 'all' && event.level !== level) return false;
      if (eventSource !== 'all' && event.source !== eventSource) return false;
      if (needle && !event.message.toLowerCase().includes(needle)) return false;
      return true;
    });
  }, [data, level, eventSource, range, query]);

  if (loading && !data) return <LoadingGrid count={6} />;
  if (error && !data) return <ErrorState description={error} onRetry={reload} />;
  if (!data) return <NoLiveData onEnableDemo={() => setMode('demo')} />;

  return (
    <div className="space-y-4">
      <SourceRow
        views={['logs']}
        note="No backend endpoint for this view - shown with clearly-labelled sample data."
      />
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          label="Errors"
          icon={ShieldAlert}
          tone={data.counts.error > 0 ? 'bad' : 'ok'}
          value={formatNumber(data.counts.error)}
          sub="Failing requests, unreachable rules"
          footer="Last 3 hours of buffered events"
        />
        <MetricCard
          label="Warnings"
          icon={AlertTriangle}
          tone={data.counts.warn > 0 ? 'warn' : 'ok'}
          value={formatNumber(data.counts.warn)}
          sub="Timeouts, slow probes, pending pods"
          footer="Scheduler metrics cache and KubeEdge heartbeats"
        />
        <MetricCard
          label="Info events"
          icon={Info}
          tone="info"
          value={formatNumber(data.counts.info)}
          sub="Successful requests and decisions"
          footer="Orchestrator / scheduler / node services"
        />
        <MetricCard
          label="Debug events"
          icon={Bug}
          tone="neutral"
          value={formatNumber(data.counts.debug)}
          sub="Verbose service logging"
          footer="Enable DEBUG level in services to increase"
        />
      </div>

      <Panel
        title="Event stream"
        subtitle={`${formatNumber(filtered.length)} events match the current filters`}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <SegmentedControl<LevelFilter>
              value={level}
              onChange={setLevel}
              size="sm"
              options={[
                { value: 'all', label: 'All levels' },
                { value: 'error', label: 'Error', count: data.counts.error },
                { value: 'warn', label: 'Warn', count: data.counts.warn },
                { value: 'info', label: 'Info', count: data.counts.info },
                { value: 'debug', label: 'Debug', count: data.counts.debug },
              ]}
            />
            <Select<SourceFilter>
              value={eventSource}
              onChange={setEventSource}
              label="Source"
              options={[
                { value: 'all', label: 'All sources' },
                { value: 'orchestrator', label: 'orchestrator' },
                { value: 'scheduler', label: 'scheduler' },
                { value: 'edge', label: 'edge' },
                { value: 'cloud', label: 'cloud' },
                { value: 'k3s', label: 'k3s' },
                { value: 'kubeedge', label: 'kubeedge' },
              ]}
            />
            <Select<RangeFilter>
              value={range}
              onChange={setRange}
              label="Range"
              options={[
                { value: '15m', label: 'Last 15 min' },
                { value: '1h', label: 'Last hour' },
                { value: '3h', label: 'Last 3 hours' },
                { value: 'all', label: 'Everything' },
              ]}
            />
            <SearchInput value={query} onChange={setQuery} placeholder="Search message…" />
          </div>
        }
        bodyClassName="p-0"
      >
        {filtered.length === 0 ? (
          <div className="p-5">
            <EmptyState
              title="No events match"
              description="Widen the time range or clear the level / source / text filters."
              action={
                <button
                  type="button"
                  onClick={() => {
                    setLevel('all');
                    setEventSource('all');
                    setRange('all');
                    setQuery('');
                  }}
                  className="inline-flex items-center gap-1.5 rounded-md border border-line-strong bg-raised px-3 py-1.5 text-xs font-medium text-ink transition hover:border-brand/40 hover:text-brand"
                >
                  <SearchX className="h-3.5 w-3.5" />
                  Reset filters
                </button>
              }
            />
          </div>
        ) : (
          <TableShell className="max-h-[560px]">
            <thead className="sticky top-0 z-10">
              <tr>
                <Th className="w-44">Timestamp</Th>
                <Th className="w-20">Level</Th>
                <Th className="w-28">Source</Th>
                <Th>Message</Th>
              </tr>
            </thead>
            <tbody>
              {filtered.slice(0, 300).map((event) => (
                <Tr key={event.id}>
                  <Td className="whitespace-nowrap">
                    <Mono className="text-ink-dim">{formatDateTime(event.t)}</Mono>
                  </Td>
                  <Td>
                    <span
                      className={`rounded border px-1.5 py-px text-[10px] font-semibold uppercase tracking-wider ${
                        event.level === 'error'
                          ? 'border-bad/30 bg-bad/10 text-bad'
                          : event.level === 'warn'
                            ? 'border-warn/30 bg-warn/10 text-warn'
                            : event.level === 'info'
                              ? 'border-info/30 bg-info/10 text-info'
                              : 'border-line-strong bg-raised text-ink-dim'
                      }`}
                    >
                      {event.level}
                    </span>
                  </Td>
                  <Td>
                    <span className="text-[11px] text-ink-muted">{event.source}</span>
                  </Td>
                  <Td>
                    <Mono className="break-all text-ink-muted">{event.message}</Mono>
                  </Td>
                </Tr>
              ))}
            </tbody>
          </TableShell>
        )}
      </Panel>
    </div>
  );
}

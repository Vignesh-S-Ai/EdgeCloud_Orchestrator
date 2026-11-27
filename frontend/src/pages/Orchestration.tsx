import { useState } from 'react';
import { Activity, ArrowRightLeft, Brain, ShieldAlert, Zap } from 'lucide-react';
import { DecisionBars } from '../components/charts/DecisionBars';
import { RouteFlow } from '../components/charts/RouteFlow';
import { Panel } from '../components/ui/Panel';
import { MetricCard } from '../components/ui/MetricCard';
import { Pill, TargetBadge, toneForStatus } from '../components/ui/StatusBadge';
import { SegmentedControl, SearchInput } from '../components/ui/Controls';
import { EmptyState, ErrorState, LoadingGrid, LoadingState, NoLiveData } from '../components/ui/States';
import { SourceRow } from '../components/ui/SourceChips';
import { Mono, TableShell, Td, Th, Tr } from '../components/ui/Table';
import { useData } from '../context/DataSourceContext';
import { useAsync } from '../hooks/useAsync';
import { formatMs, formatNumber, timeAgo } from '../lib/format';
import { errorMessage } from '../services/http';
import type { Decision, RoutingRecord, Target } from '../types';

type TargetFilter = 'all' | Target;
type StatusFilter = 'all' | RoutingRecord['status'];

const MAX_ROWS = 60;

function averageOf(records: RoutingRecord[], pick: (record: RoutingRecord) => number | null): number | null {
  const values = records.map(pick).filter((value): value is number => value !== null);
  if (values.length === 0) return null;
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

export function OrchestrationPage() {
  const { source, refreshMs, setMode } = useData();
  const { data, loading, error, reload } = useAsync(() => source.getRouting(), [source], {
    intervalMs: refreshMs,
  });

  const [targetFilter, setTargetFilter] = useState<TargetFilter>('all');
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');
  const [query, setQuery] = useState('');

  if (loading && !data) return <LoadingGrid count={4} />;
  if (error && !data) return <ErrorState description={error} onRetry={reload} />;

  if (!data) {
    return (
      <div className="space-y-4">
        <NoLiveData onEnableDemo={() => setMode('demo')} />
        <DecisionProbe />
      </div>
    );
  }

  const records = data.records;
  const last = records[0] ?? null;
  const executed = records.filter((r) => r.actualTarget !== null);
  const filtered = records.filter((record) => {
    if (targetFilter !== 'all' && record.selectedTarget !== targetFilter) return false;
    if (statusFilter !== 'all' && record.status !== statusFilter) return false;
    if (query && !record.id.includes(query.toLowerCase())) return false;
    return true;
  });

  const fallbacks = records.filter((r) => r.fallbackUsed).length;
  const failures = records.filter((r) => r.status === 'failed').length;
  const edgeInferenceAvg = averageOf(records.filter((r) => r.actualTarget === 'edge'), (r) => r.inferenceMs);
  const cloudInferenceAvg = averageOf(records.filter((r) => r.actualTarget === 'cloud'), (r) => r.inferenceMs);

  return (
    <div className="space-y-4">
      <SourceRow
        views={['routingHistory', 'series', 'decisionProbe']}
        note="Routing history and charts are labelled sample data - the decision probe below runs against the live scheduler."
      />
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          label="Routed requests"
          icon={ArrowRightLeft}
          tone="brand"
          value={formatNumber(records.length)}
          sub="Scheduler decisions recorded"
          footer={source.mode === 'live' ? 'Labelled sample history' : 'Rolling 6h window'}
        />
        <MetricCard
          label="Edge share"
          icon={Activity}
          tone="ok"
          value={data.edgeSharePct !== null ? `${Math.round(data.edgeSharePct)}%` : '—'}
          sub="Executed on the edge node"
          footer={executed.length ? `${formatNumber(executed.length)} executed` : '—'}
        />
        <MetricCard
          label="Avg scheduler decision"
          icon={Brain}
          tone="warn"
          value={data.avgSchedulerMs !== null ? formatMs(data.avgSchedulerMs) : '—'}
          sub="POST /decision round trip"
          footer="Cached metrics dominate this number"
        />
        <MetricCard
          label="Fallbacks / failures"
          icon={ShieldAlert}
          tone={fallbacks + failures > 0 ? 'bad' : 'ok'}
          value={`${fallbacks} / ${failures}`}
          sub="Cloud->edge fallbacks and failed placements"
          footer={fallbacks ? 'High priority only (orchestrator policy)' : 'No fallback triggered'}
        />
      </div>

      <Panel title="Edge -> Cloud routing path" subtitle="Where the most recent workload was executed">
        <RouteFlow
          lastTarget={last?.actualTarget ?? last?.selectedTarget ?? null}
          edgeSharePct={data.edgeSharePct}
          edgeMs={edgeInferenceAvg}
          cloudMs={cloudInferenceAvg}
          sourceNote={source.mode === 'demo' ? 'Simulated routing history' : 'Labelled sample routing history - no history endpoint yet'}
        />
      </Panel>

      <div className="grid gap-4 xl:grid-cols-3">
        <Panel
          className="xl:col-span-2"
          title="Request routing history"
          subtitle={`${formatNumber(filtered.length)} of ${formatNumber(records.length)} decisions`}
          actions={
            <div className="flex flex-wrap items-center gap-2">
              <SearchInput value={query} onChange={setQuery} placeholder="Search workload id…" />
              <SegmentedControl<TargetFilter>
                value={targetFilter}
                onChange={setTargetFilter}
                size="sm"
                options={[
                  { value: 'all', label: 'All' },
                  { value: 'edge', label: 'Edge' },
                  { value: 'cloud', label: 'Cloud' },
                  { value: 'queue', label: 'Queue' },
                  { value: 'error', label: 'Error' },
                ]}
              />
              <SegmentedControl<StatusFilter>
                value={statusFilter}
                onChange={setStatusFilter}
                size="sm"
                options={[
                  { value: 'all', label: 'Any status' },
                  { value: 'success', label: 'Success' },
                  { value: 'fallback', label: 'Fallback' },
                  { value: 'failed', label: 'Failed' },
                  { value: 'queued', label: 'Queued' },
                ]}
              />
            </div>
          }
          bodyClassName="p-0"
        >
          {filtered.length === 0 ? (
            <div className="p-5">
              <EmptyState
                title="No routing records match"
                description="Adjust the target, status or search filters to see decisions again."
              />
            </div>
          ) : (
            <>
              <TableShell>
                <thead>
                  <tr>
                    <Th>Time</Th>
                    <Th>Workload</Th>
                    <Th>Priority</Th>
                    <Th>Selected</Th>
                    <Th>Executed</Th>
                    <Th>Status</Th>
                    <Th className="text-right">Score</Th>
                    <Th className="text-right">Scheduler</Th>
                    <Th className="text-right">Inference</Th>
                    <Th className="text-right">Total</Th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.slice(0, MAX_ROWS).map((record) => (
                    <Tr key={`${record.id}-${record.t}`}>
                      <Td className="whitespace-nowrap">
                        <Mono className="text-ink-muted">{timeAgo(record.t)}</Mono>
                      </Td>
                      <Td>
                        <Mono className="text-ink">{record.id}</Mono>
                        <div className="text-[10px] text-ink-dim">{record.workloadType}</div>
                      </Td>
                      <Td>
                        <Pill label={record.priority.toUpperCase()} tone={record.priority === 'high' ? 'bad' : record.priority === 'medium' ? 'warn' : 'neutral'} />
                      </Td>
                      <Td>
                        <TargetBadge target={record.selectedTarget} />
                      </Td>
                      <Td>{record.actualTarget ? <TargetBadge target={record.actualTarget} /> : <span className="text-ink-dim">—</span>}</Td>
                      <Td>
                        <Pill label={record.status} tone={toneForStatus(record.status)} />
                      </Td>
                      <Td className="text-right">
                        <Mono className="text-ink-muted">{record.score.toFixed(0)}</Mono>
                      </Td>
                      <Td className="text-right">
                        <Mono className="text-ink-muted">{formatMs(record.schedulerMs)}</Mono>
                      </Td>
                      <Td className="text-right">
                        <Mono className={record.inferenceMs !== null ? 'text-ink' : 'text-ink-dim'}>
                          {formatMs(record.inferenceMs)}
                        </Mono>
                      </Td>
                      <Td className="text-right">
                        <Mono className="text-ink">{formatMs(record.totalMs)}</Mono>
                      </Td>
                    </Tr>
                  ))}
                </tbody>
              </TableShell>

              <div className="border-t border-line px-4 py-2.5 text-[11px] text-ink-dim">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span>
                    Showing {Math.min(filtered.length, MAX_ROWS)} rows · {filtered.length - MAX_ROWS > 0 ? `${filtered.length - MAX_ROWS} older rows hidden` : 'all rows visible'}
                  </span>
                  <span className="hidden md:inline">Hover a row for the scheduler reason below</span>
                </div>
                <div className="mt-2 rounded-lg border border-line bg-raised/50 px-3 py-2 font-mono text-[11px] leading-relaxed text-ink-muted">
                  {filtered[0]
                    ? `reason: ${filtered[0].reason}${filtered[0].fallbackReason ? ` · ${filtered[0].fallbackReason}` : ''}`
                    : ''}
                </div>
              </div>
            </>
          )}
        </Panel>

        <div className="space-y-4">
          <Panel title="Scheduler decision distribution" subtitle="Targets chosen by the rule-based policy">
            <DecisionBars data={data.decisionCounts.map((item) => ({ target: item.target, count: item.count }))} />
            <div className="mt-2 rounded-lg border border-line bg-raised/50 px-3 py-2 text-[11px] leading-relaxed text-ink-muted">
              <span className="text-ink-dim">latest reason: </span>
              {last ? last.reason : '—'}
            </div>
          </Panel>

          <DecisionProbe />
        </div>
      </div>
    </div>
  );
}

/**
 * Interactive widget around the real `POST /decision` endpoint of the
 * scheduler service. In demo mode the same widget is fed by the mock store.
 */
function DecisionProbe() {
  const { source, endpoints } = useData();
  const [state, setState] = useState<{ loading: boolean; data: Decision | null; error: string | null }>({
    loading: false,
    data: null,
    error: null,
  });

  const run = async () => {
    setState((prev) => ({ ...prev, loading: true, error: null }));
    try {
      const decision = await source.probeDecision();
      setState({ loading: false, data: decision, error: null });
    } catch (error) {
      setState({ loading: false, data: null, error: errorMessage(error) });
    }
  };

  return (
    <Panel
      title="Scheduler decision probe"
      subtitle={`POST ${endpoints.scheduler}/decision`}
      actions={
        <button
          type="button"
          onClick={run}
          disabled={state.loading}
          className="inline-flex items-center gap-1.5 rounded-md border border-brand/40 bg-brand/10 px-3 py-1.5 text-xs font-medium text-brand transition hover:bg-brand/20 disabled:opacity-50"
        >
          <Zap className={`h-3.5 w-3.5 ${state.loading ? 'animate-pulse' : ''}`} />
          {state.loading ? 'Probing…' : 'Run probe'}
        </button>
      }
    >
      {state.loading && <LoadingState label="Asking the scheduler for a placement decision…" rows={2} />}

      {!state.loading && state.error && (
        <ErrorState
          title="Decision probe failed"
          description={
            source.mode === 'live'
              ? `${state.error} — the scheduler needs reachable edge and cloud URLs to fetch live metrics.`
              : state.error
          }
          onRetry={run}
        />
      )}

      {!state.loading && !state.error && !state.data && (
        <EmptyState
          title="No probe run yet"
          description={
            source.mode === 'live'
              ? 'Runs a real POST /decision against the scheduler using live edge/cloud metrics.'
              : 'Runs a simulated decision against the mock store (DEMO DATA).'
          }
        />
      )}

      {!state.loading && !state.error && state.data && (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <TargetBadge target={state.data.target} />
            <span className="text-[11px] tabular-nums text-ink-dim">score {state.data.score.toFixed(1)}</span>
          </div>
          <div className="h-1.5 overflow-hidden rounded-full bg-raised">
            <div
              className="h-full rounded-full bg-brand transition-all"
              style={{ width: `${Math.max(2, Math.min(100, state.data.score))}%` }}
            />
          </div>
          <p className="text-[11px] leading-relaxed text-ink-muted">{state.data.reason}</p>
          <div className="flex items-center justify-between border-t border-line pt-2 text-[10px] text-ink-dim">
            <Mono>{state.data.workload_id}</Mono>
            <span>{source.mode === 'live' ? 'Live scheduler response' : 'Demo data'}</span>
          </div>
        </div>
      )}
    </Panel>
  );
}

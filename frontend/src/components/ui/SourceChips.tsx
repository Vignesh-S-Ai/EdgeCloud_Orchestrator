import { Radio, TestTube2 } from 'lucide-react';
import { useData } from '../../context/DataSourceContext';

/**
 * View keys the backend can actually serve today. Everything else has no
 * endpoint yet and falls back to clearly-labelled sample data in live mode.
 */
export type ViewKey =
  | 'health'
  | 'metrics'
  | 'serviceInfo'
  | 'decisionProbe'
  | 'routingHistory'
  | 'series'
  | 'activity'
  | 'workloads'
  | 'inference'
  | 'logs';

const LIVE_VIEWS: ReadonlySet<ViewKey> = new Set<ViewKey>([
  'health',
  'metrics',
  'serviceInfo',
  'decisionProbe',
]);

interface SourceChipsProps {
  views: ViewKey[];
}

/**
 * Per-view source indicator, rendered only in live mode so it is always
 * obvious which panels come from the running FastAPI services and which are
 * clearly-labelled sample data (views with no endpoint yet).
 */
export function SourceChips({ views }: SourceChipsProps) {
  const { mode } = useData();
  if (mode !== 'live') return null;

  const hasLive = views.some((view) => LIVE_VIEWS.has(view));
  const hasSample = views.some((view) => !LIVE_VIEWS.has(view));
  if (!hasLive && !hasSample) return null;

  return (
    <span className="flex flex-wrap items-center gap-1.5">
      {hasLive && (
        <span
          title="Read from the running FastAPI services (/health, /metrics, /decision)"
          className="inline-flex items-center gap-1.5 rounded-md border border-ok/35 bg-ok/10 px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.1em] text-ok"
        >
          <Radio className="h-3 w-3" />
          Live data
        </span>
      )}
      {hasSample && (
        <span
          title="No backend endpoint for this view yet - shown with clearly-labelled sample data"
          className="inline-flex items-center gap-1.5 rounded-md border border-dashed border-ink-dim/60 bg-raised px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.1em] text-ink-muted"
        >
          <TestTube2 className="h-3 w-3" />
          Sample data
        </span>
      )}
    </span>
  );
}

interface SourceRowProps extends SourceChipsProps {
  note?: string;
}

/** Chip row with an optional explanatory note; hidden entirely in demo mode. */
export function SourceRow({ views, note }: SourceRowProps) {
  const { mode } = useData();
  if (mode !== 'live') return null;

  return (
    <div className="flex flex-wrap items-center gap-2">
      <SourceChips views={views} />
      {note && <span className="text-[11px] text-ink-dim">{note}</span>}
    </div>
  );
}

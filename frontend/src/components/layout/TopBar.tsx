import { useEffect, useState } from 'react';
import { FlaskConical, Menu, Radio, RefreshCw } from 'lucide-react';
import { useData } from '../../context/DataSourceContext';
import { SegmentedControl } from '../ui/Controls';

interface TopBarProps {
  title: string;
  subtitle: string;
  onMenu: () => void;
  updated: number | null;
  refreshing: boolean;
}

export function TopBar({ title, subtitle, onMenu, updated, refreshing }: TopBarProps) {
  const { mode, setMode, refreshMs, source } = useData();
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  return (
    <header className="sticky top-0 z-20 border-b border-line bg-base/90 backdrop-blur">
      <div className="flex h-16 items-center gap-4 px-4 sm:px-6 lg:px-8">
        <button
          type="button"
          onClick={onMenu}
          className="rounded-lg border border-line bg-raised p-2 text-ink-muted transition hover:text-ink lg:hidden"
          aria-label="Open navigation"
        >
          <Menu className="h-4 w-4" />
        </button>

        <div className="min-w-0 flex-1">
          <h1 className="truncate text-[15px] font-semibold tracking-tight text-ink">{title}</h1>
          <p className="truncate text-[11px] text-ink-dim">{subtitle}</p>
        </div>

        <div className="hidden items-center gap-3 sm:flex">
          <div className="flex items-center gap-1.5 text-[11px] text-ink-dim">
            <RefreshCw className={`h-3 w-3 ${refreshing ? 'animate-spin text-brand' : ''}`} />
            <span className="tabular-nums">
              {updated ? `Updated ${new Date(updated).toLocaleTimeString('en-GB')}` : 'Waiting for data'}
            </span>
          </div>

          <span className="h-4 w-px bg-line" />

          <ModeBadge mode={mode} hint={source.hint} />
        </div>

        <SegmentedControl<DataSourceMode>
          value={mode}
          onChange={setMode}
          size="sm"
          options={[
            { value: 'demo', label: 'Demo' },
            { value: 'live', label: 'Live' },
          ]}
        />
      </div>

      <div className="flex items-center justify-between gap-3 border-t border-line/70 bg-raised/40 px-4 py-1.5 text-[10px] text-ink-dim sm:px-6 lg:px-8">
        <span className="font-mono truncate">CLOUD-13 · Edge-Cloud Orchestration for Low-Latency Workloads</span>
        <span className="hidden shrink-0 tabular-nums sm:inline">
          {new Date(now).toLocaleString('en-GB')} · refresh {Math.round(refreshMs / 1000)}s
        </span>
      </div>
    </header>
  );
}

function ModeBadge({ mode, hint }: { mode: DataSourceMode; hint: string }) {
  if (mode === 'live') {
    return (
      <span
        title={hint}
        className="inline-flex items-center gap-1.5 rounded-md border border-ok/35 bg-ok/10 px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.1em] text-ok"
      >
        <Radio className="h-3 w-3" />
        LIVE BACKEND
      </span>
    );
  }
  return (
    <span
      title={hint}
      className="inline-flex items-center gap-1.5 rounded-md border border-warn/40 bg-warn/10 px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.1em] text-warn"
    >
      <FlaskConical className="h-3 w-3" />
      DEMO DATA
    </span>
  );
}

type DataSourceMode = 'demo' | 'live';

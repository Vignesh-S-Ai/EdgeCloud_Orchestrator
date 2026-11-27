import type { TooltipProps } from 'recharts';

const FORMATTERS: Record<string, (value: number) => string> = {
  edgeMs: (v) => `${v} ms`,
  cloudMs: (v) => `${v} ms`,
  schedulerMs: (v) => `${v} ms`,
  totalMs: (v) => `${v} ms`,
  edgeCpu: (v) => `${v}%`,
  edgeRam: (v) => `${v}%`,
  edgeDisk: (v) => `${v}%`,
  cloudCpu: (v) => `${v}%`,
  cloudRam: (v) => `${v}%`,
  cloudDisk: (v) => `${v}%`,
};

export const SERIES_COLOR: Record<string, string> = {
  edgeMs: '#38BDF8',
  cloudMs: '#A78BFA',
  schedulerMs: '#FBBF24',
  totalMs: '#34D399',
  edgeCpu: '#38BDF8',
  edgeRam: '#0EA5E9',
  edgeDisk: '#0B7EA8',
  cloudCpu: '#A78BFA',
  cloudRam: '#8B5CF6',
  cloudDisk: '#7C3AED',
};

function formatTime(t: number): string {
  return new Date(t).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
}

export function DarkTooltip({ active, payload, label }: TooltipProps<number, string>) {
  if (!active || !payload || payload.length === 0) return null;
  const ts = typeof label === 'number' ? label : Number(label);
  return (
    <div className="rounded-lg border border-line-strong bg-panel/95 px-3 py-2 shadow-pop">
      <div className="mb-1.5 text-[10px] uppercase tracking-[0.09em] text-ink-dim">
        {Number.isFinite(ts) ? formatTime(ts) : String(label ?? '')}
      </div>
      <div className="space-y-1">
        {payload.map((entry) => {
          const key = String(entry.dataKey ?? entry.name ?? '');
          const formatter = FORMATTERS[key];
          const value = Number(entry.value);
          return (
            <div key={key} className="flex items-center justify-between gap-4 text-[11px]">
              <span className="flex items-center gap-1.5 text-ink-muted">
                <span className="h-2 w-2 rounded-sm" style={{ backgroundColor: entry.color }} />
                {entry.name}
              </span>
              <span className="font-medium tabular-nums text-ink">{formatter ? formatter(value) : value}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export const axisProps = {
  stroke: '#1A2432',
  tick: { fill: '#64748B', fontSize: 10 },
  tickLine: false,
  axisLine: { stroke: '#1A2432' },
} as const;

export const gridProps = {
  stroke: '#16202C',
  strokeDasharray: '3 3',
  vertical: false,
} as const;

import type { ReactNode } from 'react';
import type { LucideIcon } from 'lucide-react';
import { Skeleton } from './States';

export type MetricTone = 'brand' | 'ok' | 'warn' | 'bad' | 'violet' | 'info' | 'neutral';

const TONE_TEXT: Record<MetricTone, string> = {
  brand: 'text-brand',
  ok: 'text-ok',
  warn: 'text-warn',
  bad: 'text-bad',
  violet: 'text-violet',
  info: 'text-info',
  neutral: 'text-ink',
};

interface MetricCardProps {
  label: string;
  value: ReactNode;
  unit?: string;
  sub?: ReactNode;
  icon?: LucideIcon;
  tone?: MetricTone;
  footer?: ReactNode;
  loading?: boolean;
  className?: string;
}

export function MetricCard({ label, value, unit, sub, icon: Icon, tone = 'neutral', footer, loading, className = '' }: MetricCardProps) {
  return (
    <div className={`group rounded-xl border border-line bg-panel p-4 shadow-card transition hover:border-line-strong ${className}`}>
      <div className="flex items-start justify-between gap-3">
        <span className="text-[11px] font-medium uppercase tracking-[0.09em] text-ink-dim">{label}</span>
        {Icon && (
          <span className={`inline-flex h-7 w-7 items-center justify-center rounded-md border border-line bg-raised ${TONE_TEXT[tone]}`}>
            <Icon className="h-4 w-4" />
          </span>
        )}
      </div>

      {loading ? (
        <Skeleton className="mt-3 h-8 w-28" />
      ) : (
        <div className="mt-2.5 flex items-baseline gap-1.5">
          <span className={`text-2xl font-semibold tracking-tight tabular-nums ${TONE_TEXT[tone]}`}>{value}</span>
          {unit && <span className="text-xs font-medium text-ink-dim">{unit}</span>}
        </div>
      )}

      {sub && <div className="mt-1 text-xs leading-relaxed text-ink-muted">{sub}</div>}
      {footer && <div className="mt-3 border-t border-line pt-2.5 text-[11px] text-ink-dim">{footer}</div>}
    </div>
  );
}

export function StatStrip({ items }: { items: { label: string; value: ReactNode; tone?: MetricTone }[] }) {
  return (
    <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
      {items.map((item) => (
        <div key={item.label} className="min-w-0">
          <div className="text-[11px] uppercase tracking-[0.09em] text-ink-dim">{item.label}</div>
          <div className={`mt-0.5 text-sm font-semibold tabular-nums ${TONE_TEXT[item.tone ?? 'neutral']}`}>{item.value}</div>
        </div>
      ))}
    </div>
  );
}

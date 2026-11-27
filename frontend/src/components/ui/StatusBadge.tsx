import type { ReactNode } from 'react';

export type Tone = 'ok' | 'warn' | 'bad' | 'info' | 'brand' | 'violet' | 'neutral';

const TONES: Record<Tone, { dot: string; text: string; border: string; bg: string }> = {
  ok: { dot: 'bg-ok', text: 'text-ok', border: 'border-ok/30', bg: 'bg-ok/10' },
  warn: { dot: 'bg-warn', text: 'text-warn', border: 'border-warn/30', bg: 'bg-warn/10' },
  bad: { dot: 'bg-bad', text: 'text-bad', border: 'border-bad/30', bg: 'bg-bad/10' },
  info: { dot: 'bg-info', text: 'text-info', border: 'border-info/30', bg: 'bg-info/10' },
  brand: { dot: 'bg-brand', text: 'text-brand', border: 'border-brand/30', bg: 'bg-brand/10' },
  violet: { dot: 'bg-violet', text: 'text-violet', border: 'border-violet/30', bg: 'bg-violet/10' },
  neutral: { dot: 'bg-ink-dim', text: 'text-ink-muted', border: 'border-line-strong', bg: 'bg-raised' },
};

/** Map backend / Kubernetes status strings to a visual tone. */
export function toneForStatus(status: string | null | undefined): Tone {
  if (!status) return 'neutral';
  const value = status.toLowerCase();
  if (['ok', 'ready', 'running', 'success', 'healthy', 'true'].includes(value)) return 'ok';
  if (['degraded', 'pending', 'warning', 'queued', 'fallback', 'notready'].includes(value)) return 'warn';
  if (['error', 'failed', 'crashloopbackoff', 'unhealthy', 'false'].includes(value)) return 'bad';
  if (value === 'edge') return 'brand';
  if (value === 'cloud') return 'violet';
  return 'neutral';
}

interface StatusBadgeProps {
  label: string;
  tone?: Tone;
  pulse?: boolean;
  className?: string;
}

export function StatusBadge({ label, tone = 'neutral', pulse = false, className = '' }: StatusBadgeProps) {
  const style = TONES[tone];
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-md border px-2 py-0.5 text-[11px] font-medium ${style.border} ${style.bg} ${style.text} ${className}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${style.dot} ${pulse ? 'animate-pulse' : ''}`} />
      {label}
    </span>
  );
}

export function Pill({ label, tone = 'neutral', className = '' }: StatusBadgeProps) {
  const style = TONES[tone];
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[11px] font-medium tabular-nums ${style.border} ${style.bg} ${style.text} ${className}`}
    >
      {label}
    </span>
  );
}

export function TargetBadge({ target }: { target: string }) {
  const tone = toneForStatus(target);
  const label = target === 'edge' ? 'EDGE' : target === 'cloud' ? 'CLOUD' : target.toUpperCase();
  return <Pill label={label} tone={tone} />;
}

export function Dot({ tone }: { tone: Tone }) {
  return <span className={`inline-block h-2 w-2 rounded-full ${TONES[tone].dot}`} />;
}

export function toneColor(tone: Tone): string {
  switch (tone) {
    case 'ok':
      return '#34D399';
    case 'warn':
      return '#FBBF24';
    case 'bad':
      return '#F87171';
    case 'info':
      return '#60A5FA';
    case 'brand':
      return '#38BDF8';
    case 'violet':
      return '#A78BFA';
    default:
      return '#93A1B5';
  }
}

export function Label({ children, className = '' }: { children: ReactNode; className?: string }) {
  return (
    <span className={`text-[11px] font-medium uppercase tracking-[0.09em] text-ink-dim ${className}`}>{children}</span>
  );
}

interface GaugeProps {
  label: string;
  value: number | null;
  sub?: string;
  size?: number;
  /** Percent thresholds for warn / bad colouring (utilisation style). */
  warnAt?: number;
  badAt?: number;
  suffix?: string;
}

const ARC_COLOR = { ok: '#34D399', warn: '#FBBF24', bad: '#F87171' };

/** Compact circular utilisation gauge (SVG, no chart library). */
export function Gauge({ label, value, sub, size = 116, warnAt = 70, badAt = 85, suffix = '%' }: GaugeProps) {
  const stroke = 9;
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const pct = value === null ? 0 : Math.min(100, Math.max(0, value));
  const color = value === null ? '#64748B' : pct >= badAt ? ARC_COLOR.bad : pct >= warnAt ? ARC_COLOR.warn : ARC_COLOR.ok;

  return (
    <div className="flex flex-col items-center">
      <div className="relative" style={{ width: size, height: size }}>
        <svg width={size} height={size} className="-rotate-90">
          <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke="#1A2432" strokeWidth={stroke} />
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="none"
            stroke={color}
            strokeWidth={stroke}
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={circumference - (pct / 100) * circumference}
            style={{ transition: 'stroke-dashoffset 500ms ease, stroke 300ms ease' }}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-xl font-semibold tabular-nums text-ink">
            {value === null ? '—' : value.toFixed(0)}
            {value === null ? '' : suffix}
          </span>
          <span className="text-[10px] uppercase tracking-[0.1em] text-ink-dim">{label}</span>
        </div>
      </div>
      {sub && <div className="mt-2 text-center text-[11px] tabular-nums text-ink-muted">{sub}</div>}
    </div>
  );
}

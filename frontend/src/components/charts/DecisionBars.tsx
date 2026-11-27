interface DecisionBarsProps {
  data: { target: string; count: number }[];
}

const TARGET_STYLES: Record<string, { bar: string; text: string }> = {
  edge: { bar: 'bg-brand', text: 'text-brand' },
  cloud: { bar: 'bg-violet', text: 'text-violet' },
  queue: { bar: 'bg-warn', text: 'text-warn' },
  error: { bar: 'bg-bad', text: 'text-bad' },
};

/**
 * Placement decision breakdown. Rendered as plain bars (no chart library) so
 * tiny counts such as queue/error stay visible next to a dominant edge bar.
 */
export function DecisionBars({ data }: DecisionBarsProps) {
  const max = Math.max(1, ...data.map((item) => item.count));
  const total = data.reduce((sum, item) => sum + item.count, 0) || 1;

  return (
    <ul className="space-y-3">
      {data.map((item) => {
        const style = TARGET_STYLES[item.target] ?? { bar: 'bg-ink-dim', text: 'text-ink-muted' };
        const pct = (item.count / total) * 100;
        return (
          <li key={item.target}>
            <div className="flex items-center justify-between text-[11px]">
              <span className={`font-semibold tracking-wider ${style.text}`}>{item.target.toUpperCase()}</span>
              <span className="tabular-nums text-ink-muted">
                {item.count}
                <span className="ml-1.5 text-ink-dim">{pct.toFixed(1)}%</span>
              </span>
            </div>
            <div className="mt-1.5 h-2 overflow-hidden rounded-full bg-raised">
              <div
                className={`h-full rounded-full ${style.bar}`}
                style={{ width: `${Math.max(item.count > 0 ? 3 : 0, (item.count / max) * 100)}%` }}
              />
            </div>
          </li>
        );
      })}
    </ul>
  );
}

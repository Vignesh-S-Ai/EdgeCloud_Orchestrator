import type { ReactNode } from 'react';
import { Cloud, Cpu, Server, Waypoints } from 'lucide-react';
import type { Target } from '../../types';

interface RouteFlowProps {
  lastTarget: Target | null;
  edgeSharePct: number | null;
  edgeMs: number | null;
  cloudMs: number | null;
  sourceNote: string;
}

/**
 * Edge <-> Cloud routing visualization: ingress -> scheduler -> chosen node.
 * The active path (based on the most recent decision) is highlighted.
 */
export function RouteFlow({ lastTarget, edgeSharePct, edgeMs, cloudMs, sourceNote }: RouteFlowProps) {
  const ranOnEdge = lastTarget === 'edge';
  const ranOnCloud = lastTarget === 'cloud';

  return (
    <div className="rounded-lg border border-line bg-raised/40 p-4">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-stretch lg:gap-0">
        <FlowNode
          icon={<Server className="h-4 w-4" />}
          title="Client request"
          subtitle="POST /orchestrate"
          tone="neutral"
          active
        />

        <Connector label="ingress" active />

        <FlowNode
          icon={<Waypoints className="h-4 w-4" />}
          title="Scheduler"
          subtitle="POST /decision · rule_based"
          tone="brand"
          active
        />

        <Connector label="placement" active={lastTarget === 'edge' || lastTarget === 'cloud'} />

        <div className="flex flex-1 flex-col gap-3">
          <FlowNode
            icon={<Cpu className="h-4 w-4" />}
            title="Edge node"
            subtitle={edgeMs !== null ? `/detect · ${edgeMs.toFixed(0)} ms avg` : '/detect'}
            tone="brand"
            active={ranOnEdge}
            share={edgeSharePct !== null ? `${Math.round(edgeSharePct)}%` : undefined}
          />
          <FlowNode
            icon={<Cloud className="h-4 w-4" />}
            title="Cloud node"
            subtitle={cloudMs !== null ? `/infer · ${cloudMs.toFixed(0)} ms avg` : '/infer'}
            tone="violet"
            active={ranOnCloud}
            share={edgeSharePct !== null ? `${Math.round(100 - edgeSharePct)}%` : undefined}
          />
        </div>
      </div>

      <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-line pt-3 text-[11px] text-ink-dim">
        <span>
          Highlighted path = destination of the most recent decision
          {lastTarget ? ` (${lastTarget.toUpperCase()})` : ''}
        </span>
        <span>{sourceNote}</span>
      </div>
    </div>
  );
}

function Connector({ label, active }: { label: string; active: boolean }) {
  const color = active ? 'bg-brand/60' : 'bg-line-strong';
  return (
    <div className="relative flex shrink-0 items-center lg:w-20">
      <div className={`h-px w-full ${color} ${active ? '' : 'opacity-50'}`} />
      <span className="absolute left-1/2 top-0 -translate-x-1/2 -translate-y-1/2 whitespace-nowrap rounded border border-line bg-raised px-1 py-px text-[9px] uppercase tracking-[0.12em] text-ink-dim">
        {label}
      </span>
    </div>
  );
}

function FlowNode({
  icon,
  title,
  subtitle,
  tone,
  active,
  share,
}: {
  icon: ReactNode;
  title: string;
  subtitle: string;
  tone: 'brand' | 'violet' | 'neutral';
  active: boolean;
  share?: string;
}) {
  const palette =
    tone === 'brand'
      ? { text: 'text-brand', border: 'border-brand/45', bg: 'bg-brand/[0.08]', glow: 'shadow-[0_0_0_1px_rgba(56,189,248,0.18)]' }
      : tone === 'violet'
        ? { text: 'text-violet', border: 'border-violet/45', bg: 'bg-violet/[0.08]', glow: 'shadow-[0_0_0_1px_rgba(167,139,250,0.18)]' }
        : { text: 'text-ink-muted', border: 'border-line-strong', bg: 'bg-panel', glow: '' };

  return (
    <div
      className={`flex min-w-0 flex-1 items-center gap-3 rounded-lg border px-3 py-2.5 transition ${
        active ? `${palette.border} ${palette.bg} ${palette.glow}` : 'border-line bg-panel opacity-70'
      }`}
    >
      <span className={`inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md border ${palette.border} ${palette.text}`}>
        {icon}
      </span>
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <span className="truncate text-xs font-semibold text-ink">{title}</span>
          {share && <span className={`text-[10px] font-semibold tabular-nums ${palette.text}`}>{share}</span>}
        </div>
        <div className="truncate font-mono text-[10px] text-ink-dim">{subtitle}</div>
      </div>
    </div>
  );
}

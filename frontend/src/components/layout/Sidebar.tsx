import { NavLink } from 'react-router-dom';
import type { ReactNode } from 'react';
import { Activity, Database, Radio, X } from 'lucide-react';
import { NAV_SECTIONS } from '../../config/navigation';
import { useData } from '../../context/DataSourceContext';

interface SidebarProps {
  open: boolean;
  onClose: () => void;
}

export function Sidebar({ open, onClose }: SidebarProps) {
  const { mode, endpoints, refreshMs } = useData();

  return (
    <>
      {open && <div className="fixed inset-0 z-30 bg-black/60 lg:hidden" onClick={onClose} aria-hidden="true" />}

      <aside
        className={`fixed inset-y-0 left-0 z-40 flex w-[264px] flex-col border-r border-line bg-panel transition-transform duration-200 lg:static lg:translate-x-0 ${
          open ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        <div className="flex h-16 items-center gap-3 border-b border-line px-5">
          <span className="relative inline-flex h-9 w-9 items-center justify-center rounded-lg border border-brand/30 bg-brand/10 text-brand">
            <Activity className="h-5 w-5" />
          </span>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="text-sm font-semibold tracking-tight text-ink">CLOUD-13</span>
              <span className="rounded border border-line-strong px-1 py-px text-[9px] font-semibold tracking-wider text-ink-dim">
                v0.1.0
              </span>
            </div>
            <div className="truncate text-[11px] text-ink-dim">Edge-Cloud Orchestration</div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="ml-auto rounded-md p-1 text-ink-muted hover:bg-raised lg:hidden"
            aria-label="Close navigation"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <nav className="flex-1 overflow-y-auto px-3 py-4">
          {NAV_SECTIONS.map((section) => (
            <div key={section.section} className="mb-5">
              <div className="px-2 pb-2 text-[10px] font-semibold uppercase tracking-[0.14em] text-ink-dim">
                {section.section}
              </div>
              <ul className="space-y-0.5">
                {section.items.map((item) => (
                  <li key={item.to}>
                    <NavLink
                      to={item.to}
                      end={item.end}
                      onClick={onClose}
                      className={({ isActive }) =>
                        `group flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-[13px] font-medium transition ${
                          isActive
                            ? 'bg-brand/10 text-brand ring-1 ring-brand/25'
                            : 'text-ink-muted hover:bg-raised hover:text-ink'
                        }`
                      }
                    >
                      <item.icon className="h-4 w-4 shrink-0" />
                      <span className="truncate">{item.label}</span>
                    </NavLink>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </nav>

        <div className="border-t border-line px-4 py-4">
          <div className="flex items-center gap-2">
            <span
              className={`inline-flex h-2 w-2 rounded-full ${
                mode === 'live' ? 'bg-ok' : 'bg-warn'
              }`}
            />
            <span className="text-[11px] font-semibold uppercase tracking-[0.1em] text-ink-muted">
              {mode === 'live' ? 'LIVE BACKEND' : 'DEMO DATA'}
            </span>
          </div>

          <dl className="mt-3 space-y-1.5 text-[11px]">
            <EndpointRow icon={<Radio className="h-3 w-3" />} label="Orchestrator" value={endpoints.orchestrator} />
            <EndpointRow icon={<Activity className="h-3 w-3" />} label="Edge" value={endpoints.edge} />
            <EndpointRow icon={<Database className="h-3 w-3" />} label="Cloud" value={endpoints.cloud} />
            <EndpointRow icon={<Activity className="h-3 w-3" />} label="Scheduler" value={endpoints.scheduler} />
          </dl>

          <p className="mt-3 text-[10px] leading-relaxed text-ink-dim">
            Auto refresh every {Math.round(refreshMs / 1000)}s · read-only dashboard
          </p>
        </div>
      </aside>
    </>
  );
}

function EndpointRow({ icon, label, value }: { icon: ReactNode; label: string; value: string }) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-ink-dim">{icon}</span>
      <dt className="w-16 shrink-0 text-ink-dim">{label}</dt>
      <dd className="min-w-0 flex-1 truncate font-mono text-[10px] text-ink-muted" title={value}>
        {value.replace(/^https?:\/\//, '')}
      </dd>
    </div>
  );
}

import { useMemo, useState } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import { ROUTE_META } from '../../config/navigation';
import { useData } from '../../context/DataSourceContext';
import { useAsync } from '../../hooks/useAsync';
import { Sidebar } from './Sidebar';
import { TopBar } from './TopBar';

export function AppShell() {
  const [navOpen, setNavOpen] = useState(false);
  const location = useLocation();
  const { source, refreshMs } = useData();

  const meta = ROUTE_META[location.pathname] ?? {
    title: 'CLOUD-13',
    subtitle: 'Edge-Cloud Orchestration',
  };

  // Keeps a heartbeat going so the top bar shows a real "last updated" time
  // and pages that poll independently stay in the same refresh cycle.
  const heartbeat = useAsync(() => Promise.resolve(Date.now()), [source], { intervalMs: refreshMs });

  const footer = useMemo(
    () => (
      <footer className="border-t border-line px-4 py-4 text-[11px] text-ink-dim sm:px-6 lg:px-8">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span>
            CLOUD-13 dashboard · data source:{' '}
            <span className={source.mode === 'live' ? 'text-ok' : 'text-warn'}>{source.label}</span>
          </span>
          <span className="hidden sm:inline">{source.hint}</span>
        </div>
      </footer>
    ),
    [source],
  );

  return (
    <div className="flex min-h-screen bg-base text-ink">
      <Sidebar open={navOpen} onClose={() => setNavOpen(false)} />

      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar
          title={meta.title}
          subtitle={meta.subtitle}
          onMenu={() => setNavOpen(true)}
          updated={heartbeat.updated}
          refreshing={heartbeat.refreshing}
        />

        <main className="flex-1 px-4 py-6 sm:px-6 lg:px-8">
          <Outlet />
        </main>

        {footer}
      </div>
    </div>
  );
}

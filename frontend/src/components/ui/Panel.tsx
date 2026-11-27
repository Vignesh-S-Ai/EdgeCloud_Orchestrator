import type { ReactNode } from 'react';

interface PanelProps {
  title?: string;
  subtitle?: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
}

export function Panel({ title, subtitle, actions, children, className = '', bodyClassName = 'p-5' }: PanelProps) {
  const hasHeader = Boolean(title || actions);
  return (
    <section className={`flex flex-col rounded-xl border border-line bg-panel shadow-card ${className}`}>
      {hasHeader && (
        <header className="flex flex-wrap items-start justify-between gap-x-4 gap-y-3 border-b border-line px-5 py-3.5">
          <div className="min-w-0 flex-1 basis-56">
            {title && <h3 className="text-[13px] font-semibold tracking-wide text-ink">{title}</h3>}
            {subtitle && <p className="mt-0.5 text-xs text-ink-dim">{subtitle}</p>}
          </div>
          {actions && <div className="flex flex-1 flex-wrap items-center justify-start gap-2 sm:flex-none sm:justify-end">{actions}</div>}
        </header>
      )}
      <div className={`${bodyClassName} flex-1`}>{children}</div>
    </section>
  );
}

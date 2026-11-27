import type { ReactNode } from 'react';
import { AlertTriangle, Database, Inbox, RefreshCw, ServerOff } from 'lucide-react';
import { NO_ENDPOINT_REASON } from '../../config/env';

export function Skeleton({ className = '' }: { className?: string }) {
  return <div className={`animate-pulse rounded-md bg-raised ${className}`} />;
}

export function CardSkeleton() {
  return (
    <div className="rounded-xl border border-line bg-panel p-5">
      <Skeleton className="h-3 w-24" />
      <Skeleton className="mt-4 h-7 w-32" />
      <Skeleton className="mt-3 h-3 w-40" />
    </div>
  );
}

export function LoadingState({ label = 'Loading…', rows = 4 }: { label?: string; rows?: number }) {
  return (
    <div className="space-y-3" role="status" aria-live="polite">
      <div className="flex items-center gap-2 text-xs text-ink-dim">
        <RefreshCw className="h-3.5 w-3.5 animate-spin" />
        {label}
      </div>
      {Array.from({ length: rows }).map((_, index) => (
        <Skeleton key={index} className="h-10 w-full" />
      ))}
    </div>
  );
}

export function LoadingGrid({ count = 6 }: { count?: number }) {
  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3" role="status" aria-live="polite">
      {Array.from({ length: count }).map((_, index) => (
        <CardSkeleton key={index} />
      ))}
    </div>
  );
}

interface MessageStateProps {
  title?: string;
  description: ReactNode;
  action?: ReactNode;
}

export function ErrorState({ title = 'Unable to load data', description, action, onRetry }: MessageStateProps & { onRetry?: () => void }) {
  return (
    <div className="flex min-h-[180px] flex-col items-center justify-center rounded-xl border border-bad/30 bg-bad/[0.04] px-6 py-10 text-center">
      <span className="mb-3 inline-flex h-10 w-10 items-center justify-center rounded-lg border border-bad/30 bg-bad/10 text-bad">
        <ServerOff className="h-5 w-5" />
      </span>
      <h3 className="text-sm font-semibold text-ink">{title}</h3>
      <p className="mt-1.5 max-w-lg break-words text-xs leading-relaxed text-ink-muted">{description}</p>
      <div className="mt-4 flex items-center gap-2">
        {action}
        {onRetry && (
          <button
            type="button"
            onClick={onRetry}
            className="inline-flex items-center gap-1.5 rounded-md border border-line-strong bg-raised px-3 py-1.5 text-xs font-medium text-ink transition hover:border-brand/40 hover:text-brand"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            Retry
          </button>
        )}
      </div>
    </div>
  );
}

export function EmptyState({ title, description, action }: MessageStateProps) {
  return (
    <div className="flex min-h-[180px] flex-col items-center justify-center rounded-xl border border-dashed border-line bg-panel/60 px-6 py-10 text-center">
      <span className="mb-3 inline-flex h-10 w-10 items-center justify-center rounded-lg border border-line-strong bg-raised text-ink-muted">
        <Inbox className="h-5 w-5" />
      </span>
      <h3 className="text-sm font-semibold text-ink">{title}</h3>
      <p className="mt-1.5 max-w-lg text-xs leading-relaxed text-ink-muted">{description}</p>
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

/**
 * Rendered where the live backend simply has no endpoint for a view - never
 * shows invented numbers as if they were production metrics.
 */
export function NoLiveData({ reason = NO_ENDPOINT_REASON, onEnableDemo }: { reason?: string; onEnableDemo?: () => void }) {
  return (
    <div className="flex min-h-[220px] flex-col items-center justify-center rounded-xl border border-dashed border-line-strong bg-raised/40 px-6 py-10 text-center">
      <span className="mb-3 inline-flex h-10 w-10 items-center justify-center rounded-lg border border-line-strong bg-raised text-ink-muted">
        <Database className="h-5 w-5" />
      </span>
      <h3 className="text-sm font-semibold text-ink">No live endpoint for this view</h3>
      <p className="mt-1.5 max-w-xl text-xs leading-relaxed text-ink-muted">{reason}</p>
      {onEnableDemo && (
        <button
          type="button"
          onClick={onEnableDemo}
          className="mt-4 inline-flex items-center gap-1.5 rounded-md border border-brand/40 bg-brand/10 px-3 py-1.5 text-xs font-medium text-brand transition hover:bg-brand/20"
        >
          <Database className="h-3.5 w-3.5" />
          Show labelled demo data
        </button>
      )}
    </div>
  );
}

export function InlineNote({ children, tone = 'info' }: { children: ReactNode; tone?: 'info' | 'warn' }) {
  const style =
    tone === 'warn' ? 'border-warn/30 bg-warn/[0.06] text-warn' : 'border-info/30 bg-info/[0.06] text-info';
  return (
    <div className={`flex items-start gap-2 rounded-lg border px-3 py-2 text-xs leading-relaxed ${style}`}>
      <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
      <span>{children}</span>
    </div>
  );
}

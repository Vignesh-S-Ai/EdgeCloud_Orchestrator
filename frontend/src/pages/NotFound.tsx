import { Link } from 'react-router-dom';
import { Compass } from 'lucide-react';

export function NotFoundPage() {
  return (
    <div className="flex min-h-[50vh] flex-col items-center justify-center text-center">
      <span className="mb-4 inline-flex h-12 w-12 items-center justify-center rounded-xl border border-line bg-panel text-brand">
        <Compass className="h-6 w-6" />
      </span>
      <h2 className="text-lg font-semibold text-ink">Page not found</h2>
      <p className="mt-1 text-sm text-ink-muted">That route does not exist in the CLOUD-13 dashboard.</p>
      <Link
        to="/"
        className="mt-5 rounded-lg border border-brand/40 bg-brand/10 px-4 py-2 text-sm font-medium text-brand transition hover:bg-brand/20"
      >
        Back to Overview
      </Link>
    </div>
  );
}

/** Display helpers shared by every page. */

export const formatMs = (value: number | null | undefined, digits = 0): string => {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  if (value >= 1000) return `${(value / 1000).toFixed(2)} s`;
  return `${value.toFixed(digits)} ms`;
};

export const formatPct = (value: number | null | undefined, digits = 1): string =>
  value === null || value === undefined || Number.isNaN(value) ? '—' : `${value.toFixed(digits)}%`;

export const formatNumber = (value: number | null | undefined): string =>
  value === null || value === undefined || Number.isNaN(value)
    ? '—'
    : value.toLocaleString('en-US', { maximumFractionDigits: 0 });

export const formatCompact = (value: number | null | undefined): string => {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}k`;
  return value.toFixed(0);
};

export const formatGb = (value: number | null | undefined): string =>
  value === null || value === undefined ? '—' : `${value.toFixed(1)} GB`;

export const formatTime = (ts: number): string =>
  new Date(ts).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', second: '2-digit' });

export const formatClock = (ts: number): string =>
  new Date(ts).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });

export const formatDateTime = (ts: number): string =>
  new Date(ts).toLocaleString('en-GB', {
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });

export const timeAgo = (ts: number, now: number = Date.now()): string => {
  const seconds = Math.max(0, Math.round((now - ts) / 1000));
  if (seconds < 5) return 'just now';
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
};

export const formatUptime = (seconds: number | null | undefined): string => {
  if (seconds === null || seconds === undefined) return '—';
  const total = Math.max(0, Math.floor(seconds));
  const days = Math.floor(total / 86400);
  const hours = Math.floor((total % 86400) / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  if (days > 0) return `${days}d ${hours}h`;
  if (hours > 0) return `${hours}h ${minutes}m`;
  return `${minutes}m`;
};

export const percentile = (values: number[], p: number): number | null => {
  if (values.length === 0) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const index = Math.min(sorted.length - 1, Math.max(0, Math.ceil((p / 100) * sorted.length) - 1));
  return sorted[index];
};

export const average = (values: number[]): number | null =>
  values.length === 0 ? null : values.reduce((sum, value) => sum + value, 0) / values.length;

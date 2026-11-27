import type { ReactNode } from 'react';
import { Search } from 'lucide-react';

interface Option<T extends string> {
  value: T;
  label: string;
  count?: number;
}

export function SegmentedControl<T extends string>({
  value,
  onChange,
  options,
  size = 'md',
}: {
  value: T;
  onChange: (value: T) => void;
  options: Option<T>[];
  size?: 'sm' | 'md';
}) {
  const pad = size === 'sm' ? 'px-2 py-1 text-[11px]' : 'px-2.5 py-1.5 text-xs';
  return (
    <div className="inline-flex items-center gap-0.5 rounded-lg border border-line bg-raised p-0.5">
      {options.map((option) => {
        const active = option.value === value;
        return (
          <button
            key={option.value}
            type="button"
            onClick={() => onChange(option.value)}
            className={`${pad} rounded-md font-medium transition ${
              active ? 'bg-panel text-ink shadow-sm ring-1 ring-line-strong' : 'text-ink-muted hover:text-ink'
            }`}
          >
            {option.label}
            {option.count !== undefined && (
              <span className={`ml-1.5 tabular-nums ${active ? 'text-brand' : 'text-ink-dim'}`}>{option.count}</span>
            )}
          </button>
        );
      })}
    </div>
  );
}

export function Select<T extends string>({
  value,
  onChange,
  options,
  label,
}: {
  value: T;
  onChange: (value: T) => void;
  options: Option<T>[];
  label?: string;
}) {
  return (
    <label className="inline-flex items-center gap-2">
      {label && <span className="text-[11px] uppercase tracking-[0.09em] text-ink-dim">{label}</span>}
      <select
        value={value}
        onChange={(event) => onChange(event.target.value as T)}
        className="rounded-lg border border-line bg-raised px-2.5 py-1.5 text-xs font-medium text-ink outline-none transition focus:border-brand/50"
      >
        {options.map((option) => (
          <option key={option.value} value={option.value} className="bg-panel">
            {option.label}
          </option>
        ))}
      </select>
    </label>
  );
}

export function SearchInput({
  value,
  onChange,
  placeholder = 'Search…',
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
}) {
  return (
    <div className="relative">
      <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-ink-dim" />
      <input
        type="search"
        value={value}
        placeholder={placeholder}
        onChange={(event) => onChange(event.target.value)}
        className="w-56 rounded-lg border border-line bg-raised py-1.5 pl-8 pr-3 text-xs text-ink placeholder:text-ink-dim outline-none transition focus:border-brand/50"
      />
    </div>
  );
}

export function Toolbar({ children }: { children: ReactNode }) {
  return <div className="flex flex-wrap items-center gap-2">{children}</div>;
}

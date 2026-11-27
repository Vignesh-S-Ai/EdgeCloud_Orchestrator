import type { ReactNode } from 'react';

export function TableShell({ children, className = '' }: { children: ReactNode; className?: string }) {
  return (
    <div className={`overflow-x-auto ${className}`}>
      <table className="w-full min-w-[640px] border-collapse text-left text-xs">{children}</table>
    </div>
  );
}

export function Th({ children, className = '' }: { children?: ReactNode; className?: string }) {
  return (
    <th
      className={`whitespace-nowrap border-b border-line bg-raised/60 px-4 py-2.5 text-[10px] font-semibold uppercase tracking-[0.09em] text-ink-dim ${className}`}
    >
      {children}
    </th>
  );
}

export function Td({ children, className = '' }: { children?: ReactNode; className?: string }) {
  return <td className={`border-b border-line/70 px-4 py-2.5 align-middle text-ink-muted ${className}`}>{children}</td>;
}

export function Tr({ children, onClick }: { children: ReactNode; onClick?: () => void }) {
  return (
    <tr
      onClick={onClick}
      className={`transition ${onClick ? 'cursor-pointer hover:bg-raised/70' : 'hover:bg-raised/40'} last:border-0`}
    >
      {children}
    </tr>
  );
}

export function Mono({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <span className={`font-mono text-[11px] tabular-nums ${className}`}>{children}</span>;
}

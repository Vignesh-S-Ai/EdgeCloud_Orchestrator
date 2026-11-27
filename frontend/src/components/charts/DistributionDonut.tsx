import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts';

interface Slice {
  name: string;
  value: number;
  color: string;
}

export function DistributionDonut({
  data,
  centerLabel,
  centerValue,
  height = 220,
}: {
  data: Slice[];
  centerLabel: string;
  centerValue: string;
  height?: number;
}) {
  const total = data.reduce((sum, slice) => sum + slice.value, 0);
  return (
    <div className="relative">
      <ResponsiveContainer width="100%" height={height}>
        <PieChart>
          <Pie
            data={data}
            dataKey="value"
            nameKey="name"
            innerRadius="68%"
            outerRadius="94%"
            paddingAngle={2}
            stroke="#0C121A"
            strokeWidth={2}
          >
            {data.map((slice) => (
              <Cell key={slice.name} fill={slice.color} />
            ))}
          </Pie>
          <Tooltip
            contentStyle={{
              background: '#0C121A',
              border: '1px solid #263244',
              borderRadius: 8,
              fontSize: 11,
              color: '#E7EEF7',
            }}
            itemStyle={{ color: '#E7EEF7' }}
            formatter={(value: number, name: string) => [`${value} requests`, name]}
          />
        </PieChart>
      </ResponsiveContainer>
      <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-2xl font-semibold tabular-nums text-ink">{centerValue}</span>
        <span className="mt-0.5 text-[10px] uppercase tracking-[0.1em] text-ink-dim">{centerLabel}</span>
        <span className="mt-1 text-[11px] tabular-nums text-ink-muted">{total.toLocaleString('en-US')} total</span>
      </div>
    </div>
  );
}

import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import type { ResourcePoint } from '../../types';
import { axisProps, gridProps, DarkTooltip, SERIES_COLOR } from './chartTheme';

export function UtilizationChart({ data, height = 240 }: { data: ResourcePoint[]; height?: number }) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={{ top: 8, right: 8, left: -14, bottom: 0 }}>
        <CartesianGrid {...gridProps} />
        <XAxis
          dataKey="t"
          type="number"
          domain={['dataMin', 'dataMax']}
          {...axisProps}
          tickFormatter={(value: number) =>
            new Date(value).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })
          }
          minTickGap={44}
        />
        <YAxis {...axisProps} unit="%" domain={[0, 100]} width={48} />
        <Tooltip content={<DarkTooltip />} />
        <Legend wrapperStyle={{ fontSize: 11, color: '#93A1B5', paddingTop: 6 }} iconType="square" iconSize={8} />
        <Line type="monotone" dataKey="edgeCpu" name="Edge CPU" stroke={SERIES_COLOR.edgeCpu} strokeWidth={2} dot={false} />
        <Line
          type="monotone"
          dataKey="edgeRam"
          name="Edge RAM"
          stroke={SERIES_COLOR.edgeRam}
          strokeWidth={1.6}
          strokeDasharray="5 4"
          dot={false}
        />
        <Line type="monotone" dataKey="cloudCpu" name="Cloud CPU" stroke={SERIES_COLOR.cloudCpu} strokeWidth={2} dot={false} />
        <Line
          type="monotone"
          dataKey="cloudRam"
          name="Cloud RAM"
          stroke={SERIES_COLOR.cloudRam}
          strokeWidth={1.6}
          strokeDasharray="5 4"
          dot={false}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}

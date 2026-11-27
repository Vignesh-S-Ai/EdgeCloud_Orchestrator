import {
  Area,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { LatencyPoint } from '../../types';
import { axisProps, gridProps, DarkTooltip, SERIES_COLOR } from './chartTheme';

export function LatencyTrendChart({ data, height = 240 }: { data: LatencyPoint[]; height?: number }) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <ComposedChart data={data} margin={{ top: 8, right: 8, left: -14, bottom: 0 }}>
        <defs>
          <linearGradient id="edgeFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={SERIES_COLOR.edgeMs} stopOpacity={0.28} />
            <stop offset="100%" stopColor={SERIES_COLOR.edgeMs} stopOpacity={0.02} />
          </linearGradient>
          <linearGradient id="cloudFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={SERIES_COLOR.cloudMs} stopOpacity={0.24} />
            <stop offset="100%" stopColor={SERIES_COLOR.cloudMs} stopOpacity={0.02} />
          </linearGradient>
        </defs>
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
        <YAxis {...axisProps} unit=" ms" width={62} />
        <Tooltip content={<DarkTooltip />} />
        <Legend
          wrapperStyle={{ fontSize: 11, color: '#93A1B5', paddingTop: 6 }}
          iconType="square"
          iconSize={8}
        />
        <Area
          type="monotone"
          dataKey="edgeMs"
          name="Edge inference"
          stroke={SERIES_COLOR.edgeMs}
          strokeWidth={2}
          fill="url(#edgeFill)"
          dot={false}
          activeDot={{ r: 3 }}
        />
        <Area
          type="monotone"
          dataKey="cloudMs"
          name="Cloud inference"
          stroke={SERIES_COLOR.cloudMs}
          strokeWidth={2}
          fill="url(#cloudFill)"
          dot={false}
          activeDot={{ r: 3 }}
        />
        <Line
          type="monotone"
          dataKey="schedulerMs"
          name="Scheduler decision"
          stroke={SERIES_COLOR.schedulerMs}
          strokeWidth={1.6}
          strokeDasharray="5 4"
          dot={false}
        />
      </ComposedChart>
    </ResponsiveContainer>
  );
}

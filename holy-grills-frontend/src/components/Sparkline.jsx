import React from 'react';
import { ResponsiveContainer, Area, AreaChart, Dot } from 'recharts';

/**
 * Sparkline — tiny trend line for dashboards. A smooth area chart with a
 * gradient fill (no axes/grid). The most recent point renders a pulsing dot so
 * the trend reads as a live, fluid value rather than a frozen fill that runs
 * edge-to-edge. Used for the 7-day HP "earned" trend on the Dashboard.
 */
export default function Sparkline({ data, color = '#F72B13', height = 44 }) {
  if (!data || data.length === 0) return null;
  const id = `spark-${color.replace('#', '')}`;
  const lastIndex = data.length - 1;
  // Custom dot renderer — a pulsing ring + solid core on the last (current) point.
  const renderDot = (props) => {
    const { cx, cy, index } = props;
    if (index !== lastIndex) return null;
    return (
      <Dot key={`dot-${index}`} cx={cx} cy={cy} r={0} fill="none">
        <circle cx={cx} cy={cy} r={5} fill={color} opacity={0.3} className="animate-ping" />
        <circle cx={cx} cy={cy} r={3} fill={color} stroke="#fff" strokeWidth={1} />
      </Dot>
    );
  };
  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={data} margin={{ top: 2, right: 4, bottom: 0, left: 0 }}>
        <defs>
          <linearGradient id={id} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity={0.3} />
            <stop offset="100%" stopColor={color} stopOpacity={0} />
          </linearGradient>
        </defs>
        <Area
          type="monotone"
          dataKey="value"
          stroke={color}
          strokeWidth={2}
          fill={`url(#${id})`}
          isAnimationActive
          animationDuration={750}
          dot={renderDot}
          activeDot={false}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}
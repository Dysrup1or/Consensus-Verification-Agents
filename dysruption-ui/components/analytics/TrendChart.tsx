'use client';

export type TrendChartProps = {
  data: { date: string; value: number }[];
  title: string;
  color?: string;
  height?: number;
  valueFormatter?: (v: number) => string;
};

export default function TrendChart({
  data,
  title,
  color = '#3b82f6',
  height = 200,
  valueFormatter = (v) => v.toFixed(1),
}: TrendChartProps) {
  if (!data || data.length === 0) {
    return (
      <div className="bg-zinc-900 rounded-lg border border-zinc-800 p-4" style={{ height: height + 60 }}>
        <h3 className="text-sm font-medium text-zinc-400 mb-4">{title}</h3>
        <div className="flex items-center justify-center h-full text-zinc-500">No data available</div>
      </div>
    );
  }

  const values = data.map((d) => d.value);
  const max = Math.max(...values, 1);
  const min = Math.min(...values, 0);
  const range = max - min || 1;
  const width = 600;
  const padding = 20;

  const chartWidth = width - padding * 2;

  const points = data
    .map((d, i) => {
      const x = padding + (i / (data.length - 1)) * chartWidth;
      const y = height - padding - ((d.value - min) / range) * (height - padding * 2);
      return `${x},${y}`;
    })
    .join(' ');

  return (
    <div className="bg-zinc-900 rounded-lg border border-zinc-800 p-4">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-medium text-zinc-400">{title}</h3>
        <span className="text-sm font-bold text-white">{valueFormatter(data[data.length - 1]?.value ?? 0)}</span>
      </div>
      <svg width="100%" height={height} viewBox={`0 0 ${width} ${height}`} className="overflow-visible">
        {[0, 0.25, 0.5, 0.75, 1].map((t) => (
          <line
            key={t}
            x1={padding}
            y1={padding + t * (height - padding * 2)}
            x2={width - padding}
            y2={padding + t * (height - padding * 2)}
            stroke="#27272a"
            strokeWidth={1}
          />
        ))}
        <polyline points={points} fill="none" stroke={color} strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />
        {data.map((d, i) => {
          const x = padding + (i / (data.length - 1)) * chartWidth;
          const y = height - padding - ((d.value - min) / range) * (height - padding * 2);
          return <circle key={i} cx={x} cy={y} r={3} fill={color} className="hover:r-5 transition-all cursor-pointer" />;
        })}
        {[0, Math.floor(data.length / 2), data.length - 1].map((idx) => {
          const d = data[idx];
          if (!d) return null;
          const x = padding + (idx / (data.length - 1)) * chartWidth;
          const label = d.date.split('T')[0];
          return (
            <text key={idx} x={x} y={height - 5} fill="#71717a" fontSize={10} textAnchor="middle">
              {label}
            </text>
          );
        })}
      </svg>
    </div>
  );
}

'use client';

export type SparklineProps = {
  data: number[];
  color?: string;
  height?: number;
  width?: number;
};

export default function Sparkline({ data, color = '#22c55e', height = 24, width = 80 }: SparklineProps) {
  if (!data || data.length === 0) {
    return <div style={{ width, height }} className="bg-zinc-800 rounded" />;
  }

  const max = Math.max(...data, 1);
  const min = 0;
  const range = max - min || 1;

  const points = data
    .map((value, i) => {
      const x = (i / (data.length - 1)) * width;
      const y = height - ((value - min) / range) * height;
      return `${x},${y}`;
    })
    .join(' ');

  return (
    <svg width={width} height={height} className="overflow-visible">
      <polyline
        points={points}
        fill="none"
        stroke={color}
        strokeWidth={1.5}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

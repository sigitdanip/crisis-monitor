interface SparklineProps {
  data: number[];
  width?: number;
  height?: number;
  color?: string;
  className?: string;
}

export function Sparkline({ data, width = 80, height = 24, color = "#10b981", className = "" }: SparklineProps) {
  if (!data.length) return <div className={`w-[${width}px] h-[${height}px] bg-zinc-900/50 rounded`} />;

  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;

  const points = data.map((v, i) => {
    const x = (i / (data.length - 1)) * (width - 4) + 2;
    const y = height - 4 - ((v - min) / range) * (height - 8) + 2;
    return `${x},${y}`;
  });

  const last = data[data.length - 1];
  const first = data[0];
  const trendColor = last >= first ? "#10b981" : "#ef4444";
  const stroke = color === "auto" ? trendColor : color;

  return (
    <svg width={width} height={height} className={className}>
      <polyline
        points={points.join(" ")}
        fill="none"
        stroke={stroke}
        strokeWidth={1.5}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {data.length > 1 && (
        <circle cx={points[points.length - 1]?.split(",")[0]} cy={points[points.length - 1]?.split(",")[1]} r={2} fill={stroke} />
      )}
    </svg>
  );
}

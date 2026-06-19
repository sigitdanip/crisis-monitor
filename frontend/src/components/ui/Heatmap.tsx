interface HeatmapProps {
  data: { x: number; y: number; value: number }[];
  xLabels: string[];
  yLabels: string[];
  cellSize?: number;
  colorScale?: string[];
}

const DEFAULT_COLORS = ["#18181b", "#f59e0b", "#ef4444"]; // 0: zinc, 1: amber, 2: red

export function Heatmap({ data, xLabels, yLabels, cellSize = 14, colorScale = DEFAULT_COLORS }: HeatmapProps) {
  const maxVal = Math.max(...data.map((d) => d.value), 1);
  const gap = 2;
  const totalW = xLabels.length * (cellSize + gap) + gap + 60;
  const totalH = yLabels.length * (cellSize + gap) + gap + 20;

  return (
    <svg width={totalW} height={totalH} viewBox={`0 0 ${totalW} ${totalH}`} className="font-mono text-[9px]">
      {data.map((cell) => {
        const cx = 60 + cell.x * (cellSize + gap) + gap;
        const cy = 10 + cell.y * (cellSize + gap) + gap;
        const colorIdx = Math.round((cell.value / maxVal) * (colorScale.length - 1));
        return (
          <rect key={`${cell.x}-${cell.y}`} x={cx} y={cy} width={cellSize} height={cellSize} fill={colorScale[colorIdx]} rx={1} />
        );
      })}
      {yLabels.map((label, i) => (
        <text key={`y-${i}`} x={56} y={10 + i * (cellSize + gap) + cellSize / 2 + 3} fill="#71717a" textAnchor="end">
          {label}
        </text>
      ))}
      {xLabels.map((label, i) => (
        <text key={`x-${i}`} x={60 + i * (cellSize + gap) + cellSize / 2 + gap} y={totalH - 2} fill="#71717a" textAnchor="middle">
          {label}
        </text>
      ))}
    </svg>
  );
}

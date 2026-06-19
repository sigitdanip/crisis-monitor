interface DonutChartProps {
  segments: { label: string; value: number; color: string }[];
  size?: number;
  thickness?: number;
  centerLabel?: string;
  centerValue?: string;
}

export function DonutChart({ segments, size = 120, thickness = 18, centerLabel, centerValue }: DonutChartProps) {
  const total = segments.reduce((s, seg) => s + seg.value, 0) || 1;
  const r = (size - thickness) / 2;
  const cx = size / 2;
  const cy = size / 2;
  const circumference = 2 * Math.PI * r;

  let offset = 0;
  const arcs = segments.map((seg) => {
    const pct = seg.value / total;
    const length = pct * circumference;
    const dash = `${length} ${circumference - length}`;
    const arc = { ...seg, dash, dashOffset: -offset };
    offset += length;
    return arc;
  });

  return (
    <div className="relative inline-flex items-center justify-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        {arcs.map((arc) => (
          <circle
            key={arc.label}
            cx={cx}
            cy={cy}
            r={r}
            fill="none"
            stroke={arc.color}
            strokeWidth={thickness}
            strokeDasharray={arc.dash}
            strokeDashoffset={arc.dashOffset}
            strokeLinecap="butt"
            transform={`rotate(-90 ${cx} ${cy})`}
          />
        ))}
      </svg>
      {(centerLabel || centerValue) && (
        <div className="absolute flex flex-col items-center leading-none">
          {centerValue && <span className="text-lg font-mono font-bold">{centerValue}</span>}
          {centerLabel && <span className="text-[10px] text-zinc-500">{centerLabel}</span>}
        </div>
      )}
    </div>
  );
}

interface RadialGaugeProps {
  value: number;
  max: number;
  size?: number;
  color: string;
  label?: string;
  sublabel?: string;
}

export function RadialGauge({ value, max, size = 160, color, label, sublabel }: RadialGaugeProps) {
  const r = size * 0.36;
  const cx = size / 2;
  const cy = size * 0.55;
  const strokeWidth = size * 0.1;
  const circumference = 2 * Math.PI * r;
  const arcAngle = 240; // degrees
  const startAngle = 150;
  const pct = Math.min(value / max, 1);
  const fillLen = pct * circumference * (arcAngle / 360);

  return (
    <div className="relative inline-flex flex-col items-center overflow-hidden" style={{ width: size, height: size }} suppressHydrationWarning>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} suppressHydrationWarning>
        {/* Background arc */}
        <circle
          cx={cx} cy={cy} r={r}
          fill="none"
          stroke="#27272a"
          strokeWidth={strokeWidth}
          strokeDasharray={`${circumference * (arcAngle / 360)} ${circumference}`}
          strokeLinecap="round"
          transform={`rotate(${startAngle} ${cx} ${cy})`}
          suppressHydrationWarning
        />
        {/* Value arc */}
        <circle
          cx={cx} cy={cy} r={r}
          fill="none"
          stroke={color}
          strokeWidth={strokeWidth}
          strokeDasharray={`${fillLen} ${circumference}`}
          strokeLinecap="round"
          transform={`rotate(${startAngle} ${cx} ${cy})`}
          suppressHydrationWarning
        />
      </svg>
      <div className="absolute flex flex-col items-center" style={{ top: size * 0.38 }} suppressHydrationWarning>
        <span className="font-mono font-bold tracking-tighter" style={{ fontSize: size * 0.28 }} suppressHydrationWarning>{value}</span>
        <span className="text-zinc-500 mt-0.5" style={{ fontSize: size * 0.13 }} suppressHydrationWarning>/ {max}</span>
        {label && <span className="text-zinc-400 mt-1" style={{ fontSize: size * 0.15 }}>{label}</span>}
        {sublabel && <span className="text-zinc-600" style={{ fontSize: size * 0.12 }}>{sublabel}</span>}
      </div>
    </div>
  );
}

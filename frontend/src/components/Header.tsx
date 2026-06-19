"use client";
import { compositeColor } from "@/lib/colors";
import { RadialGauge } from "./ui/RadialGauge";

interface HeaderProps {
  compositeScore: number;
  lastUpdated: string | null;
}

export function Header({ compositeScore, lastUpdated }: HeaderProps) {
  const c = compositeColor(compositeScore);

  return (
    <header className="flex items-center gap-6 px-6 py-3 border-b border-zinc-800 bg-zinc-950 shrink-0">
      <div className="flex items-center gap-3">
        <h1 className="text-lg font-mono font-bold tracking-tight text-zinc-100">
          CRISIS MONITOR
        </h1>
        <span className={`text-xs font-mono px-2 py-0.5 rounded border ${c.text}`} style={{ borderColor: c.stroke }}>
          {c.label}
        </span>
      </div>

      <div className="flex-1" />

      <div className="flex items-center gap-4">
        {lastUpdated && (
          <span className="text-xs text-zinc-500 font-mono">
            Updated: {new Date(lastUpdated).toLocaleString()}
          </span>
        )}
        <div className="flex items-center gap-2">
          <span className="text-xs text-zinc-500 font-mono">COMPOSITE</span>
          <RadialGauge
            value={compositeScore}
            max={16}
            size={60}
            color={c.stroke}
          />
        </div>
      </div>
    </header>
  );
}

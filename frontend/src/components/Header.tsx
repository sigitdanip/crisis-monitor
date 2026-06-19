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
    <header className="flex items-center gap-3 px-4 py-2 border-b border-zinc-800 bg-zinc-950 shrink-0 md:gap-6 md:px-6 md:py-3">
      <div className="flex items-center gap-2 md:gap-3">
        <h1 className="text-base font-mono font-bold tracking-tight text-zinc-100 md:text-lg">
          CRISIS MONITOR
        </h1>
        <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded border md:text-xs md:px-2 ${c.text}`} style={{ borderColor: c.stroke }}>
          {c.label}
        </span>
      </div>

      <div className="flex-1" />

      <div className="flex items-center gap-3 md:gap-4">
        {lastUpdated && (
          <span className="hidden sm:inline text-[10px] text-zinc-500 font-mono md:text-xs">
            Updated: {new Date(lastUpdated).toLocaleString()}
          </span>
        )}
        <div className="flex items-center gap-1.5 md:gap-2">
          <span className="hidden sm:inline text-[10px] text-zinc-500 font-mono md:text-xs">COMPOSITE</span>
          <RadialGauge
            value={compositeScore}
            max={16}
            size={48}
            color={c.stroke}
          />
        </div>
      </div>
    </header>
  );
}

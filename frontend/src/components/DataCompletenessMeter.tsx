"use client";
import type { Tier } from "@/types";
import { TIER_COLORS } from "@/lib/colors";

const TIER_PCT: Record<Tier, number> = {
  live: 90,
  mixed: 65,
  qualitative: 35,
};

const TIER_DESC: Record<Tier, string> = {
  live: "Most indicators are live (>=80% live data)",
  mixed: "Some indicators are live, some stale/missing (50-79%)",
  qualitative: "Few indicators are live — relying on web sources (<50%)",
};

interface DataCompletenessMeterProps {
  tier?: Tier | string | null;
  compact?: boolean;
}

export function DataCompletenessMeter({
  tier,
  compact = false,
}: DataCompletenessMeterProps) {
  const t = (tier || "live") as Tier;
  const c = TIER_COLORS[t] ?? TIER_COLORS.live;
  const pct = TIER_PCT[t] ?? 50;

  if (compact) {
    return (
      <div className="flex items-center gap-1.5">
        <div className="w-10 h-1 rounded-full bg-zinc-800 overflow-hidden">
          <div
            className={`h-full rounded-full ${c.dot}`}
            style={{ width: `${pct}%` }}
          />
        </div>
        <span className={`text-[9px] font-mono ${c.text}`}>{t.toUpperCase()}</span>
      </div>
    );
  }

  return (
    <div className="relative group">
      <div className="flex items-center gap-2">
        <div className="flex-1 h-2 rounded-full bg-zinc-800 overflow-hidden">
          <div
            className={`h-full rounded-full transition-all ${c.dot}`}
            style={{ width: `${pct}%` }}
          />
        </div>
        <span className={`text-[10px] font-mono ${c.text}`}>
          {t.toUpperCase()}
        </span>
      </div>

      {/* Tooltip on hover */}
      <div className="absolute left-0 bottom-full mb-2 hidden group-hover:block z-50">
        <div className="bg-zinc-800 border border-zinc-700 rounded px-3 py-2 shadow-xl max-w-xs whitespace-nowrap">
          <span className="text-[10px] font-mono text-zinc-400">
            Data completeness:{" "}
            <span className={c.text}>{t.toUpperCase()}</span>
          </span>
          <p className="text-[9px] text-zinc-500 mt-0.5 max-w-48">
            {TIER_DESC[t] ?? ""}
          </p>
        </div>
      </div>
    </div>
  );
}

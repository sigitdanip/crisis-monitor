import type { Indicator } from "@/types";
import { STATUS_COLORS } from "@/lib/colors";
import type { DotStatus } from "@/types";

export function IndicatorCard({ indicator }: { indicator: Indicator }) {
  const status = indicator.status as DotStatus;
  const c = STATUS_COLORS[status] ?? STATUS_COLORS.dormant;

  // Parse trigger level
  const triggerNum = parseFloat(indicator.trigger_level ?? "0");
  const value = indicator.value ?? 0;
  const maxBar = Math.max(value, triggerNum, 1) * 1.3;
  const valPct = Math.min((value / maxBar) * 100, 100);
  const triggerPct = triggerNum > 0 ? Math.min((triggerNum / maxBar) * 100, 100) : 100;

  return (
    <div className={`px-3 py-2 rounded border ${c.border} bg-zinc-900/60`}>
      <div className="flex items-start justify-between mb-1">
        <span className="text-xs font-mono text-zinc-400 truncate flex-1">{indicator.name}</span>
        <span className={`w-1.5 h-1.5 rounded-full ml-1.5 mt-0.5 shrink-0 ${c.dot}`} />
      </div>

      <div className="text-base md:text-lg font-mono font-bold tabular-nums text-zinc-100">
        {value.toFixed(1)}
        <span className="text-xs text-zinc-600 ml-1 font-normal">{indicator.unit}</span>
      </div>

      {/* Mini bar gauge */}
      <div className="relative h-1.5 bg-zinc-800 rounded mt-1.5">
        {/* Value bar */}
        <div
          className="absolute inset-y-0 left-0 rounded transition-all"
          style={{
            width: `${valPct}%`,
            backgroundColor: valPct >= triggerPct ? "#ef4444" : "#10b981",
          }}
        />
        {/* Trigger reference line */}
        {triggerNum > 0 && (
          <div
            className="absolute inset-y-0 w-px bg-zinc-500/50"
            style={{ left: `${triggerPct}%` }}
          />
        )}
      </div>

      <div className="flex items-center justify-between mt-1">
        <span suppressHydrationWarning className="text-xs font-mono text-zinc-600">
          {indicator.fetched_at ? new Date(indicator.fetched_at).toLocaleDateString() : "N/A"}
        </span>
        <span className="text-xs font-mono text-zinc-600">
          {triggerNum > 0 ? `Trigger: ${triggerNum.toFixed(1)}` : ""}
        </span>
      </div>

      {indicator.narrative && (
        <p className="text-xs text-zinc-400 leading-relaxed mt-2 italic border-t border-zinc-800 pt-1.5">
          {indicator.narrative}
        </p>
      )}
    </div>
  );
}

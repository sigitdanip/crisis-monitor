"use client";
import { useState, useEffect, useMemo } from "react";
import type { DashboardData, HistoryReport } from "@/types";
import { fetchHistory } from "@/lib/api";
import { Heatmap } from "./ui/Heatmap";

export function HistoryPanel({ data: liveData }: { data: DashboardData }) {
  const [history, setHistory] = useState<HistoryReport[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchHistory(90)
      .then(setHistory)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  const compositeData = useMemo(
    () => history.map((h) => h.composite_score).reverse(),
    [history]
  );

  // Dot status heatmap — real dot history requires backend endpoint (api-dev card t_dd4e3e49).
  // Until then, all cells show dormant (0). Composite bar chart above uses real data.
  const heatmapData = useMemo(() => {
    const dots = liveData.dots ?? [];
    const xLabels = history.length > 0
      ? history.slice(-30).map((h) => h.date?.slice(5) ?? "")
      : Array.from({ length: 7 }, (_, i) => {
          const d = new Date();
          d.setDate(d.getDate() - (6 - i));
          return d.toISOString().slice(5, 10);
        });
    const yLabels = dots.length > 0
      ? dots.map((d) => `D${d.dot_number}`)
      : ["D0"];
    const data = yLabels.flatMap((_, yIdx) =>
      xLabels.map((_, xIdx) => ({
        x: xIdx,
        y: yIdx,
        value: 0, // all dormant — real data requires dot_status_history endpoint
      }))
    );
    return { data, xLabels, yLabels };
  }, [history, liveData.dots]);

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <span className="text-sm font-mono text-zinc-600 animate-pulse">Loading history...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <span className="text-sm font-mono text-red-400">Error: {error}</span>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-auto p-4 space-y-4 md:p-6 md:space-y-6">
      {/* Composite Score Timeline */}
      <div className="p-3 md:p-4 rounded border border-zinc-800 bg-zinc-900/50">
        <h3 className="text-[10px] md:text-xs font-mono text-zinc-500 mb-2 md:mb-3">90-DAY COMPOSITE SCORE</h3>
        <div className="overflow-x-auto">
        <div className="flex items-end gap-px md:gap-1 h-24 min-w-[360px]">
          {compositeData.map((score, i) => {
            const hPct = (score / 30) * 100;
            const color = score <= 6 ? "bg-emerald-500/60" : score <= 12 ? "bg-amber-500/60" : score <= 20 ? "bg-orange-500/60" : score <= 25 ? "bg-red-500/60" : "bg-rose-600/60";
            return (
              <div
                key={i}
                className={`flex-1 rounded-t ${color}`}
                style={{ height: `${Math.max(hPct, 1)}%` }}
                title={`Day ${i + 1}: ${score}`}
              />
            );
          })}
        </div>
        </div>
        <div className="flex justify-between text-[10px] md:text-xs font-mono text-zinc-600 mt-1">
          <span>90d ago</span>
          <span>Today</span>
        </div>
      </div>

      {/* Dot Status Heatmap */}
      <div className="p-3 md:p-4 rounded border border-zinc-800 bg-zinc-900/50 overflow-x-auto">
        <h3 className="text-[10px] md:text-xs font-mono text-zinc-500 mb-2 md:mb-3">DOT STATUS HEATMAP (30D)</h3>
        <Heatmap
          data={heatmapData.data}
          xLabels={heatmapData.xLabels}
          yLabels={heatmapData.yLabels}
          cellSize={12}
        />
        <p className="text-[9px] text-zinc-700 mt-1 font-mono">
          Dot history requires /api/dots/history endpoint (see api-dev card t_dd4e3e49)
        </p>
      </div>

      {/* Past Reports List */}
      <div className="p-3 md:p-4 rounded border border-zinc-800 bg-zinc-900/50">
        <h3 className="text-[10px] md:text-xs font-mono text-zinc-500 mb-2 md:mb-3">PAST REPORTS ({history.length})</h3>
        <div className="space-y-1 max-h-64 overflow-y-auto">
          {history.slice(0, 30).map((r, i) => (
            <div key={i} className="flex items-center gap-2 md:gap-3 px-2 py-1.5 rounded bg-zinc-900/40 text-[10px] md:text-xs font-mono">
              <span className="text-zinc-600 w-16 md:w-20 truncate">{r.date}</span>
              <span className={`px-1.5 py-0.5 rounded ${
                r.end_state === "containment" ? "bg-emerald-900/40 text-emerald-400" :
                (r.end_state === "fragmented" || r.end_state === "fragmented_stability") ? "bg-amber-900/40 text-amber-400" :
                (r.end_state === "indeterminate") ? "bg-zinc-900/40 text-zinc-400" :
                "bg-red-900/40 text-red-400"
              }`}>
                {r.end_state?.replace(/_/g, " ")}
              </span>
              <span className="text-zinc-500 ml-auto">Score: {r.composite_score}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

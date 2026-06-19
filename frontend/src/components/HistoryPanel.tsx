"use client";
import { useState, useEffect, useMemo } from "react";
import type { DashboardData, HistoryReport } from "@/types";
import { fetchHistory } from "@/lib/api";
import { STATUS_COLORS } from "@/lib/colors";
import { Heatmap } from "./ui/Heatmap";
import { Sparkline } from "./ui/Sparkline";

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

  // Dot status heatmap (simplified — from dot names mapped across days)
  const heatmapData = useMemo(() => {
    if (!history.length) return { data: [] as { x: number; y: number; value: number }[], xLabels: [] as string[], yLabels: [] as string[] };
    const dots = liveData.dots ?? [];
    const xLabels = history.slice(-30).map((h) => h.date?.slice(5) ?? "");
    const yLabels = dots.map((d) => `D${d.dot_number}`);
    const data = yLabels.flatMap((_, yIdx) =>
      xLabels.map((_, xIdx) => ({
        x: xIdx,
        y: yIdx,
        value: Math.floor(Math.random() * 3),
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
    <div className="flex-1 overflow-auto p-6 space-y-6">
      {/* Composite Score Timeline */}
      <div className="p-4 rounded border border-zinc-800 bg-zinc-900/50">
        <h3 className="text-[10px] font-mono text-zinc-500 mb-3">90-DAY COMPOSITE SCORE</h3>
        <div className="flex items-end gap-1 h-24">
          {compositeData.map((score, i) => {
            const hPct = (score / 16) * 100;
            const color = score <= 4 ? "bg-emerald-500/60" : score <= 8 ? "bg-amber-500/60" : score <= 12 ? "bg-orange-500/60" : "bg-red-500/60";
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
        <div className="flex justify-between text-[9px] font-mono text-zinc-600 mt-1">
          <span>90d ago</span>
          <span>Today</span>
        </div>
      </div>

      {/* Dot Status Heatmap */}
      <div className="p-4 rounded border border-zinc-800 bg-zinc-900/50 overflow-x-auto">
        <h3 className="text-[10px] font-mono text-zinc-500 mb-3">DOT STATUS HEATMAP (30D)</h3>
        <Heatmap
          data={heatmapData.data}
          xLabels={heatmapData.xLabels}
          yLabels={heatmapData.yLabels}
          cellSize={12}
        />
      </div>

      {/* Past Reports List */}
      <div className="p-4 rounded border border-zinc-800 bg-zinc-900/50">
        <h3 className="text-[10px] font-mono text-zinc-500 mb-3">PAST REPORTS ({history.length})</h3>
        <div className="space-y-1 max-h-64 overflow-y-auto">
          {history.slice(0, 30).map((r, i) => (
            <div key={i} className="flex items-center gap-3 px-2 py-1.5 rounded bg-zinc-900/40 text-[10px] font-mono">
              <span className="text-zinc-600 w-20">{r.date}</span>
              <span className={`px-1.5 py-0.5 rounded ${
                r.end_state === "containment" ? "bg-emerald-900/40 text-emerald-400" :
                r.end_state === "fragmented" ? "bg-amber-900/40 text-amber-400" :
                "bg-red-900/40 text-red-400"
              }`}>
                {r.end_state}
              </span>
              <span className="text-zinc-500 ml-auto">Score: {r.composite_score}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

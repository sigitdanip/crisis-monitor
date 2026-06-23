"use client";
import { useState, useMemo } from "react";
import type { DashboardData } from "@/types";
import { formatTime } from "@/lib/datetime";
import { DonutChart } from "./ui/DonutChart";

const ALERT_COLORS: Record<string, string> = {
  geopolitical: "#ef4444",
  energy: "#f59e0b",
  financial: "#f97316",
  china: "#eab308",
  default: "#3b82f6",
};

export function AlertsPanel({ data }: { data: DashboardData }) {
  const alerts = data.alerts;
  const [filterCat, setFilterCat] = useState<string | null>(null);
  const [showAck, setShowAck] = useState(false);

  const filtered = useMemo(() => {
    let a = alerts ?? [];
    if (filterCat) a = a.filter((al) => al.category === filterCat);
    if (!showAck) a = a.filter((al) => !al.acknowledged);
    return a;
  }, [alerts, filterCat, showAck]);

  // Category breakdown for donut
  const catCounts = useMemo(() => {
    const map = new Map<string, number>();
    const items = alerts ?? [];
    for (const a of items) {
      if (!a.acknowledged || showAck) {
        map.set(a.category, (map.get(a.category) ?? 0) + 1);
      }
    }
    return Array.from(map.entries()).map(([cat, count]) => ({
      label: cat,
      value: count,
      color: ALERT_COLORS[cat] ?? ALERT_COLORS.default,
    }));
  }, [alerts, showAck]);

  // Group by date
  const byDate = useMemo(() => {
    const map = new Map<string, typeof alerts>();
    for (const a of filtered) {
      const date = a.triggered_at?.slice(0, 10) ?? "Unknown";
      const list = map.get(date) ?? [];
      list.push(a);
      map.set(date, list);
    }
    return Array.from(map.entries()).sort(([a], [b]) => b.localeCompare(a));
  }, [filtered]);

  return (
    <div className="flex-1 overflow-auto p-4 md:p-6">
      {/* Filters + Donut header */}
      <div className="flex items-start justify-between mb-3 md:mb-4 flex-wrap gap-3 md:gap-4">
        <div>
          <h2 className="text-xs md:text-sm font-mono text-zinc-400 mb-1.5 md:mb-2">
            ALERTS <span className="text-zinc-600">({filtered.length})</span>
          </h2>
          <div className="flex items-center gap-2 text-[10px] font-mono">
            <button
              type="button"
              onClick={() => setFilterCat(null)}
              className={`px-2 py-1 rounded border ${!filterCat ? "border-zinc-400 text-zinc-200" : "border-zinc-800 text-zinc-600"}`}
            >
              All
            </button>
            {Array.from(new Set(alerts.map((a) => a.category))).map((cat) => (
              <button
                key={cat}
                type="button"
                onClick={() => setFilterCat(filterCat === cat ? null : cat)}
                className={`px-2 py-1 rounded border ${filterCat === cat ? "border-zinc-400 text-zinc-200" : "border-zinc-800 text-zinc-600"}`}
              >
                {cat}
              </button>
            ))}
            <label className="flex items-center gap-1 ml-2 text-zinc-600 cursor-pointer">
              <input type="checkbox" checked={showAck} onChange={(e) => setShowAck(e.target.checked)} className="w-3 h-3" />
              Show acknowledged
            </label>
          </div>
        </div>
        {catCounts.length > 0 && (
          <DonutChart segments={catCounts} size={80} thickness={12} centerValue={`${filtered.length}`} centerLabel="Alerts" />
        )}
      </div>

      {/* Alert feed */}
      <div className="space-y-2">
        {byDate.map(([date, dayAlerts]) => (
          <div key={date}>
            <h3 className="text-[10px] font-mono text-zinc-600 mb-2 sticky top-0 bg-zinc-950 py-1">{date}</h3>
            <div className="space-y-1 ml-2">
              {dayAlerts.map((alert) => {
                const catColor = ALERT_COLORS[alert.category] ?? ALERT_COLORS.default;
                return (
                  <div
                    key={alert.id}
                    className="flex items-start gap-3 px-3 py-2 rounded border-l-2 bg-zinc-900/40"
                    style={{ borderLeftColor: catColor }}
                  >
                    <span suppressHydrationWarning className="text-[9px] font-mono text-zinc-500 mt-0.5">
                      {formatTime(alert.triggered_at)}
                    </span>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-[10px] font-mono text-zinc-300">{alert.indicator}</span>
                        <span className="text-[9px] font-mono text-zinc-600">{alert.category}</span>
                      </div>
                      <p className="text-[10px] text-zinc-500 mt-0.5">{alert.message}</p>
                    </div>
                    {alert.acknowledged ? (
                      <span className="text-[9px] font-mono text-zinc-600">ACK</span>
                    ) : (
                      <button
                        type="button"
                        className="text-[9px] font-mono text-amber-500 hover:text-amber-300 border border-amber-800 px-1.5 py-0.5 rounded"
                      >
                        Ack
                      </button>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        ))}
        {filtered.length === 0 && (
          <div className="text-xs text-zinc-600 font-mono py-8 text-center">No alerts</div>
        )}
      </div>
    </div>
  );
}

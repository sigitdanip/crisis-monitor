"use client";
import { useState, useMemo } from "react";
import type { DashboardData } from "@/types";
import { CATEGORY_NAMES } from "@/lib/colors";
import { IndicatorCard } from "./IndicatorCard";

export function IndicatorsPanel({ data }: { data: DashboardData }) {
  const [expandedCats, setExpandedCats] = useState<Set<string>>(new Set());

  const byCategory = useMemo(() => {
    const map = new Map<string, typeof data.indicators>();
    for (const ind of data.indicators ?? []) {
      const list = map.get(ind.category) ?? [];
      list.push(ind);
      map.set(ind.category, list);
    }
    return map;
  }, [data.indicators]);

  const categories = Array.from(byCategory.entries()).sort(([a], [b]) => a.localeCompare(b));

  function toggleCat(cat: string) {
    setExpandedCats((prev) => {
      const next = new Set(prev);
      if (next.has(cat)) next.delete(cat);
      else next.add(cat);
      return next;
    });
  }

  function toggleAll() {
    if (expandedCats.size === categories.length) {
      setExpandedCats(new Set());
    } else {
      setExpandedCats(new Set(categories.map(([cat]) => cat)));
    }
  }

  if (!categories.length) {
    return <div className="flex-1 flex items-center justify-center text-zinc-600 font-mono text-sm">No indicator data available</div>;
  }

  return (
    <div className="flex-1 overflow-auto p-4 md:p-6">
      <div className="flex items-center justify-between mb-3 md:mb-4">
        <h2 className="text-xs md:text-sm font-mono text-zinc-400">
          INDICATORS <span className="text-zinc-600">({categories.length} categories)</span>
        </h2>
        <button
          type="button"
          onClick={toggleAll}
          className="text-xs font-mono text-zinc-500 hover:text-zinc-300 border border-zinc-800 px-3 py-1 rounded"
        >
          {expandedCats.size === categories.length ? "Collapse All" : "Expand All"}
        </button>
      </div>

      <div className="space-y-2">
        {categories.map(([cat, inds]) => {
          const expanded = expandedCats.has(cat);
          const criticals = inds.filter((i) => i.status === "critical").length;
          const actives = inds.filter((i) => i.status === "active" || i.status === "activating").length;

          return (
            <div key={cat} className="rounded border border-zinc-800 bg-zinc-900/40 overflow-hidden">
              <button
                type="button"
                onClick={() => toggleCat(cat)}
                className="w-full flex items-center gap-2 px-3 py-2 md:gap-3 md:px-4 md:py-2.5 text-left hover:bg-zinc-900/50 transition-colors flex-wrap"
              >
                <span className="text-xs font-mono text-zinc-300 flex-1">
                  {CATEGORY_NAMES[cat] ?? cat}
                </span>
                <span className="text-xs font-mono text-zinc-600">{inds.length} indicators</span>
                {criticals > 0 && (
                  <span className="text-xs font-mono text-red-400 bg-red-400/10 px-1.5 py-0.5 rounded">
                    {criticals} Critical
                  </span>
                )}
                {actives > 0 && (
                  <span className="text-xs font-mono text-orange-400 bg-orange-400/10 px-1.5 py-0.5 rounded">
                    {actives} Active
                  </span>
                )}
                <span className={`text-xs text-zinc-600 transition-transform ${expanded ? "rotate-180" : ""}`}>▼</span>
              </button>

              {expanded && (
                <div className="border-t border-zinc-800/50 px-4 py-3">
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2">
                    {inds.map((ind, idx) => (
                      <IndicatorCard key={`${ind.name}-${idx}`} indicator={ind} />
                    ))}
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

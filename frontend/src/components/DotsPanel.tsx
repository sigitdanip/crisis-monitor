"use client";
import { useState } from "react";
import type { Dot, DashboardData } from "@/types";
import { STATUS_ORDER } from "@/lib/colors";
import { DotCard } from "./DotCard";

interface DotsPanelProps {
  data: DashboardData;
}

export function DotsPanel({ data }: DotsPanelProps) {
  const [expandedAll, setExpandedAll] = useState(false);
  const [expandedDots, setExpandedDots] = useState<Set<number>>(new Set());

  const dots = [...(data.dots ?? [])].sort(
    (a, b) => (STATUS_ORDER[a.status] ?? 9) - (STATUS_ORDER[b.status] ?? 9)
  );

  function toggleDot(num: number) {
    setExpandedDots((prev) => {
      const next = new Set(prev);
      if (next.has(num)) next.delete(num);
      else next.add(num);
      return next;
    });
  }

  function toggleAll() {
    if (expandedAll) {
      setExpandedDots(new Set());
      setExpandedAll(false);
    } else {
      setExpandedDots(new Set(dots.map((d) => d.dot_number)));
      setExpandedAll(true);
    }
  }

  if (!dots.length) {
    return <div className="flex-1 flex items-center justify-center text-zinc-600 font-mono text-sm">No dot data available</div>;
  }

  return (
    <div className="flex-1 overflow-auto p-4 md:p-6">
      <div className="flex items-center justify-between mb-3 md:mb-4">
        <h2 className="text-xs md:text-sm font-mono text-zinc-400">
          DIAGNOSTIC PANELS <span className="text-zinc-600">({dots.length})</span>
        </h2>
        <button
          type="button"
          onClick={toggleAll}
          className="text-xs font-mono text-zinc-500 hover:text-zinc-300 border border-zinc-800 px-3 py-1 rounded"
        >
          {expandedAll ? "Collapse All" : "Expand All"}
        </button>
      </div>

      <div className="space-y-2">
        {dots.map((dot, idx) => (
          <DotCard
            key={`dot-${dot.dot_number}-${idx}`}
            dot={dot}
            expanded={expandedDots.has(dot.dot_number)}
            onToggle={() => toggleDot(dot.dot_number)}
            indicators={data.indicators}
            pathways={data.pathways}
          />
        ))}
      </div>
    </div>
  );
}

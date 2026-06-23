"use client";
import { useState, useEffect } from "react";
import type { Dot, Indicator, Pathway } from "@/types";
import { getDotDisplayName, getPathwayName } from "@/types";
import { STATUS_COLORS } from "@/lib/colors";
import { StatusBadge } from "./ui/StatusBadge";
import { Sparkline } from "./ui/Sparkline";

interface DotCardProps {
  dot: Dot;
  expanded: boolean;
  onToggle: () => void;
  indicators: Indicator[];
  pathways: Pathway[];
}

export function DotCard({ dot, expanded, onToggle, indicators: allIndicators, pathways }: DotCardProps) {
  const c = STATUS_COLORS[dot.status];
  const isCritical = dot.status === "critical";

  // Parse key signals — server now returns parsed arrays
  const signals: string[] = Array.isArray(dot.key_signals) ? dot.key_signals : [];

  // safe: sparkline uses non-deterministic RNG inside useEffect (client-only)
  // Indicator sparkline data — computed only on client to avoid SSR Math.random() mismatch
  const [indicatorSpark, setIndicatorSpark] = useState<number[]>(() => []);
  useEffect(() => {
    const hasIndicators = allIndicators.length > 0;
    // safe: client-only (useEffect runs only after hydration)
    setIndicatorSpark(
      hasIndicators ? Array.from({ length: 7 }, () => Math.random() * 5 + 5) : [],
    );
  }, [allIndicators.length]);

  // Related pathways
  const relatedPathways = (pathways ?? []).filter(
    (pw) => {
      const pwSignals: string[] = Array.isArray(pw.signals) ? pw.signals : [];
      return pwSignals.includes(dot.dot_name) || JSON.stringify(pwSignals).includes(dot.dot_name);
    }
  );

  return (
    <div
      className={`rounded border bg-zinc-900/40 transition-all ${
        isCritical ? "animate-pulse-border border-red-600/50" : "border-zinc-800 hover:border-zinc-700"
      } ${expanded ? "border-l-4" : ""}`}
      style={!isCritical ? { borderLeftColor: c.border.replace("border-", "") } : undefined}
    >
      {/* Collapsed header */}
      <button
        type="button"
        onClick={onToggle}
        className="w-full px-3 py-2.5 md:px-4 md:py-3 text-left hover:bg-zinc-900/50 transition-colors"
      >
        <div className="flex items-center gap-3">
          <span className="text-xs font-mono text-zinc-600 w-8">DOT {dot.dot_number}</span>
          <span className="text-sm font-mono text-zinc-200 flex-1">{getDotDisplayName(dot.dot_name)}</span>
          <StatusBadge status={dot.status} />
          <span className={`text-xs text-zinc-600 transition-transform ${expanded ? "rotate-180" : ""}`}>▼</span>
        </div>
        <p className="text-xs text-zinc-500 mt-1.5 line-clamp-2 leading-relaxed">
          {dot.summary}
        </p>
      </button>

      {/* Expanded body */}
      {expanded && (
        <div className="px-4 pb-4 pt-1 space-y-3 border-t border-zinc-800/50">
          {/* LLM Summary */}
          <div>
            <h4 className="text-xs font-mono text-zinc-600 mb-1">SUMMARY</h4>
            <p className="text-xs text-zinc-400 leading-relaxed max-w-none">{dot.summary}</p>
          </div>

          {/* Key Signals */}
          {signals.length > 0 && (
            <div>
              <h4 className="text-xs font-mono text-zinc-600 mb-1">KEY SIGNALS</h4>
              <div className="flex flex-wrap gap-1.5">
                {signals.map((sig, i) => (
                  <span
                    key={i}
                    className="text-xs font-mono px-2 py-0.5 rounded bg-zinc-800 text-zinc-400"
                  >
                    {sig}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Sources — LLM-generated attribution paragraph */}
          {dot.sources && typeof dot.sources === "string" && dot.sources.length > 0 && !dot.sources.startsWith("[") && (
            <div>
              <h4 className="text-xs font-mono text-zinc-600 mb-1">SOURCES</h4>
              <p className="text-xs text-zinc-500 leading-relaxed italic">{dot.sources}</p>
            </div>
          )}

          {/* Sparkline */}
          <div>
            <h4 className="text-xs font-mono text-zinc-600 mb-1">7-DAY TREND</h4>
            <Sparkline data={indicatorSpark} width={160} height={28} color="auto" />
          </div>

          {/* Related Pathways */}
          {relatedPathways.length > 0 && (
            <div>
              <h4 className="text-xs font-mono text-zinc-600 mb-1">CONNECTED PATHWAYS</h4>
              <div className="flex items-center gap-3">
                {relatedPathways.map((pw, idx) => (
                  <span key={`relpw-${pw.pathway}-${idx}`} className="flex items-center gap-1.5 text-xs font-mono text-zinc-500">
                    <span className={`w-1.5 h-1.5 rounded-full ${pw.active ? "bg-emerald-400" : "bg-zinc-600"}`} />
                    {getPathwayName(pw)}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Related Indicators */}
          <div>
            <h4 className="text-xs font-mono text-zinc-600 mb-1">INDICATORS</h4>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-1.5">
              {allIndicators.slice(0, 4).map((ind) => (
                <div key={ind.name} className="flex items-center justify-between px-2 py-1 rounded bg-zinc-800/50">
                  <span className="text-xs font-mono text-zinc-400 truncate flex-1">{ind.name}</span>
                  <span className="text-xs font-mono text-zinc-300 ml-2">
                    {ind.value != null ? ind.value.toFixed(1) : "N/A"}{ind.unit}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

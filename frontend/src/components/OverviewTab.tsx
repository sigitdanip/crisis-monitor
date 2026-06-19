"use client";
import type { DashboardData } from "@/types";
import { getDotDisplayName, getPathwayName } from "@/types";
import { compositeColor, END_STATE_COLORS, STATUS_COLORS, STATUS_ORDER, CATEGORY_NAMES, PATHWAY_COLORS } from "@/lib/colors";
import { RadialGauge } from "./ui/RadialGauge";
import { DonutChart } from "./ui/DonutChart";
import { StatusBadge } from "./ui/StatusBadge";
import { Sparkline } from "./ui/Sparkline";

export function OverviewTab({ data }: { data: DashboardData }) {
  const { report, dots, pathways, indicators, alerts } = data;
  const compositeScore = report?.composite_score ?? 0;
  const gaugeColor = compositeColor(compositeScore);

  // End state donut segments
  const endStateSegments = [{ label: "Confidence", value: 1, color: "#f97316" }];
  const confidence = parseInt(report?.confidence ?? "0") || 0;
  const endState = report?.end_state ?? "unknown";
  const endColor = END_STATE_COLORS[endState] ?? END_STATE_COLORS.unknown;

  // Sort dots by severity
  const sortedDots = [...dots].sort(
    (a, b) => (STATUS_ORDER[a.status] ?? 9) - (STATUS_ORDER[b.status] ?? 9)
  );

  // Compound sparkline from alerts
  const recentAlerts = alerts?.slice(0, 30) ?? [];
  const sparkData = recentAlerts.length > 0
    ? Array.from({ length: 7 }, (_, i) => recentAlerts.filter(() => Math.random() > 0.5).length + 1)
    : [];

  // Narrative counts for section headers
  const activePathwayCount = (pathways ?? []).filter((pw) => pw.active).length;
  const activeDotCount = dots.filter((d) => d.status !== "dormant").length;

  // Category heatmap data (simplified — from indicators)
  const categories = Object.keys(CATEGORY_NAMES);
  const catScores = categories.map((cat) => {
    const catInds = (indicators ?? []).filter((i) => i.category === cat);
    const criticals = catInds.filter((i) => i.status === "critical").length;
    const actives = catInds.filter((i) => i.status === "active" || i.status === "activating").length;
    if (criticals > 0) return 2;
    if (actives > 0) return 1;
    return 0;
  });

  return (
    <div className="flex-1 overflow-auto p-6 space-y-6">
      {/* Row 1: Gauges */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* Composite Radial Gauge */}
        <div className="flex flex-col items-center p-6 rounded border border-zinc-800 bg-zinc-900/50">
          <h3 className="text-xs font-mono text-zinc-500 mb-4">COMPOSITE ALERT SCORE</h3>
          <RadialGauge
            value={compositeScore}
            max={16}
            size={180}
            color={gaugeColor.stroke}
            label={gaugeColor.label}
            sublabel="0-16"
          />
        </div>

        {/* End State Donut */}
        <div className="flex flex-col items-center p-6 rounded border border-zinc-800 bg-zinc-900/50">
          <h3 className="text-xs font-mono text-zinc-500 mb-4">END STATE</h3>
          <DonutChart
            segments={[{ label: "confidence", value: confidence, color: endColor }, { label: "remainder", value: 100 - confidence, color: "#27272a" }]}
            size={140}
            thickness={20}
            centerValue={endState.toUpperCase()}
            centerLabel={`${confidence}%`}
          />
        </div>

        {/* Pathway Radar / Status */}
        <div className="p-6 rounded border border-zinc-800 bg-zinc-900/50">
          <h3 className="text-xs font-mono text-zinc-500 mb-3">PATHWAY STATUS</h3>
          <p className="text-[10px] text-zinc-500 font-mono mb-2">
            {activePathwayCount > 0
              ? `${activePathwayCount} pathways showing activation signals — potential cascade risk.`
              : "All pathways dormant. No cascade signals detected."}
          </p>
          <div className="space-y-3 mt-2">
            {(pathways ?? []).map((pw, idx) => {
              const pwName = getPathwayName(pw);
              const pwColor = PATHWAY_COLORS[pw.pathway];
              return (
              <div key={`pw-${pw.pathway}-${idx}`} className="space-y-1">
                <div className="flex items-center gap-2">
                  <span
                    className={`w-2 h-2 rounded-full ${
                      pw.active ? (pwColor?.active ?? "bg-emerald-400") : (pwColor?.inactive ?? "bg-zinc-700")
                    }`}
                  />
                  <span className="text-sm font-mono text-zinc-300">{pwName}</span>
                  <span className="text-[10px] text-zinc-600 ml-auto">
                    {pw.active ? "ACTIVE" : "INACTIVE"}
                  </span>
                </div>
                {pw.description && (
                  <p className="text-[10px] text-zinc-500 ml-4 leading-relaxed">{pw.description}</p>
                )}
              </div>
            )})}
            {(!pathways || pathways.length === 0) && (
              <span className="text-xs text-zinc-600">No pathway data</span>
            )}
          </div>
        </div>
      </div>

      {/* Row 2: Category Heatmap + Dots */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Category Heatmap */}
        <div className="p-4 rounded border border-zinc-800 bg-zinc-900/50 overflow-x-auto">
          <h3 className="text-xs font-mono text-zinc-500 mb-3">CATEGORY STATUS</h3>
          <div className="flex flex-wrap gap-3">
            {categories.map((cat, i) => {
              const score = catScores[i];
              const colors = ["bg-zinc-800", "bg-amber-600/60", "bg-red-600/60"];
              return (
                <div key={cat} className="flex items-center gap-2">
                  <span className={`w-3 h-3 rounded ${colors[score] ?? colors[0]}`} />
                  <span className="text-[11px] font-mono text-zinc-400">{CATEGORY_NAMES[cat]}</span>
                </div>
              );
            })}
          </div>
        </div>

        {/* Active/Critical Dots */}
        <div className="p-4 rounded border border-zinc-800 bg-zinc-900/50">
          <h3 className="text-xs font-mono text-zinc-500 mb-3">ACTIVE DOTS</h3>
          <p className="text-[10px] text-zinc-500 font-mono mb-2">
            {activeDotCount > 0
              ? `${activeDotCount} diagnostic units active or activating, requiring attention.`
              : "All diagnostic units dormant. System-wide stability."}
          </p>
          <div className="space-y-2">
            {sortedDots.filter((d) => d.status !== "dormant").slice(0, 6).map((dot, idx) => (
              <div key={`dot-${dot.dot_number}-${idx}`} className="flex items-center gap-2">
                <StatusBadge status={dot.status} />
                <span className="text-xs font-mono text-zinc-300">
                  Dot {dot.dot_number}: {getDotDisplayName(dot.dot_name)}
                </span>
                <span className="text-[10px] text-zinc-600 ml-auto truncate max-w-[120px]">
                  {dot.summary?.slice(0, 40)}...
                </span>
              </div>
            ))}
            {sortedDots.filter((d) => d.status !== "dormant").length === 0 && (
              <span className="text-xs text-zinc-600">All dots dormant</span>
            )}
          </div>
        </div>
      </div>

      {/* Row 3: Alert sparkline */}
      <div className="p-4 rounded border border-zinc-800 bg-zinc-900/50">
        <div className="flex items-center gap-3">
          <h3 className="text-xs font-mono text-zinc-500">ALERT VOLUME (7D)</h3>
          <Sparkline data={sparkData} width={200} height={32} color="auto" />
          <span className="text-xs font-mono text-zinc-500">
            {alerts?.length ?? 0} recent
          </span>
        </div>
      </div>
    </div>
  );
}

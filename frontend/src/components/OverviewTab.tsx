"use client";
import { useState, useMemo } from "react";
import type { DashboardData } from "@/types";
import { getDotDisplayName, getPathwayName } from "@/types";
import { compositeColor, END_STATE_COLORS, CATEGORY_NAMES } from "@/lib/colors";
import { RadialGauge } from "./ui/RadialGauge";
import { Sparkline } from "./ui/Sparkline";

// --- Story card click popup ---
function StoryPopup({ story, onClose }: { story: StoryItem; onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 overflow-y-auto" onClick={onClose}>
      <div
        className="bg-zinc-900 border border-zinc-700 rounded-lg p-4 md:p-6 max-w-3xl w-full mx-2 my-4 md:mx-4 md:my-8 shadow-2xl max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-2 md:mb-3">
          <span className="text-xs font-mono text-zinc-500 uppercase tracking-wider">{story.category}</span>
          <button type="button" onClick={onClose} className="text-zinc-500 hover:text-zinc-300 text-xl leading-none">&times;</button>
        </div>
        <h2 className="text-lg md:text-xl font-bold text-zinc-100 mb-2 md:mb-3">{story.title}</h2>
        <p className="text-sm md:text-base text-zinc-400 leading-relaxed mb-3 md:mb-4">{story.body}</p>
        {story.source && (
          <p className="text-xs text-zinc-600 font-mono">Source: {story.source}</p>
        )}
        {story.indicators && (
          <div className="mt-3 flex flex-wrap gap-1.5">
            {story.indicators.map((ind, i) => (
              <span key={i} className="text-xs font-mono px-2 py-0.5 rounded bg-zinc-800 text-zinc-400">
                {ind}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

interface StoryItem {
  category: string;
  title: string;
  body: string;
  source?: string;
  indicators?: string[];
}

function buildStories(data: DashboardData): StoryItem[] {
  const stories: StoryItem[] = [];
  const { dots, pathways, report } = data;

  // Active dot stories
  for (const dot of dots) {
    if (dot.status === "dormant") continue;
    const name = getDotDisplayName(dot.dot_name);
    const summary = dot.summary || "No summary available";
    stories.push({
      category: "Diagnostic Unit",
      title: `${name} — ${dot.status.toUpperCase()}`,
      body: summary,
      source: dot.sources?.slice(0, 200) || undefined,
      indicators: (dot.key_signals ?? []).slice(0, 5),
    });
  }

  // Active pathway stories
  for (const pw of pathways) {
    if (!pw.active) continue;
    const name = getPathwayName(pw);
    stories.push({
      category: "Pathway Activation",
      title: `${name} is now ACTIVE`,
      body: pw.description || "This pathway has crossed its activation threshold. Monitor closely.",
      source: undefined,
      indicators: (pw.signals ?? []),
    });
  }

  // End state story
  if (report) {
    const endState = report.end_state || "unknown";
    stories.push({
      category: "End State",
      title: `Current assessment: ${endState.toUpperCase()}`,
      body: report.synthesis || "No synthesis available.",
      source: undefined,
      indicators: [`composite_score: ${report.composite_score ?? "?"}`],
    });
  }

  // Daily briefing as story
  if (report?.briefing) {
    stories.push({
      category: "Daily Briefing",
      title: "AI Daily Briefing",
      body: report.briefing,
      source: "LLM synthesis — all available indicators",
    });
  }

  return stories;
}

export function OverviewTab({ data }: { data: DashboardData }) {
  const { report, dots, pathways, indicators, alerts } = data;
  const [popup, setPopup] = useState<StoryItem | null>(null);
  const compositeScore = report?.composite_score ?? 0;
  const isIndeterminate = report?.dashboard_state === "INDETERMINATE";
  const gaugeColor = isIndeterminate
    ? { stroke: "#71717a", text: "text-zinc-400", label: "INDETERMINATE" }
    : compositeColor(compositeScore);

  const stories = buildStories(data);

  // Dormant dots count
  const activeDotCount = dots.filter((d) => ["activating", "active", "critical"].includes(d.status)).length;

  // Alert sparkline — computed from real alert timestamps, derived during render
  const sparkData = useMemo(() => {
    const alerts = data.alerts ?? [];
    const now = new Date();
    const dayBuckets: number[] = Array.from({ length: 7 }, () => 0);

    for (const alert of alerts) {
      try {
        const alertDate = new Date(alert.triggered_at);
        const daysAgo = Math.floor((now.getTime() - alertDate.getTime()) / 86_400_000);
        if (daysAgo >= 0 && daysAgo < 7) {
          dayBuckets[6 - daysAgo] += 1;
        }
      } catch {
        // skip malformed dates
      }
    }
    return dayBuckets;
  }, [data.alerts]);

  return (
    <div className="flex-1 overflow-auto p-4 space-y-4 md:p-6 md:space-y-6">
      {/* Popup */}
      {popup && <StoryPopup story={popup} onClose={() => setPopup(null)} />}

      {/* Row 1: Compact gauge + end state + quick stats */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        {/* Composite Gauge — SMALL */}
        <div className="flex flex-col items-center p-4 rounded border border-zinc-800 bg-zinc-900/50">
          <h3 className="text-xs font-mono text-zinc-500 mb-1">COMPOSITE</h3>
          <RadialGauge
            value={isIndeterminate ? 0 : compositeScore}
            max={30}
            size={100}
            color={gaugeColor.stroke}
            label={gaugeColor.label}
            sublabel="0-30"
          />
        </div>

        {/* End State */}
        <div className="flex flex-col items-center justify-center p-4 rounded border border-zinc-800 bg-zinc-900/50">
          <h3 className="text-xs font-mono text-zinc-500 mb-1">END STATE</h3>
          <span className={`text-xl font-mono font-bold text-center leading-none ${END_STATE_COLORS[report?.end_state ?? "unknown"]?.replace("bg-", "text-") ?? "text-zinc-400"}`}>
            {(report?.end_state ?? "?").replace(/_/g, " ").toUpperCase()}
          </span>
          <span className="text-xs text-zinc-500 mt-2">
            confidence {report?.confidence ? Math.round(parseFloat(report.confidence) * 100) : "?"}%
          </span>
        </div>

        {/* Active Dot Count */}
        <div className="flex flex-col items-center justify-center p-4 rounded border border-zinc-800 bg-zinc-900/50">
          <h3 className="text-xs font-mono text-zinc-500 mb-1">ACTIVE DOTS</h3>
          <span className={`text-2xl font-mono font-bold ${activeDotCount > 0 ? "text-amber-400" : "text-emerald-400"}`}>
            {activeDotCount}
          </span>
          <span className="text-xs text-zinc-500 mt-1">of {dots.length} total</span>
        </div>

        {/* Alert Volume */}
        <div className="flex flex-col items-center justify-center p-4 rounded border border-zinc-800 bg-zinc-900/50">
          <h3 className="text-xs font-mono text-zinc-500 mb-1">ALERTS (7D)</h3>
          <Sparkline data={sparkData} width={100} height={28} color="auto" />
          <span className="text-xs text-zinc-500 mt-1">{alerts?.length ?? 0} triggers</span>
        </div>
      </div>

      {/* Stories Section */}
      <div>
        <h3 className="text-sm font-mono text-zinc-500 mb-3 uppercase tracking-wider">Stories</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {stories.slice(0, 8).map((story, idx) => (
            <button
              key={idx}
              type="button"
              onClick={() => setPopup(story)}
              className="text-left p-4 rounded border border-zinc-800 bg-zinc-900/50 hover:border-zinc-600 hover:bg-zinc-900/80 transition-colors cursor-pointer"
            >
              <div className="flex items-center gap-2 mb-1">
                <span className="text-xs font-mono text-zinc-500 uppercase">{story.category}</span>
              </div>
              <h4 className="text-base font-semibold text-zinc-200 mb-1">{story.title}</h4>
              <p className="text-sm text-zinc-500 leading-relaxed line-clamp-2 overflow-hidden">
                {story.body}
              </p>
            </button>
          ))}
          {stories.length === 0 && (
            <p className="text-xs text-zinc-600 col-span-2">No stories to display. Run a pipeline to generate data.</p>
          )}
        </div>
      </div>

      {/* Pathway Status */}
      <div className="p-4 rounded border border-zinc-800 bg-zinc-900/50">
        <h3 className="text-xs font-mono text-zinc-500 mb-3">PATHWAY STATUS</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
          {(pathways ?? []).map((pw, idx) => {
            const pwName = getPathwayName(pw);
            return (
              <div key={`pw-${pw.pathway}-${idx}`} className="flex items-center gap-2 px-2 py-1.5 rounded bg-zinc-900/40">
                <span className={`w-2 h-2 rounded-full ${pw.active ? "bg-emerald-400" : "bg-zinc-700"}`} />
                <span className="text-xs font-mono text-zinc-300 flex-1">{pwName}</span>
                <span className={`text-xs font-mono ${pw.active ? "text-emerald-400" : "text-zinc-600"}`}>
                  {pw.active ? "ACTIVE" : "dormant"}
                </span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Category Status */}
      <div className="p-4 rounded border border-zinc-800 bg-zinc-900/50">
        <h3 className="text-xs font-mono text-zinc-500 mb-3">CATEGORY STATUS</h3>
        <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
          {(indicators ?? []).slice(0, 10).map((ind, i) => {
            const statusColor =
              ind.status === "critical" ? "bg-red-600/60" :
              ind.status === "active" || ind.status === "activating" ? "bg-amber-600/60" :
              "bg-zinc-800";
            return (
              <div key={i} className="flex items-center gap-2 px-2 py-1.5 rounded bg-zinc-900/40">
                <span className={`w-2 h-2 rounded-full ${statusColor}`} />
                <span className="text-xs font-mono text-zinc-400 truncate">{ind.name}</span>
                <span className="text-xs text-zinc-600 ml-auto">{ind.value}</span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Category RSS Scores */}
      {report?.category_rss_scores && Object.keys(report.category_rss_scores).length > 0 && (
        <div className="p-4 rounded border border-zinc-800 bg-zinc-900/50 mt-4">
          <h3 className="text-xs font-mono text-zinc-500 mb-3">CATEGORY RSS SCORES</h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
            {Object.entries(report.category_rss_scores).map(([cat, score]) => (
              <div key={cat} className="flex flex-col p-2 rounded bg-zinc-900/40">
                <span className="text-[10px] font-mono text-zinc-500 uppercase truncate">
                  {CATEGORY_NAMES[cat] || cat}
                </span>
                <span className="text-sm font-mono text-zinc-300">
                  {score.toFixed(3)}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

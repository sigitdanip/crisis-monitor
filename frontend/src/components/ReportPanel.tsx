"use client";
import { useState, useMemo, useEffect } from "react";
import type { DashboardData, KeyQuestion, FiveQuestions, HistoryReport } from "@/types";
import { getDotDisplayName, getPathwayName } from "@/types";
import { END_STATE_COLORS, compositeColor, STATUS_COLORS, STATUS_ORDER, PATHWAY_COLORS } from "@/lib/colors";
import { RadialGauge } from "./ui/RadialGauge";
import { Sparkline } from "./ui/Sparkline";
import { fetchHistory } from "@/lib/api";

export function ReportPanel({ data }: { data: DashboardData }) {
  const { report, dots, pathways, indicators, alerts } = data;
  const [expandedQ, setExpandedQ] = useState<Set<number>>(new Set());

  if (!report) {
    return <div className="flex-1 flex items-center justify-center text-zinc-600 font-mono text-sm">No report data available</div>;
  }

  const endState = report.end_state;
  const endColor = END_STATE_COLORS[endState] ?? END_STATE_COLORS.unknown;
  const confidence = Math.round(parseFloat(report.confidence ?? "0") * 100) || 0;
  const c = compositeColor(report.composite_score ?? 0);

  // Parse 5 questions — server returns parsed object
  interface QuestionItem extends KeyQuestion { key: string }
  let questions: QuestionItem[] = [];
  try {
    const parsed: FiveQuestions | Record<string, unknown> = report.five_questions;
    if (Array.isArray(parsed)) {
      questions = (parsed as unknown as Record<string, unknown>[]).map((item, idx: number) => ({
        key: `q${idx + 1}`,
        question: String(item.question ?? item.q ?? `Question ${idx + 1}`),
        answer: String(item.answer ?? item.a ?? ""),
        verdict: item.verdict ? String(item.verdict) : undefined,
        assessment: item.assessment ? String(item.assessment) : undefined,
      }));
    } else {
      questions = Object.entries(parsed ?? {}).map(([key, val]) => {
        if (typeof val === "object" && val !== null) {
          const v = val as Record<string, unknown>;
          return {
            key,
            question: String(v.question ?? key),
            answer: String(v.answer ?? ""),
            verdict: v.verdict ? String(v.verdict) : undefined,
            assessment: v.assessment ? String(v.assessment) : undefined,
            trigger_region: v.trigger_region ? String(v.trigger_region) : undefined,
            trigger_probability: typeof v.trigger_probability === "number" ? v.trigger_probability : undefined,
            probability: typeof v.probability === "number" ? v.probability : undefined,
            indicator: v.indicator ? String(v.indicator) : undefined,
            rationale: v.rationale ? String(v.rationale) : undefined,
          };
        }
        return {
          key,
          question: String(key),
          answer: String(val),
        };
      });
    }
  } catch { questions = []; }

  // Dot delta (simulated — compare with previous)
  const sortedDots = [...(dots ?? [])].sort(
    (a, b) => (STATUS_ORDER[a.status] ?? 9) - (STATUS_ORDER[b.status] ?? 9)
  );

  // 7-day trajectory — fetched from real report history, client-only.
  // SSR-safe: initial state uses placeholder labels + current score.
  interface TrajectoryDay {
    label: string;
    score: number;
  }
  const [trajectoryDays, setTrajectoryDays] = useState<TrajectoryDay[]>(() =>
    Array.from({ length: 8 }, (_, i) => ({
      label: "—",
      score: report.composite_score,
    })),
  );
  useEffect(() => {
    let cancelled = false;
    fetchHistory(7)
      .then((history: HistoryReport[]) => {
        if (cancelled) return;
        const days: TrajectoryDay[] = [];
        // History is newest-first; we want oldest-first for left-to-right display
        const reversed = [...history].reverse();
        for (const h of reversed) {
          const d = new Date(h.date + "T00:00:00");
          days.push({
            label: d.toLocaleDateString("en", { weekday: "short" }),
            score: h.composite_score,
          });
        }
        if (days.length > 0) {
          setTrajectoryDays(days);
        }
      })
      .catch(() => {
        // keep placeholder data on fetch error
      });
    return () => { cancelled = true; };
  }, [report.composite_score]);

  // Sparkline data
  const sparkData = useMemo(() => {
    return (indicators ?? []).slice(0, 15).map((i) => i.value ?? 0);
  }, [indicators]);

  function toggleQ(idx: number) {
    setExpandedQ((prev) => {
      const next = new Set(prev);
      if (next.has(idx)) next.delete(idx);
      else next.add(idx);
      return next;
    });
  }

  return (
    <div className="flex-1 overflow-auto p-4 space-y-4 md:p-6 md:space-y-6">
      {/* 0. Daily Briefing */}
      {report.briefing?.trim() && (
        <div className="p-5 rounded border border-zinc-700 bg-zinc-900/60">
          <h2 className="text-xs font-mono text-zinc-500 mb-4">DAILY BRIEFING</h2>
          <div className="space-y-3">
            {report.briefing.split(/\n\s*\n/).filter(Boolean).map((para, i) => (
              <p key={i} className="font-sans text-xs leading-relaxed text-zinc-300">
                {para.trim()}
              </p>
            ))}
          </div>
        </div>
      )}

      {/* 1. End State Banner */}
      <div className={`p-4 md:p-5 rounded border ${endColor.replace("bg-", "border-")} ${endColor.replace("bg-", "bg-")}/10`}>
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div>
            <span className="text-[10px] md:text-xs font-mono text-zinc-500">END STATE ASSESSMENT</span>
            <h2 className={`text-lg md:text-xl font-mono font-bold mt-1 ${endColor.replace("bg-", "text-")}`}>
              {endState.toUpperCase()}
            </h2>
            <p className="text-[10px] md:text-xs text-zinc-400 mt-1">{report.synthesis?.slice(0, 120)}...</p>
          </div>
          <div className="flex items-center gap-4">
            <RadialGauge value={confidence} max={100} size={80} color="#f97316" label="Confidence" />
            <RadialGauge value={report.composite_score} max={30} size={80} color={c.stroke} label="Composite" />
          </div>
        </div>
      </div>

      {/* 2. Active Pathways */}
      <div className="p-4 rounded border border-zinc-800 bg-zinc-900/50">
        <h3 className="text-xs font-mono text-zinc-500 mb-3">PATHWAY ACTIVATION</h3>
        <div className="space-y-2">
          {(pathways ?? []).map((pw, idx) => {
            const pwName = getPathwayName(pw);
            const pwColor = PATHWAY_COLORS[pw.pathway];
            return (
            <div key={`pw-${pw.pathway}-${idx}`} className="space-y-1">
              <div className="flex items-center gap-2">
                <span className={`text-lg ${pw.active ? "text-emerald-400" : "text-zinc-700"}`}>
                  {pw.active ? "●" : "○"}
                </span>
                <span className="text-xs font-mono text-zinc-300">{pwName}</span>
              </div>
              {pw.description && (
                <p className="text-xs text-zinc-500 ml-6 leading-relaxed">{pw.description}</p>
              )}
            </div>
          )})}
          {(!pathways || pathways.length === 0) && (
            <span className="text-xs text-zinc-600">No pathway data</span>
          )}
        </div>
      </div>

      {/* 3. Situation Summary */}
      <div className="p-4 rounded border border-zinc-800 bg-zinc-900/50">
        <h3 className="text-xs font-mono text-zinc-500 mb-3">SITUATION SUMMARY</h3>
        <p className="text-xs text-zinc-400 leading-relaxed max-w-none">{report.synthesis}</p>
        <div className="flex items-center gap-3 md:gap-4 mt-3 flex-wrap">
          <div>
            <span className="text-[10px] md:text-xs font-mono text-zinc-600 block mb-1">COMPOSITE TREND</span>
            <Sparkline data={trajectoryDays.map((d) => d.score)} width={140} height={28} color="auto" />
          </div>
          <div>
            <span className="text-xs font-mono text-zinc-600 block mb-1">INDICATORS</span>
            <Sparkline data={sparkData.slice(0, 8)} width={100} height={24} color="auto" />
          </div>
        </div>
      </div>

      {/* 4. Five Key Questions */}
      <div className="p-4 rounded border border-zinc-800 bg-zinc-900/50">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-xs font-mono text-zinc-500">5 KEY QUESTIONS</h3>
          <button
            type="button"
            onClick={() => {
              if (expandedQ.size === questions.length) setExpandedQ(new Set());
              else setExpandedQ(new Set(questions.map((_, i) => i)));
            }}
            className="text-xs font-mono text-zinc-600 hover:text-zinc-400"
          >
            {expandedQ.size === questions.length ? "Collapse all" : "Expand all"}
          </button>
        </div>
        <div className="space-y-2">
          {questions.map((item, idx) => {
            const isExpanded = expandedQ.has(idx);
            return (
              <div key={idx} className="border border-zinc-800 rounded overflow-hidden">
                <button
                  type="button"
                  onClick={() => toggleQ(idx)}
                  className="w-full flex items-center gap-2 px-3 py-2 text-left hover:bg-zinc-900/50"
                >
                  <span className="text-xs font-mono text-zinc-600">Q{idx + 1}</span>
                  <span className="text-sm font-mono text-zinc-300 flex-1">{item.question}</span>
                  <span className="text-xs text-zinc-600">{isExpanded ? "▲" : "▼"}</span>
                </button>
                {isExpanded && (
                  <div className="px-3 pb-3 pt-1 border-t border-zinc-800/50">
                    <p className="text-sm text-zinc-400 leading-relaxed">{item.answer}</p>
                    {(item.verdict || item.assessment) && (
                      <div className="mt-2 flex flex-wrap gap-2">
                        {item.verdict && (
                          <span className="text-xs font-mono px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-400">
                            verdict: {item.verdict}
                          </span>
                        )}
                        {item.assessment && (
                          <span className="text-xs font-mono px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-400">
                            assessment: {item.assessment}
                          </span>
                        )}
                      </div>
                    )}
                    <div className="mt-2">
                      <span className="text-xs font-mono text-zinc-600">Supporting indicators:</span>
                      <div className="flex flex-wrap gap-1 mt-1">
                        {(indicators ?? []).slice(0, 3).map((ind) => (
                          <span key={ind.name} className="text-xs font-mono px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-500">
                            {ind.name}: {ind.value?.toFixed(1)} {ind.unit}
                          </span>
                        ))}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
          {questions.length === 0 && (
            <span className="text-xs text-zinc-600">No questions available</span>
          )}
        </div>
      </div>

      {/* 5. Dot Status Delta */}
      <div className="p-4 rounded border border-zinc-800 bg-zinc-900/50">
        <h3 className="text-xs font-mono text-zinc-500 mb-3">DOT STATUS</h3>
        <div className="space-y-1">
          {sortedDots.map((dot, idx) => {
            const dc = STATUS_COLORS[dot.status];
            return (
              <div key={`dot-${dot.dot_number}-${idx}`} className="flex items-center gap-3 px-2 py-1 rounded bg-zinc-900/40">
                <span className="text-xs font-mono text-zinc-600 w-8">D{dot.dot_number}</span>
                <span className="text-xs font-mono text-zinc-400 flex-1">{getDotDisplayName(dot.dot_name)}</span>
                <span className={`w-2 h-2 rounded-full ${dc.dot}`} />
                <span className={`text-xs font-mono ${dc.text}`}>{dot.status}</span>
              </div>
            );
          })}
        </div>
      </div>

      {/* 6. End State Trajectory (7-day) */}
      <div className="p-4 rounded border border-zinc-800 bg-zinc-900/50">
        <h3 className="text-[10px] md:text-xs font-mono text-zinc-500 mb-3">7-DAY TRAJECTORY</h3>
        <div className="flex items-center gap-1 md:gap-2 overflow-x-auto pb-1">
          {trajectoryDays.map((day, i) => {
            const dayColor = compositeColor(day.score);
            const isToday = i === trajectoryDays.length - 1;
            return (
              <div
                key={i}
                className={`flex flex-col items-center px-2 py-1.5 rounded font-mono ${
                  isToday ? "border border-zinc-400 bg-zinc-800" : "bg-zinc-900/60"
                }`}
              >
                <span suppressHydrationWarning className="text-xs text-zinc-500">{day.label}</span>
                <span className={`text-sm font-bold ${dayColor.text}`}>{day.score}</span>
              </div>
            );
          })}
        </div>
      </div>

      {/* 7. Footer */}
      <div className="flex items-center justify-between text-xs font-mono text-zinc-600 border-t border-zinc-800 pt-3">
        <span suppressHydrationWarning>Generated: {new Date(report.created_at).toLocaleString()}</span>
        <span>Next run: daily at 08:00</span>
      </div>
    </div>
  );
}

"use client";
import { useState, useEffect, useCallback, useRef } from "react";
import type { TimeseriesResponse, TimeseriesPoint } from "@/types";
import { fetchTimeseriesByDays } from "@/lib/api";
import { usePolling } from "@/lib/usePolling";
import { formatMonthDay, formatMonthDayTime } from "@/lib/datetime";
import { compositeColor } from "@/lib/colors";

// Y-axis zones for the 0-30 scale
const ZONE_COLORS = [
  { max: 6, bg: "rgba(16,185,129,0.15)", line: "#10b981", label: "Normal" },
  { max: 12, bg: "rgba(245,158,11,0.15)", line: "#f59e0b", label: "Monitor" },
  { max: 20, bg: "rgba(249,115,22,0.15)", line: "#f97316", label: "Elevated" },
  { max: 25, bg: "rgba(239,68,68,0.15)", line: "#ef4444", label: "Alert" },
  { max: 30, bg: "rgba(225,29,72,0.15)", line: "#e11d48", label: "Critical" },
];

// Chart dimensions
const CHART_H = 160;
const PAD_L = 36;
const PAD_R = 12;
const PAD_T = 8;
const PAD_B = 20;

function drawZoneBands(ctx: CanvasRenderingContext2D, w: number, h: number) {
  const plotH = h - PAD_T - PAD_B;
  for (const zone of ZONE_COLORS) {
    const idx = ZONE_COLORS.indexOf(zone);
    const prevMax = idx > 0 ? ZONE_COLORS[idx - 1].max : 0;
    const yBottom = PAD_T + plotH * (1 - prevMax / 30);
    const yTop = PAD_T + plotH * (1 - zone.max / 30);
    ctx.fillStyle = zone.bg;
    ctx.fillRect(PAD_L, yTop, w - PAD_L - PAD_R, yBottom - yTop);
  }
}

function drawYAxis(ctx: CanvasRenderingContext2D, h: number, w: number) {
  const plotH = h - PAD_T - PAD_B;
  ctx.fillStyle = "#71717a";
  ctx.font = "9px monospace";
  ctx.textAlign = "right";
  for (let score = 0; score <= 30; score += 6) {
    const y = PAD_T + plotH * (1 - score / 30);
    ctx.fillText(String(score), PAD_L - 4, y + 3);
    ctx.strokeStyle = "#27272a";
    ctx.beginPath();
    ctx.moveTo(PAD_L, y);
    ctx.lineTo(w - PAD_R, y);
    ctx.stroke();
  }
}

function drawXAxis(
  ctx: CanvasRenderingContext2D,
  points: TimeseriesPoint[],
  h: number,
  w: number,
  days: number,
) {
  if (points.length < 2) return;
  const plotW = w - PAD_L - PAD_R;
  const stepX = plotW / Math.max(points.length - 1, 1);
  const plotH = h - PAD_T - PAD_B;
  const yBase = PAD_T + plotH + 14; // below the plot area

  ctx.fillStyle = "#52525b";
  ctx.font = "8px monospace";
  ctx.textAlign = "center";

  // Choose label spacing based on range
  const skip = days <= 1 ? 1 : days <= 7 ? 1 : 3; // every point for 1d, every point for 7d, every 3rd for 30d

  for (let i = 0; i < points.length; i += skip) {
    const pt = points[i];
    const x = PAD_L + i * stepX;
    const label = formatMonthDay(pt.recorded_at);
    ctx.fillText(label, x, yBase);
  }
}

function drawLine(
  ctx: CanvasRenderingContext2D,
  points: TimeseriesPoint[],
  h: number,
  color: string,
  w: number,
) {
  if (points.length < 2) return;
  const plotW = w - PAD_L - PAD_R;
  const plotH = h - PAD_T - PAD_B;

  ctx.strokeStyle = color;
  ctx.lineWidth = 1.5;
  ctx.lineJoin = "round";
  ctx.beginPath();

  const stepX = plotW / Math.max(points.length - 1, 1);
  points.forEach((pt, i) => {
    const x = PAD_L + i * stepX;
    const y = PAD_T + plotH * (1 - Math.min(pt.value, 30) / 30);
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.stroke();

  // Draw dots on every data point (capped at 80 for performance)
  const dotLimit = Math.min(points.length, 80);
  ctx.fillStyle = color;
  for (let i = 0; i < dotLimit; i++) {
    const pt = points[i];
    const x = PAD_L + i * stepX;
    const y = PAD_T + plotH * (1 - Math.min(pt.value, 30) / 30);
    const radius = i === points.length - 1 ? 3 : 2;
    ctx.beginPath();
    ctx.arc(x, y, radius, 0, Math.PI * 2);
    ctx.fill();
  }
}

interface TooltipData {
  x: number;
  y: number;
  indicatorName: string;
  value: number;
  status: string;
  time: string;
}

function TimeseriesChart({
  title,
  unit,
  points,
  days,
  height = CHART_H,
}: {
  title: string;
  unit: string;
  points: TimeseriesPoint[];
  days: number;
  height?: number;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [tooltip, setTooltip] = useState<TooltipData | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [chartW, setChartW] = useState(600);

  // ResizeObserver: track container width, clamp to [320, 800], redraw on change
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    let rafId: number;

    const observer = new ResizeObserver((entries) => {
      const width = entries[0]?.contentRect.width;
      if (!width) return;
      cancelAnimationFrame(rafId);
      rafId = requestAnimationFrame(() => {
        setChartW(Math.min(800, Math.max(320, Math.round(width))));
      });
    });

    observer.observe(container);
    return () => {
      observer.disconnect();
      cancelAnimationFrame(rafId);
    };
  }, []);

  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    canvas.width = chartW * dpr;
    canvas.height = height * dpr;
    canvas.style.width = `${chartW}px`;
    canvas.style.height = `${height}px`;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    ctx.clearRect(0, 0, chartW, height);

    // Zone bands
    drawZoneBands(ctx, chartW, height);

    // Y axis
    drawYAxis(ctx, height, chartW);

    // X axis (date labels)
    if (points.length > 0) {
      drawXAxis(ctx, points, height, chartW, days);
    }

    // Data line
    if (points.length > 0) {
      const lastPt = points[points.length - 1];
      const c = compositeColor(Math.min(lastPt.value, 30));
      drawLine(ctx, points, height, c.stroke, chartW);
    }
  }, [points, height, chartW, days]);

  useEffect(() => {
    draw();
  }, [draw]);

  const handleMouseMove = useCallback(
    (e: React.MouseEvent<HTMLCanvasElement>) => {
      const canvas = canvasRef.current;
      const container = containerRef.current;
      if (!canvas || !container || points.length < 2) return;

      const rect = canvas.getBoundingClientRect();
      const scaleX = chartW / rect.width;
      const mx = (e.clientX - rect.left) * scaleX;

      const plotW = chartW - PAD_L - PAD_R;
      const stepX = plotW / (points.length - 1);
      const idx = Math.round((mx - PAD_L) / stepX);
      if (idx < 0 || idx >= points.length) {
        setTooltip(null);
        return;
      }

      const pt = points[idx];
      const x = PAD_L + idx * stepX;
      const plotH = height - PAD_T - PAD_B;
      const y = PAD_T + plotH * (1 - Math.min(pt.value, 30) / 30);

      setTooltip({
        x: x / scaleX,
        y: y / scaleX,
        indicatorName: title,
        value: pt.value,
        status: pt.status,
        time: formatMonthDayTime(pt.recorded_at),
      });
    },
    [points, title, height, chartW],
  );

  const handleMouseLeave = useCallback(() => setTooltip(null), []);

  const lastStatus = points.length > 0 ? points[points.length - 1].status : "";
  const statusColor =
    lastStatus === "critical" ? "text-red-400" :
    lastStatus === "breached" ? "text-amber-400" :
    "text-zinc-500";

  return (
    <div ref={containerRef} className="relative">
      <div className="flex items-center gap-2 mb-1">
        <span className="text-xs font-mono text-zinc-400">{title}</span>
        <span className={`text-[10px] font-mono ${statusColor}`}>
          {lastStatus ? lastStatus.toUpperCase() : ""}
        </span>
      </div>
      <canvas
        ref={canvasRef}
        className="w-full cursor-crosshair"
        style={{ height }}
        onMouseMove={handleMouseMove}
        onMouseLeave={handleMouseLeave}
      />
      {tooltip && (
        <div
          className="absolute z-50 pointer-events-none bg-zinc-900 border border-zinc-600 px-2 py-1.5 rounded text-[10px] font-mono text-zinc-200 whitespace-nowrap"
          style={{ left: tooltip.x + 8, top: tooltip.y - 40 }}
        >
          <div>{tooltip.indicatorName}</div>
          <div>
            {tooltip.value.toFixed(2)} {unit}
          </div>
          <div className={tooltip.status === "critical" ? "text-red-400" : tooltip.status === "breached" ? "text-amber-400" : "text-zinc-500"}>
            [{tooltip.status.toUpperCase()}]
          </div>
          <div className="text-zinc-600">{tooltip.time}</div>
        </div>
      )}
    </div>
  );
}

// eslint-disable-next-line @typescript-eslint/no-unused-vars
export function TimeseriesPanel({ data }: { data: import("@/types").DashboardData }) {
  const [timeseries, setTimeseries] = useState<TimeseriesResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedCategory, setSelectedCategory] = useState<string>("all");
  const [days, setDays] = useState(7);

  const loadTimeseries = useCallback(async () => {
    try {
      const ts = await fetchTimeseriesByDays(days);
      setTimeseries(ts);
      setError(null);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Unknown error";
      // 404 = endpoint not implemented yet — show info, not error
      if (msg.includes("404")) {
        setError("Timeseries endpoint not yet available (pending api-dev card t_dd4e3e49)");
      } else {
        setError(msg);
      }
    } finally {
      setLoading(false);
    }
  }, [days]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- standard fetch-on-mount via useCallback
    loadTimeseries();
  }, [loadTimeseries]);

  // Poll every 24h (daily pipeline runs at 8am)
  usePolling(loadTimeseries, 24 * 60 * 60 * 1000);

  // Extract categories from the series data
  const categories = timeseries?.series
    ? [...new Set(timeseries.series.map((s) => s.category))]
    : [];

  const filteredSeries = timeseries?.series?.filter(
    (s) => selectedCategory === "all" || s.category === selectedCategory,
  ) ?? [];

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <span className="text-sm font-mono text-zinc-600 animate-pulse">Loading timeseries data...</span>
      </div>
    );
  }

  if (error && !timeseries) {
    return (
      <div className="flex-1 flex items-center justify-center flex-col gap-2 p-4">
        <span className="text-sm font-mono text-amber-400">Timeseries unavailable</span>
        <span className="text-xs font-mono text-zinc-600">{error}</span>
        <button
          type="button"
          onClick={() => { setLoading(true); setError(null); loadTimeseries(); }}
          className="mt-2 text-xs font-mono text-zinc-400 border border-zinc-700 px-3 py-1 hover:bg-zinc-900"
        >
          Retry
        </button>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-auto p-4 space-y-4 md:p-6 md:space-y-6">
      {/* Range Tabs */}
      <div className="flex items-center gap-2 flex-wrap">
        {[1, 7, 30].map((d) => (
          <button
            key={d}
            type="button"
            onClick={() => setDays(d)}
            className={`text-xs font-mono px-2 py-1 rounded border ${
              days === d
                ? "border-zinc-400 text-zinc-200 bg-zinc-800"
                : "border-zinc-700 text-zinc-500 hover:border-zinc-600"
            }`}
          >
            {d}D
          </button>
        ))}
      </div>

      {/* Composite Score Timeseries */}
      {timeseries?.composite_series && timeseries.composite_series.length > 0 && (
        <div className="p-3 md:p-4 rounded border border-zinc-800 bg-zinc-900/50">
          <h3 className="text-[10px] md:text-xs font-mono text-zinc-500 mb-3">
            COMPOSITE SCORE — LAST {days} {days === 1 ? "DAY" : "DAYS"}
          </h3>
          <TimeseriesChart
            title="Composite Score"
            unit="pts"
            points={timeseries.composite_series.map((p) => ({
              recorded_at: p.recorded_at,
              value: p.composite_score,
              status: p.interpretation,
            }))}
            days={days}
            height={200}
          />
        </div>
      )}

      {/* Category Filter */}
      {categories.length > 0 && (
        <div className="flex items-center gap-2 flex-wrap">
          <button
            type="button"
            onClick={() => setSelectedCategory("all")}
            className={`text-xs font-mono px-2 py-1 rounded border ${
              selectedCategory === "all"
                ? "border-zinc-400 text-zinc-200 bg-zinc-800"
                : "border-zinc-700 text-zinc-500 hover:border-zinc-600"
            }`}
          >
            ALL
          </button>
          {categories.map((cat) => (
            <button
              key={cat}
              type="button"
              onClick={() => setSelectedCategory(cat)}
              className={`text-xs font-mono px-2 py-1 rounded border capitalize ${
                selectedCategory === cat
                  ? "border-zinc-400 text-zinc-200 bg-zinc-800"
                  : "border-zinc-700 text-zinc-500 hover:border-zinc-600"
              }`}
            >
              {cat.replace(/_/g, " ")}
            </button>
          ))}
        </div>
      )}

      {/* Per-Indicator Timeseries */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {filteredSeries.map((series) => (
          <div
            key={series.indicator_name}
            className="p-3 rounded border border-zinc-800 bg-zinc-900/50"
          >
            <TimeseriesChart
              title={series.display_name || series.indicator_name}
              unit={series.unit || ""}
              points={series.points}
              days={days}
            />
          </div>
        ))}
      </div>

      {filteredSeries.length === 0 && timeseries && (
        <p className="text-xs text-zinc-600 text-center">
          {selectedCategory === "all"
            ? "Waiting for first daily snapshot at 8am"
            : `No indicators in category "${selectedCategory.replace(/_/g, " ")}"`}
        </p>
      )}

      {/* Footer with date range */}
      {timeseries?.from && (
        <div className="flex items-center justify-between text-[10px] font-mono text-zinc-600 border-t border-zinc-800 pt-3">
          <span suppressHydrationWarning>
            {formatMonthDay(timeseries.from)} — {formatMonthDay(timeseries.to)}
          </span>
          <span>Updates daily</span>
        </div>
      )}
    </div>
  );
}

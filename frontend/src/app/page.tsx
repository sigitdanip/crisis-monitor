"use client";
import { useState, useEffect, useCallback } from "react";
import type { DashboardData } from "@/types";
import { formatTimeSec } from "@/lib/datetime";
import { fetchDashboard } from "@/lib/api";
import { usePolling } from "@/lib/usePolling";
import { Header } from "@/components/Header";
import { TabBar, type TabId } from "@/components/TabBar";
import { OverviewTab } from "@/components/OverviewTab";
import { DotsPanel } from "@/components/DotsPanel";
import { IndicatorsPanel } from "@/components/IndicatorsPanel";
import { ReportPanel } from "@/components/ReportPanel";
import { AlertsPanel } from "@/components/AlertsPanel";
import { HistoryPanel } from "@/components/HistoryPanel";
import { PipelinePanel } from "@/components/PipelinePanel";
import { TimeseriesPanel } from "@/components/TimeseriesPanel";

const EMPTY_DATA: DashboardData = {
  indicators: [],
  dots: [],
  pathways: [],
  report: null,
  alerts: [],
};

const LS_KEY = "crisis-monitor:cache:dashboard";

interface CacheEntry {
  data: DashboardData;
  cachedAt: number;
}

function readCache(): CacheEntry | null {
  try {
    const raw = localStorage.getItem(LS_KEY);
    if (!raw) return null;
    const parsed: CacheEntry = JSON.parse(raw);
    if (parsed?.data?.report) return parsed;
    return null;
  } catch {
    return null;
  }
}

function writeCache(data: DashboardData): void {
  try {
    // safe: client-only (localStorage is not available during SSR)
    const entry: CacheEntry = { data, cachedAt: Date.now() };
    localStorage.setItem(LS_KEY, JSON.stringify(entry));
  } catch {
    // quota exceeded — silently ignore
  }
}

export default function Home() {
  const [activeTab, setActiveTab] = useState<TabId>("overview");

  // HYDRATION-SAFE INITIAL STATE:
  // - `data` starts as EMPTY_DATA so server and first client render produce
  //   identical DOM. The localStorage cache is read inside the load() effect
  //   below, AFTER hydration completes.
  // - This is the root fix for the structural hydration mismatch on the
  //   "stale data" banner (page.tsx:168) and the "Loading dashboard data"
  //   spinner (page.tsx:110) — see related card t_d4212728.
  const [data, setData] = useState<DashboardData>(EMPTY_DATA);
  const [cachedAt, setCachedAt] = useState<number | null>(null);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      // 7s hard timeout is a BACKUP to the 5s AbortController in fetchWithTimeout.
      // If AbortController doesn't fire in some edge case, this ensures we never
      // hang indefinitely.
      const d = await Promise.race([
        fetchDashboard(),
        new Promise<never>((_, reject) =>
          setTimeout(
            () => reject(new Error("Request timed out after 7 seconds")),
            7000,
          ),
        ),
      ]);
      setData(d);
      writeCache(d);
      setCachedAt(null); // data is now fresh
      setError(null);
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : "Unknown error";
      setError(message);
      // Do NOT clear data — keep cached/stale data visible.
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    // Step 1: hydrate from localStorage (client-only, post-hydration).
    const cached = readCache();
    if (cached) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- intentional: client-only localStorage hydration after SSR
      setData(cached.data);
      setCachedAt(cached.cachedAt);
    }

    // Step 2: fetch fresh data from the API.
    load();
  }, [load]);

  // 30s polling — refreshes dashboard data without page reload
  usePolling(load, 30_000);

  const hasData = data.report !== null;
  const lastUpdated = data.report?.created_at ?? null;

  // ---- render helpers ----

  const renderContent = () => {
    // Cold load: no cached data and still waiting.
    if (!hasData && loading) {
      return (
        <div className="flex-1 flex items-center justify-center">
          <span className="text-sm font-mono text-zinc-600 animate-pulse">
            Loading dashboard data...
          </span>
        </div>
      );
    }

    // Cold load failed: no cached data and fetch errored.
    if (!hasData && error) {
      return (
        <div className="flex-1 flex items-center justify-center flex-col gap-2">
          <span className="text-sm font-mono text-red-400">
            Failed to load dashboard
          </span>
          <span className="text-xs font-mono text-zinc-600">{error}</span>
          <button
            type="button"
            onClick={() => {
              setError(null);
              setLoading(true);
              load();
            }}
            className="mt-4 text-xs font-mono text-zinc-400 border border-zinc-700 px-3 py-1 hover:bg-zinc-900"
          >
            Retry
          </button>
        </div>
      );
    }

    // Normal render with data (fresh or stale).
    return (
      <>
        {activeTab === "overview" && <OverviewTab data={data} />}
        {activeTab === "dots" && <DotsPanel data={data} />}
        {activeTab === "indicators" && <IndicatorsPanel data={data} />}
        {activeTab === "timeseries" && <TimeseriesPanel data={data} />}
        {activeTab === "report" && <ReportPanel data={data} />}
        {activeTab === "alerts" && <AlertsPanel data={data} />}
        {activeTab === "history" && <HistoryPanel data={data} />}
        {activeTab === "pipeline" && <PipelinePanel />}
      </>
    );
  };

  // ---- main render ----

  return (
    <div className="flex-1 flex flex-col min-h-0 overflow-x-hidden">
      <Header
        compositeScore={data.report?.composite_score ?? 0}
        lastUpdated={lastUpdated}
      />

      {/* Stale data indicator — shown when we have cached data but a fetch
          is still in flight. */}
      {hasData && loading && (
        <div className="flex items-center gap-2 px-4 py-1 border-b border-amber-900/50 bg-amber-950/30 shrink-0">
          <span className="inline-block w-2 h-2 rounded-full bg-amber-400 animate-pulse" />
          <span className="text-[10px] font-mono text-amber-400/80 md:text-xs">
            Stale data — refreshing...
          </span>
          {cachedAt != null && (
            <span suppressHydrationWarning className="text-[10px] font-mono text-zinc-600 md:text-xs">
              (cached {formatTimeSec(cachedAt)})
            </span>
          )}
        </div>
      )}

      {/* Error banner when we have data to show but the refresh failed.
          Data from cache stays visible; user can Retry without losing context. */}
      {hasData && error && !loading && (
        <div className="flex items-center gap-2 px-4 py-1 border-b border-red-900/50 bg-red-950/30 shrink-0">
          <span className="text-[10px] font-mono text-red-400 md:text-xs">
            Refresh failed: {error}
          </span>
          <button
            type="button"
            onClick={() => {
              setError(null);
              setLoading(true);
              load();
            }}
            className="text-[10px] font-mono text-red-400 border border-red-800 px-2 py-0.5 hover:bg-red-950 md:text-xs"
          >
            Retry
          </button>
        </div>
      )}

      {/* TabBar is always visible — all states (loading, error, success, stale). */}
      <TabBar active={activeTab} onChange={setActiveTab} />

      <div className="flex-1 flex flex-col min-h-0">
        {renderContent()}
      </div>
    </div>
  );
}

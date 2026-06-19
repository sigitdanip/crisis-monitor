"use client";
import { useState, useEffect, useCallback } from "react";
import type { DashboardData } from "@/types";
import { fetchDashboard } from "@/lib/api";
import { Header } from "@/components/Header";
import { TabBar, type TabId } from "@/components/TabBar";
import { OverviewTab } from "@/components/OverviewTab";
import { DotsPanel } from "@/components/DotsPanel";
import { IndicatorsPanel } from "@/components/IndicatorsPanel";
import { ReportPanel } from "@/components/ReportPanel";
import { AlertsPanel } from "@/components/AlertsPanel";
import { HistoryPanel } from "@/components/HistoryPanel";
import { PipelinePanel } from "@/components/PipelinePanel";

const EMPTY_DATA: DashboardData = {
  indicators: [],
  dots: [],
  pathways: [],
  report: null,
  alerts: [],
};

export default function Home() {
  const [activeTab, setActiveTab] = useState<TabId>("overview");
  const [data, setData] = useState<DashboardData>(EMPTY_DATA);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const d = await fetchDashboard();
      setData(d);
      setError(null);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  if (loading) {
    return (
      <div className="flex-1 flex flex-col overflow-x-hidden">
        <Header compositeScore={0} lastUpdated={null} />
        <div className="flex-1 flex items-center justify-center">
          <span className="text-sm font-mono text-zinc-600 animate-pulse">
            Loading dashboard data...
          </span>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex-1 flex flex-col overflow-x-hidden">
        <Header compositeScore={0} lastUpdated={null} />
        <div className="flex-1 flex items-center justify-center flex-col gap-2">
          <span className="text-sm font-mono text-red-400">Failed to load dashboard</span>
          <span className="text-xs font-mono text-zinc-600">{error}</span>
          <button
            type="button"
            onClick={() => { setLoading(true); load(); }}
            className="mt-4 text-xs font-mono text-zinc-400 border border-zinc-700 px-3 py-1 rounded hover:bg-zinc-900"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  const lastUpdated = data.report?.created_at ?? null;

  return (
    <div className="flex-1 flex flex-col min-h-0 overflow-x-hidden">
      <Header
        compositeScore={data.report?.composite_score ?? 0}
        lastUpdated={lastUpdated}
      />
      <TabBar active={activeTab} onChange={setActiveTab} />
      <div className="flex-1 flex flex-col min-h-0">
        {activeTab === "overview" && <OverviewTab data={data} />}
        {activeTab === "dots" && <DotsPanel data={data} />}
        {activeTab === "indicators" && <IndicatorsPanel data={data} />}
        {activeTab === "report" && <ReportPanel data={data} />}
        {activeTab === "alerts" && <AlertsPanel data={data} />}
        {activeTab === "history" && <HistoryPanel data={data} />}
        {activeTab === "pipeline" && <PipelinePanel />}
      </div>
    </div>
  );
}

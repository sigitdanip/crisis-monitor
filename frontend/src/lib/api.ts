import type { DashboardData, PipelineStatus, HistoryReport } from "@/types";

const BASE = "";

export async function fetchDashboard(): Promise<DashboardData> {
  const res = await fetch(`${BASE}/api/dashboard`);
  if (!res.ok) throw new Error(`Dashboard fetch failed: ${res.status}`);
  return res.json();
}

export async function fetchPipeline(): Promise<PipelineStatus> {
  const res = await fetch(`${BASE}/api/pipeline/status`);
  if (!res.ok) throw new Error(`Pipeline fetch failed: ${res.status}`);
  return res.json();
}

export async function fetchHistory(days = 30): Promise<HistoryReport[]> {
  const res = await fetch(`${BASE}/api/reports/history?days=${days}`);
  if (!res.ok) throw new Error(`History fetch failed: ${res.status}`);
  const data = await res.json();
  return data.reports ?? [];
}

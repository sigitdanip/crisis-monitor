import type { DashboardData, PipelineStatus, HistoryReport, TimeseriesResponse } from "@/types";

const BASE = "";
const DEFAULT_TIMEOUT = 5000; // 5s

async function fetchWithTimeout(
  url: string,
  init?: RequestInit,
  timeoutMs = DEFAULT_TIMEOUT,
): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const res = await fetch(url, {
      ...init,
      signal: controller.signal,
    });
    return res;
  } catch (err: unknown) {
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new Error(`Request timed out after ${timeoutMs / 1000}s`);
    }
    throw err;
  } finally {
    clearTimeout(timer);
  }
}

export async function fetchDashboard(): Promise<DashboardData> {
  const res = await fetchWithTimeout(`${BASE}/api/dashboard`);
  if (!res.ok) throw new Error(`Dashboard fetch failed: ${res.status}`);
  return res.json();
}

export async function fetchPipeline(): Promise<PipelineStatus> {
  const res = await fetchWithTimeout(`${BASE}/api/pipeline/status`);
  if (!res.ok) throw new Error(`Pipeline fetch failed: ${res.status}`);
  return res.json();
}

export async function fetchHistory(days = 30): Promise<HistoryReport[]> {
  const res = await fetchWithTimeout(`${BASE}/api/reports/history?days=${days}`);
  if (!res.ok) throw new Error(`History fetch failed: ${res.status}`);
  const data = await res.json();
  return data.reports ?? [];
}

export async function fetchTimeseries(minutes = 60): Promise<TimeseriesResponse> {
  const res = await fetchWithTimeout(`${BASE}/api/timeseries?minutes=${minutes}`);
  if (!res.ok) throw new Error(`Timeseries fetch failed: ${res.status}`);
  return res.json();
}

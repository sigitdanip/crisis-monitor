"use client";
import { useState, useEffect } from "react";
import type { FetcherHealthItem } from "@/types";
import { fetchFetcherHealth } from "@/lib/api";
import { formatDateTime } from "@/lib/datetime";

export function FetcherHealthPanel() {
  const [fetchers, setFetchers] = useState<FetcherHealthItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchFetcherHealth()
      .then((data) => {
        if (cancelled) return;
        setFetchers(data.fetchers ?? []);
        setError(null);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "Unknown error");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center text-zinc-600 font-mono text-sm">
        Loading fetcher health...
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex-1 flex items-center justify-center flex-col gap-2">
        <span className="text-sm font-mono text-red-400">
          Failed to load fetcher health
        </span>
        <span className="text-xs font-mono text-zinc-600">{error}</span>
      </div>
    );
  }

  if (!fetchers.length) {
    return (
      <div className="flex-1 flex items-center justify-center text-zinc-600 font-mono text-sm">
        No fetcher data available
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-auto p-4 md:p-6">
      <h2 className="text-xs md:text-sm font-mono text-zinc-400 mb-3 md:mb-4">
        FETCHER HEALTH{" "}
        <span className="text-zinc-600">({fetchers.length})</span>
      </h2>

      <div className="space-y-1">
        {fetchers.map((f) => {
          const isHealthy = f.consecutive_failures === 0;
          const successPct = Math.round((f.last_24h_success_rate ?? 1) * 100);

          return (
            <div
              key={f.fetcher_name}
              className="flex items-center gap-3 px-3 py-2 rounded border border-zinc-800 bg-zinc-900/40"
            >
              {/* Status indicator dot */}
              <span
                className={`w-2 h-2 rounded-full flex-shrink-0 ${
                  isHealthy ? "bg-emerald-400" : "bg-red-500 animate-pulse"
                }`}
              />

              {/* Fetcher name */}
              <span className="text-xs font-mono text-zinc-300 w-32 flex-shrink-0">
                {f.fetcher_name}
              </span>

              {/* Success rate bar */}
              <div className="flex-1 flex items-center gap-2 min-w-0">
                <div className="flex-1 h-1.5 rounded-full bg-zinc-800 overflow-hidden">
                  <div
                    className={`h-full rounded-full ${
                      successPct >= 80
                        ? "bg-emerald-500"
                        : successPct >= 50
                          ? "bg-amber-500"
                          : "bg-red-500"
                    }`}
                    style={{ width: `${successPct}%` }}
                  />
                </div>
                <span className="text-[10px] font-mono text-zinc-500 w-8 text-right">
                  {successPct}%
                </span>
              </div>

              {/* Consecutive failures */}
              <span className="text-[10px] font-mono text-zinc-500 w-16 text-right">
                {f.consecutive_failures > 0 ? (
                  <span className="text-red-400">
                    {f.consecutive_failures} fails
                  </span>
                ) : (
                  <span className="text-zinc-600">ok</span>
                )}
              </span>

              {/* Last success timestamp */}
              <span
                suppressHydrationWarning
                className="text-[10px] font-mono text-zinc-600 w-24 text-right hidden md:inline"
              >
                {f.last_success
                  ? formatDateTime(f.last_success).slice(0, 16)
                  : "—"}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

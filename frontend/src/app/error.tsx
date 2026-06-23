"use client";

import { useEffect } from "react";

interface ErrorPageProps {
  error: Error & { digest?: string };
  // Next.js 16 renamed `reset` to `unstable_retry` (v16.2.0).
  // It re-fetches and re-renders the error boundary's children,
  // which is the correct recovery for route-level errors.
  unstable_retry: () => void;
}

export default function ErrorPage({ error, unstable_retry }: ErrorPageProps) {
  useEffect(() => {
    // Log the full error to the browser console for debugging.
    console.error("[CrisisMonitor] Route error boundary caught:", error);
    if (error.digest) {
      console.error("[CrisisMonitor] Error digest (match server logs):", error.digest);
    }

    // Optional: send to backend error-reporting endpoint.
    // Fire-and-forget — we don't block the fallback UI on this.
    try {
      fetch("/api/health", { method: "HEAD" }).catch(() => {
        // Backend may be the cause of the error; swallow.
      });
    } catch {
      // Silently ignore.
    }
  }, [error]);

  return (
    <div className="flex-1 flex items-center justify-center min-h-screen bg-zinc-950">
      <div className="flex flex-col items-center gap-4 px-6 py-10 max-w-lg text-center">
        {/* Error icon — monospace ASCII-friendly */}
        <div className="text-4xl font-mono text-red-400 select-none">
          [!]
        </div>

        <h2 className="text-base font-mono font-bold text-zinc-100 md:text-lg">
          Something went wrong
        </h2>

        <p className="text-sm font-mono text-zinc-400 leading-relaxed md:text-base">
          {error.message || "An unexpected error occurred while rendering this page."}
        </p>

        {/* Digest shown in dev only — helps match server logs */}
        {error.digest && (
          <code className="text-[10px] font-mono text-zinc-600 break-all md:text-xs">
            Digest: {error.digest}
          </code>
        )}

        <div className="flex items-center gap-3 mt-2">
          <button
            type="button"
            onClick={() => unstable_retry()}
            className="text-xs font-mono text-zinc-200 border border-zinc-600 px-3 py-1.5 hover:bg-zinc-800 hover:border-zinc-500 transition-colors md:text-sm"
          >
            Reload
          </button>

          <a
            href={
              "mailto:?subject=" +
              encodeURIComponent("[CrisisMonitor] Client Error") +
              "&body=" +
              encodeURIComponent(
                `Error: ${error.message}\nDigest: ${error.digest || "N/A"}\nURL: ${typeof window !== "undefined" ? window.location.href : "N/A"}\nTime: ${new Date().toISOString()}`,
              )
            }
            className="text-xs font-mono text-zinc-500 border border-zinc-800 px-3 py-1.5 hover:text-zinc-300 hover:border-zinc-600 transition-colors md:text-sm"
          >
            Report Issue
          </a>
        </div>

        <p className="text-[10px] font-mono text-zinc-700 mt-6 md:text-xs">
          If this persists, check the browser console (F12) for details.
        </p>
      </div>
    </div>
  );
}

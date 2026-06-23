"use client";

import { useEffect } from "react";

interface GlobalErrorProps {
  error: Error & { digest?: string };
  unstable_retry: () => void;
}

/**
 * global-error.tsx — catches errors in the root layout itself.
 * Must define its own <html> + <body> since it replaces the
 * root layout/template when active.
 */
export default function GlobalError({ error, unstable_retry }: GlobalErrorProps) {
  useEffect(() => {
    console.error("[CrisisMonitor] Global error boundary caught:", error);
    if (error.digest) {
      console.error("[CrisisMonitor] Error digest:", error.digest);
    }
  }, [error]);

  return (
    <html lang="en" className="h-full antialiased">
      <head>
        <title>Crisis Monitor — Error</title>
        <meta name="viewport" content="width=device-width, initial-scale=1" />
      </head>
      <body className="h-full flex flex-col bg-zinc-950 text-zinc-100">
        <div className="flex-1 flex items-center justify-center">
          <div className="flex flex-col items-center gap-4 px-6 py-10 max-w-lg text-center">
            {/* Error icon */}
            <div className="text-4xl font-mono text-red-400 select-none">
              [!!]
            </div>

            <h2 className="text-base font-mono font-bold text-zinc-100 md:text-lg">
              Critical Error
            </h2>

            <p className="text-sm font-mono text-zinc-400 leading-relaxed md:text-base">
              The application failed to initialize.
            </p>

            <p className="text-xs font-mono text-zinc-500 md:text-sm">
              {error.message}
            </p>

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

              <button
                type="button"
                onClick={() => {
                  window.location.reload();
                }}
                className="text-xs font-mono text-zinc-500 border border-zinc-800 px-3 py-1.5 hover:text-zinc-300 hover:border-zinc-600 transition-colors md:text-sm"
              >
                Hard Reload
              </button>
            </div>

            <p className="text-[10px] font-mono text-zinc-700 mt-6 md:text-xs">
              Check the browser console (F12) for details, or try clearing your cache.
            </p>
          </div>
        </div>
      </body>
    </html>
  );
}

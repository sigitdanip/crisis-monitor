"use client";
import { useEffect, useRef } from "react";

/**
 * Generic polling hook. Calls `callback` every `intervalMs` milliseconds.
 * Cleans up on unmount or when deps change.
 */
export function usePolling(
  callback: () => void | Promise<void>,
  intervalMs: number,
  deps: unknown[] = [],
) {
  const savedCallback = useRef(callback);

  // Keep callback ref current after each render
  useEffect(() => {
    savedCallback.current = callback;
  });

  useEffect(() => {
    let timer: ReturnType<typeof setInterval> | null = null;
    let stopped = false;

    const tick = async () => {
      if (stopped) return;
      try {
        await savedCallback.current();
      } catch {
        // silently ignore polling errors — the page already handles fetch errors
      }
    };

    // Start polling
    timer = setInterval(tick, intervalMs);

    return () => {
      stopped = true;
      if (timer !== null) clearInterval(timer);
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [intervalMs, ...deps]);
}

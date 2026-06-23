"use client";

import { useEffect } from "react";

/**
 * Test page — deliberately throws an error to verify the error boundary.
 * Visit /test-error in the browser. You should see the error.tsx fallback UI
 * instead of a blank screen or Next.js default error overlay.
 *
 * DELETE THIS PAGE after verification.
 *
 * Wrapped in useEffect so the throw only happens client-side.
 * Throwing during SSR causes production `next build` to fail
 * (Next.js prerenders all pages, including client components).
 */

export default function TestErrorPage() {
  useEffect(() => {
    throw new Error(
      "Intentional test error: verifying the error boundary fallback UI renders correctly.",
    );
  }, []);

  return null;
}

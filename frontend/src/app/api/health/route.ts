import { NextResponse } from "next/server";

// P1-1: Health endpoint independent of SSR compilation.
// force-static ensures this route is served from the static module cache,
// not from Turbopack's RSC pipeline. Even during first-compile, this
// responds fast (<50ms) without triggering EPIPE cascades.
export const dynamic = "force-static";

export function GET() {
  return NextResponse.json({
    status: "ok",
    uptime: process.uptime(),
  });
}

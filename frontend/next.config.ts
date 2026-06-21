import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Next.js 16 blocks cross-origin requests to dev resources by default.
  // Without this, the dev server returns 403 for HMR + static chunks when
  // the user accesses the app via the external IP (e.g. http://187.77.130.62:3001)
  // instead of localhost. The page loads SSR HTML but JS bundles are blocked,
  // hydration fails, the page stays on the SSR initial state forever.
  // See: https://nextjs.org/docs/app/api-reference/config/next-config-js/allowedDevOrigins
  allowedDevOrigins: [
    "187.77.130.62",  // external IP — dev access from non-localhost networks
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
  ],
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: 'http://localhost:8001/api/:path*',
      },
    ];
  },
  // Hide the on-screen Next.js dev tools button (bottom-left by default).
  // The user finds it distracting and wants a clean view. Next.js still
  // surfaces compile/runtime errors in the terminal and console.
  // See: https://nextjs.org/docs/app/api-reference/config/next-config-js/devIndicators
  devIndicators: false,
};

export default nextConfig;

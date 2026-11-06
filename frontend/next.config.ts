import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // Sentry wrapping (`withSentryConfig`) lands in P2.10. Until then,
  // this is the bare Next.js config.
  // Build-time checks Link hrefs against the app/* file tree. Stable
  // since Next.js 15.5; it used to live under `experimental`.
  typedRoutes: true,
  // `output: "export"` is set conditionally via NEXT_OUTPUT=export at
  // build time. Used for one-off zip uploads to Amplify Hosting before
  // a GitHub auto-deploy connection is wired up. Once Amplify's
  // GitHub-driven build is live, we leave this flag off and let
  // Amplify's compute layer handle SSR/ISR natively.
  ...(process.env.NEXT_OUTPUT === "export" ? { output: "export" as const } : {}),
};

export default nextConfig;

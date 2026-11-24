import type { NextConfig } from "next";

const backend = (process.env.BACKEND_URL ?? "http://localhost:8000").replace(/\/$/, "");

const nextConfig: NextConfig = {
  poweredByHeader: false,
  // Keep SSE responses unbuffered through the rewrite proxy.
  compress: false,
  experimental: {
    // Local storage mode uploads PDFs through this proxy (production uploads go straight to Supabase).
    middlewareClientMaxBodySize: "60mb",
  },
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${backend}/api/:path*` }];
  },
};

export default nextConfig;

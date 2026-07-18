import type { NextConfig } from "next";

const basePath = "/apps/concordance";

const nextConfig: NextConfig = {
  basePath,
  compress: true,
  poweredByHeader: false,
  turbopack: {
    root: process.cwd()
  },
  async headers() {
    return [
      {
        source: "/api/:path*",
        headers: [
          { key: "Cache-Control", value: "public, s-maxage=60, stale-while-revalidate=300" }
        ]
      }
    ];
  },
  async redirects() {
    return [
      {
        source: "/",
        destination: basePath,
        permanent: false,
        basePath: false
      }
    ];
  }
};

export default nextConfig;

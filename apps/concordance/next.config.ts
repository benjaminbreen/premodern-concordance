import type { NextConfig } from "next";

const standaloneDeployment = process.env.NEXT_PUBLIC_CONCORDANCE_STANDALONE === "1";
const basePath = standaloneDeployment ? "" : "/apps/concordance";

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
    if (standaloneDeployment) return [];

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

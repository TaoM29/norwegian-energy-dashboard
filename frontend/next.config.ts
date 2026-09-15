import type { NextConfig } from "next";
const config: NextConfig = {
  distDir: process.env.ENERGY_E2E === "1" ? ".next-e2e" : ".next",
  async rewrites() {
    const api = process.env.ENERGY_API_URL || "http://127.0.0.1:8000";
    return [
      {
        source: "/chart-trial/geography",
        destination: `${api}/api/regional/geography`,
      },
      {
        source: "/api/:path*",
        destination: `${api}/api/:path*`,
      },
    ];
  },
};
export default config;

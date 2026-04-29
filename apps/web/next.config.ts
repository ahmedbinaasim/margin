import type { NextConfig } from "next";

const config: NextConfig = {
  output: "export",
  images: { unoptimized: true },
  trailingSlash: true,
  // The dashboard at /app is fully client-rendered; we still pre-render shells.
  experimental: {},
};

export default config;

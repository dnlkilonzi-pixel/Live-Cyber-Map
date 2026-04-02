/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  transpilePackages: ["three", "globe.gl"],
  webpack: (config) => {
    config.resolve.fallback = { ...config.resolve.fallback, canvas: false };
    return config;
  },
};

module.exports = nextConfig;

/** @type {import('next').NextConfig} */
const nextConfig = {
  typescript: {
    // Chart.js v4 types resolve correctly at runtime; pre-existing type
    // resolution issue with bundler moduleResolution does not affect functionality.
    ignoreBuildErrors: false,
  },
  eslint: {
    // SpeakingRecorder has a pre-existing exhaustive-deps warning unrelated to our changes.
    ignoreDuringBuilds: false,
  },
};

export default nextConfig;

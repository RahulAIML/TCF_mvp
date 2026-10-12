/** @type {import('next').NextConfig} */
const nextConfig = {
  typescript: {
    ignoreBuildErrors: false,
  },
  eslint: {
    ignoreDuringBuilds: false,
  },
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: [
          // Suppress "unload is not allowed" Permissions-Policy warnings from Chrome
          { key: "Permissions-Policy", value: "unload=()" },
        ],
      },
    ];
  },
  async rewrites() {
    const apiBase = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    return [
      // Proxy /api/* → backend (covers routes like /api/tcf/transcribe-audio)
      {
        source: "/api/:path*",
        destination: `${apiBase}/api/:path*`,
      },
      // Proxy /audio/* → backend static audio files (avoids browser CORS on audio)
      {
        source: "/audio/:path*",
        destination: `${apiBase}/audio/:path*`,
      },
      // Proxy bare backend routes (no /api prefix) that the api.ts service uses
      // e.g. /signup, /login, /tcf/*, /learn/*, /ai/chat, etc.
      {
        source: "/:path((?!_next|favicon|api|audio).*)",
        destination: `${apiBase}/:path*`,
      },
    ];
  },
};

export default nextConfig;

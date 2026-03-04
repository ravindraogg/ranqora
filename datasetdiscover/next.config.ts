import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Standalone output for Docker / self-hosted deployments
  output: "standalone",

  // Security headers for production
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "X-XSS-Protection", value: "1; mode=block" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          {
            key: "Permissions-Policy",
            value: "camera=(), microphone=(), geolocation=()",
          },
          {
            key: "Content-Security-Policy",
            value: "default-src 'self'; script-src 'self' 'unsafe-eval' 'unsafe-inline' https://va.vercel-scripts.com; style-src 'self' 'unsafe-inline'; img-src 'self' blob: data: https://huggingface.co https://*.huggingface.co https://cdn-uploads.huggingface.co https://kaggle.com https://*.kaggle.com https://images.unsplash.com; font-src 'self' data:; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'; upgrade-insecure-requests; connect-src 'self' http://127.0.0.1:8000 https://vitals.vercel-insights.com;",
          }
        ],
      },
    ];
  },

  // Rewrite /api/* calls to the backend in production
  // Override via NEXT_PUBLIC_API_URL env var at runtime
  async rewrites() {
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";
    return [
      {
        source: "/api/:path*",
        destination: `${apiUrl}/api/:path*`,
      },
    ];
  },

  // Allow images from HuggingFace and other dataset sources
  images: {
    remotePatterns: [
      { protocol: "https", hostname: "huggingface.co" },
      { protocol: "https", hostname: "*.huggingface.co" },
      { protocol: "https", hostname: "cdn-uploads.huggingface.co" },
      { protocol: "https", hostname: "kaggle.com" },
      { protocol: "https", hostname: "*.kaggle.com" },
      { protocol: "https", hostname: "images.unsplash.com" },
    ],
  },
};

export default nextConfig;

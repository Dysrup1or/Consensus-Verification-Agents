/** @type {import('next').NextConfig} */
const nextConfig = {
  // Intentionally minimal; configure API endpoints via NEXT_PUBLIC_API_URL / NEXT_PUBLIC_WS_URL
  output: 'export',
  images: {
    unoptimized: true,
  },
};

module.exports = nextConfig;

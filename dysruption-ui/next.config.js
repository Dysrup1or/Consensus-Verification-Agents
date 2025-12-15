/** @type {import('next').NextConfig} */
const nextConfig = {
  // Intentionally minimal; this app uses NextAuth + server routes (/api/*),
  // so it must run in server mode (do not use `output: 'export'`).
  images: {
    unoptimized: true,
  },
};

module.exports = nextConfig;

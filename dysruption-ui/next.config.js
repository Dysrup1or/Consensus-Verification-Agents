/** @type {import('next').NextConfig} */
const nextConfig = {
  env: {
    NEXT_PUBLIC_USE_MOCK: process.env.USE_MOCK,
  },
};

module.exports = nextConfig;

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  compiler: {
    styledComponents: true,
  },
  // Enable standalone output for Docker (minimal production image)
  output: process.env.DOCKER_BUILD === '1' ? 'standalone' : undefined,
};

module.exports = nextConfig;

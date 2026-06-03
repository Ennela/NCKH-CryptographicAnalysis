/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  /* Allow proxying to FastAPI backend for production */
  async rewrites() {
    return [
      {
        source: '/api/v1/:path*',
        destination: 'http://inference:8000/api/v1/:path*' // Proxy to backend
      }
    ]
  }
}

module.exports = nextConfig

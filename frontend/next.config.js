/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  /* The old Symbols page was merged into "Dữ liệu & Phân tích". */
  async redirects() {
    return [{ source: '/symbols', destination: '/analysis', permanent: false }]
  },
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

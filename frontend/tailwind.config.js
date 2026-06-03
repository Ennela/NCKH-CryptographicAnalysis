/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        darkBg: "#090d16",
        darkCard: "#121824",
        darkBorder: "#1e293b",
        glowIndigo: "#6366f1",
        glowEmerald: "#10b981",
        glowRose: "#f43f5e"
      },
      fontFamily: {
        sans: ["Inter", "sans-serif"],
      }
    },
  },
  plugins: [],
}

/** @type {import('tailwindcss').Config} */
// Palette taken from the team's HTML/CSS mockup (branch `frontend-hieu`,
// "HTML & CSS demo/index.css"): slate page, slate-800 panels, slate-600
// borders, blue accent, amber dashed forecast line.
module.exports = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        page: "#0F172A",
        panel: "#1E293B",
        inset: "#172033",
        line: "#475569",
        muted: "#C3C2C2",
        accent: "#2563EB",
        accentHover: "#1E40AF",
        accentSoft: "#3B82F6",
        forecast: "#F59E0B",
        up: "#10B981",
        down: "#F43F5E",
      },
      fontFamily: {
        sans: ["Inter", "Arial", "sans-serif"],
      },
    },
  },
  plugins: [],
};

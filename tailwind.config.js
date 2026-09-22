/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./templates/admin/**/*.html",
    "./templates/**/*.html",
    "./static/admin_premium/**/*.js",
    "./static/js/**/*.js",
  ],
  theme: {
    extend: {
      colors: {
        // Ratshie brand palette (gold accent, warm neutrals)
        brand: {
          50: "#fff9eb",
          100: "#fff0c9",
          200: "#ffdf8e",
          300: "#ffc94d",
          400: "#ffb41f",
          500: "#f0a000",
          600: "#d19000",
          700: "#a96f00",
          800: "#8a5900",
          900: "#6f4900",
        },
        ink: {
          50: "#f8fafc",
          100: "#f1f5f9",
          200: "#e2e8f0",
          300: "#cbd5e1",
          400: "#94a3b8",
          500: "#64748b",
          600: "#475569",
          700: "#334155",
          800: "#1e293b",
          900: "#0f172a",
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "-apple-system", "Segoe UI", "Roboto", "sans-serif"],
        display: ["Sora", "Inter", "system-ui", "sans-serif"],
      },
      boxShadow: {
        soft: "0 1px 2px 0 rgba(16,24,40,0.05), 0 1px 3px 0 rgba(16,24,40,0.08)",
        card: "0 1px 3px 0 rgba(16,24,40,0.06), 0 1px 2px -1px rgba(16,24,40,0.06)",
        pop: "0 10px 40px -2px rgba(16,24,40,0.15)",
      },
      borderRadius: {
        xl: "0.9rem",
        "2xl": "1.25rem",
      },
    },
  },
  plugins: [],
};

/** ArenaOS design system — strict tokens from the Grok/ChatGPT/Gemini reference set. */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "#FFFFFF",
        surface: "#F8F9FA",
        surface2: "#F5F5F7",
        ink: { DEFAULT: "#1A1A1A", dim: "#6B7280" },
        accent: { DEFAULT: "#007AFF", deep: "#2563EB" },
        line: "#E5E7EB",
        success: "#22C55E",
      },
      fontFamily: { sans: ["system-ui", "-apple-system", "BlinkMacSystemFont", "SF Pro Display", "Inter", "sans-serif"] },
      boxShadow: {
        soft: "0 1px 3px rgba(0,0,0,0.08), 0 4px 12px rgba(0,0,0,0.05)",
        lift: "0 8px 30px rgba(0,0,0,0.12)",
      },
      borderRadius: { card: "18px" },
    },
  },
  plugins: [],
};

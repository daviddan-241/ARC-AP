/** ArenaOS design system — strict tokens from the Grok/ChatGPT/Gemini reference set. */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // ARC — dark navy + magenta->violet->blue circuit gradient (from the
        // ARC wordmark: real colors sampled, not guessed).
        bg: "#0A0D24",
        surface: "#12152E",
        surface2: "#1A1E3D",
        ink: { DEFAULT: "#F3F4FA", dim: "#9298C0" },
        accent: { DEFAULT: "#9B4DFF", deep: "#6C2BD9", cyan: "#4EC1FF", magenta: "#D946C8" },
        line: "#262A4E",
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

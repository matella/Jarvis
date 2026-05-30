/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        void: "#04060a",
        deep: "#070b12",
        panel: "rgba(18, 26, 36, 0.55)",
        edge: "rgba(96, 224, 213, 0.16)",
        teal: { DEFAULT: "#3de0d5", dim: "#1c8a83", glow: "#5af2e8" },
        blue: { DEFAULT: "#4d8dff" },
        amber: { DEFAULT: "#ffb454" },
        steel: { DEFAULT: "#7d93a3" },
        ink: { DEFAULT: "#c8d6de", dim: "#5d7280", faint: "#33454f" },
      },
      fontFamily: {
        display: ['"Chakra Petch"', "monospace"],
        mono: ['"IBM Plex Mono"', "ui-monospace", "monospace"],
      },
      boxShadow: {
        glow: "0 0 24px rgba(61, 224, 213, 0.25)",
        panel: "inset 0 1px 0 rgba(255,255,255,0.03), 0 18px 50px -20px rgba(0,0,0,0.8)",
      },
      keyframes: {
        rise: {
          "0%": { opacity: "0", transform: "translateY(10px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
      },
      animation: { rise: "rise 0.6s cubic-bezier(0.2,0.8,0.2,1) both" },
    },
  },
  plugins: [],
};

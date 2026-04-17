import type { Config } from "tailwindcss";

// Cyberpunk operator dashboard tokens. Mirrors the HTML mockups so designs
// translate 1:1: cyan primary, amber secondary, lime tertiary, near-black
// surfaces, tight radii, monoscape-y feel.
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        // Surfaces — graduated darks, slight cyan tint to match the mockups.
        bg: {
          base: "#0a0f13",
          surface: "#0f1620",
          raised: "#141d29",
          overlay: "#1b2735",
        },
        // Borders — subtle cyan-grey lines used between panels and cards.
        border: {
          DEFAULT: "rgba(129, 236, 255, 0.12)",
          strong: "rgba(129, 236, 255, 0.24)",
        },
        // Text scale.
        ink: {
          DEFAULT: "#e6f1ff",
          dim: "#9aa9bd",
          mute: "#5a6878",
        },
        // Brand / status colors from the mockups.
        primary: {
          DEFAULT: "#81ecff", // cyan
          glow: "rgba(129, 236, 255, 0.35)",
          dark: "#0a3a45",
        },
        secondary: {
          DEFAULT: "#ffbf00", // amber
          glow: "rgba(255, 191, 0, 0.30)",
        },
        tertiary: {
          DEFAULT: "#b8ffbb", // lime
          glow: "rgba(184, 255, 187, 0.28)",
        },
        danger: {
          DEFAULT: "#ff6b6b",
          glow: "rgba(255, 107, 107, 0.28)",
        },
      },
      fontFamily: {
        // Display = Space Grotesk for headings/labels, body = Inter, mono =
        // JetBrains Mono for log lines / code-like data.
        display: ["'Space Grotesk'", "system-ui", "sans-serif"],
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["'JetBrains Mono'", "ui-monospace", "monospace"],
      },
      borderRadius: {
        DEFAULT: "0.125rem",
        md: "0.1875rem",
        lg: "0.25rem",
        xl: "0.375rem",
      },
      boxShadow: {
        glow: "0 0 18px rgba(129, 236, 255, 0.18)",
        "glow-strong": "0 0 28px rgba(129, 236, 255, 0.45)",
      },
      keyframes: {
        pulseDot: {
          "0%, 100%": { opacity: "1", transform: "scale(1)" },
          "50%": { opacity: "0.55", transform: "scale(1.2)" },
        },
        scan: {
          "0%": { transform: "translateY(-100%)" },
          "100%": { transform: "translateY(100%)" },
        },
      },
      animation: {
        pulseDot: "pulseDot 1.4s ease-in-out infinite",
        scan: "scan 2.6s linear infinite",
      },
    },
  },
  plugins: [],
} satisfies Config;

import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        // Background surfaces — `bg-bg-base`, `bg-bg-surface`, …
        bg: {
          base: "rgb(var(--bg-base) / <alpha-value>)",
          surface: "rgb(var(--bg-surface) / <alpha-value>)",
          raised: "rgb(var(--bg-raised) / <alpha-value>)",
          overlay: "rgb(var(--bg-overlay) / <alpha-value>)",
          lowest: "rgb(var(--bg-lowest) / <alpha-value>)",
        },

        // Ink (text) ramp — `text-ink`, `text-ink-dim`, `text-ink-mute`.
        ink: {
          DEFAULT: "rgb(var(--ink) / <alpha-value>)",
          dim: "rgb(var(--ink-dim) / <alpha-value>)",
          mute: "rgb(var(--ink-mute) / <alpha-value>)",
        },

        border: {
          DEFAULT: "rgb(var(--border) / <alpha-value>)",
        },

        primary: {
          DEFAULT: "rgb(var(--primary) / <alpha-value>)",
          container: "rgb(var(--primary-container) / <alpha-value>)",
        },
        secondary: {
          DEFAULT: "rgb(var(--secondary) / <alpha-value>)",
        },
        tertiary: {
          DEFAULT: "rgb(var(--tertiary) / <alpha-value>)",
        },
        danger: {
          DEFAULT: "rgb(var(--danger) / <alpha-value>)",
        },
      },
      fontFamily: {
        display: ["'Manrope'", "system-ui", "sans-serif"],
        headline: ["'EB Garamond'", "serif"],
        body: ["Manrope", "system-ui", "sans-serif"],
        sans: ["Manrope", "system-ui", "sans-serif"],
        mono: [
          "'JetBrains Mono'",
          "ui-monospace",
          "SFMono-Regular",
          "Menlo",
          "monospace",
        ],
      },
      borderRadius: {
        DEFAULT: "0.25rem",
        md: "0.375rem",
        lg: "0.5rem",
        xl: "0.75rem",
        "2xl": "1rem",
      },
      boxShadow: {
        sahara: "0 2px 16px rgba(58, 48, 42, 0.04)",
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
        pulseRing: {
          "0%": { transform: "scale(1)", opacity: "0.4" },
          "100%": { transform: "scale(3)", opacity: "0" },
        },
      },
      animation: {
        pulseDot: "pulseDot 1.4s ease-in-out infinite",
        scan: "scan 2.6s linear infinite",
        pulseRing: "pulseRing 2s infinite ease-in-out",
      },
    },
  },
  plugins: [],
} satisfies Config;

import typography from "@tailwindcss/typography";
import type { Config } from "tailwindcss";

import { v2Tokens } from "./components/ui/v2/tailwind.tokens";

const config: Config = {
  darkMode: "class",
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    container: {
      center: true,
      padding: "2rem",
      screens: {
        "2xl": "1400px",
      },
    },
    extend: {
      colors: {
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
        },
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
        // v2 additive colors — brand, semantic states, surfaces.
        // No v1 key is overwritten; v2 components opt-in by importing
        // from `@/components/ui/v2`. See components/ui/v2/README.md.
        ...v2Tokens.colors,
      },
      boxShadow: v2Tokens.boxShadow,
      transitionDuration: v2Tokens.transitionDuration,
      transitionTimingFunction: v2Tokens.transitionTimingFunction,
      ringColor: v2Tokens.ringColor,
      ringOffsetColor: v2Tokens.ringOffsetColor,
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
    },
  },
  // `prose` styles the Markdown that generated content renders through
  // react-markdown (generate-result, content-detail-dialog).
  plugins: [typography],
};

export default config;

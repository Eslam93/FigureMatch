// SPDX-FileCopyrightText: 2026 Eslam Hamed
//
// SPDX-License-Identifier: MIT

/**
 * Tailwind config fragment for v2 tokens.
 *
 * Usage: merge into your existing `tailwind.config.ts`:
 *
 *   import { v2Tokens } from "@/components/ui/v2/tailwind.tokens";
 *
 *   export default {
 *     ...config,
 *     theme: {
 *       ...config.theme,
 *       extend: {
 *         ...config.theme.extend,
 *         ...v2Tokens,
 *       },
 *     },
 *   } satisfies Config;
 *
 * Or copy the object literal inline. Either way these extend Tailwind's
 * default scales — they do not replace any v1 colors / radii.
 */

export const v2Tokens = {
  colors: {
    brand: {
      DEFAULT: "hsl(var(--brand))",
      foreground: "hsl(var(--brand-foreground))",
      subtle: "hsl(var(--brand-subtle))",
      "subtle-foreground": "hsl(var(--brand-subtle-foreground))",
    },
    success: {
      DEFAULT: "hsl(var(--success))",
      foreground: "hsl(var(--success-foreground))",
      subtle: "hsl(var(--success-subtle))",
      "subtle-foreground": "hsl(var(--success-subtle-foreground))",
    },
    warning: {
      DEFAULT: "hsl(var(--warning))",
      foreground: "hsl(var(--warning-foreground))",
      subtle: "hsl(var(--warning-subtle))",
      "subtle-foreground": "hsl(var(--warning-subtle-foreground))",
    },
    info: {
      DEFAULT: "hsl(var(--info))",
      foreground: "hsl(var(--info-foreground))",
      subtle: "hsl(var(--info-subtle))",
      "subtle-foreground": "hsl(var(--info-subtle-foreground))",
    },
    surface: {
      raised: "hsl(var(--surface-raised))",
      sunken: "hsl(var(--surface-sunken))",
      overlay: "hsl(var(--surface-overlay))",
    },
  },
  boxShadow: {
    "elev-sm": "var(--shadow-sm)",
    "elev-md": "var(--shadow-md)",
    "elev-lg": "var(--shadow-lg)",
  },
  transitionDuration: {
    fast: "var(--duration-fast)",
    base: "var(--duration-base)",
    slow: "var(--duration-slow)",
  },
  transitionTimingFunction: {
    "ease-out-soft": "var(--ease-out)",
    "ease-in-out-soft": "var(--ease-in-out)",
  },
  ringColor: {
    focus: "hsl(var(--focus-ring))",
  },
  ringOffsetColor: {
    focus: "hsl(var(--focus-ring-offset))",
  },
} as const;

// SPDX-FileCopyrightText: 2026 Eslam Hamed
//
// SPDX-License-Identifier: MIT

import { cva, type VariantProps } from "class-variance-authority";
import * as React from "react";

import { cn } from "@/lib/utils";

/**
 * v2 Badge — for status pills (e.g. the "fallback" tag in content-card.tsx,
 * which currently inlines amber Tailwind classes).
 */

const badgeVariants = cva(
  "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium",
  {
    variants: {
      variant: {
        neutral: "border-border bg-secondary text-secondary-foreground",
        brand: "border-brand/30 bg-brand-subtle text-brand-subtle-foreground",
        success: "border-success/30 bg-success-subtle text-success-subtle-foreground",
        warning: "border-warning/40 bg-warning-subtle text-warning-subtle-foreground",
        info: "border-info/30 bg-info-subtle text-info-subtle-foreground",
        destructive: "border-destructive/40 bg-destructive/10 text-destructive",
        outline: "border-border bg-transparent text-foreground",
      },
    },
    defaultVariants: { variant: "neutral" },
  },
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>, VariantProps<typeof badgeVariants> {}

export function Badge({ className, variant, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />;
}

export { badgeVariants };

// SPDX-FileCopyrightText: 2026 Eslam Hamed
//
// SPDX-License-Identifier: MIT

import { Loader2 } from "lucide-react";
import * as React from "react";

import { cn } from "@/lib/utils";

/**
 * v2 Spinner. Wraps lucide's animated Loader2 with a size scale so
 * "loading…" affordances stay consistent everywhere.
 */
export function Spinner({
  size = "md",
  className,
  label = "Loading",
}: {
  size?: "sm" | "md" | "lg";
  className?: string;
  /** Accessible label. Pass empty string if the surrounding context provides one. */
  label?: string;
}) {
  const sizeClass = size === "sm" ? "h-3 w-3" : size === "lg" ? "h-6 w-6" : "h-4 w-4";
  return (
    <span
      role="status"
      aria-live="polite"
      aria-label={label || undefined}
      className={cn("inline-flex", className)}
    >
      <Loader2 className={cn(sizeClass, "animate-spin text-muted-foreground")} aria-hidden />
      {label ? <span className="sr-only">{label}</span> : null}
    </span>
  );
}

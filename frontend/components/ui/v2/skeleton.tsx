// SPDX-FileCopyrightText: 2026 Eslam Hamed
//
// SPDX-License-Identifier: MIT

import * as React from "react";

import { cn } from "@/lib/utils";

/**
 * v2 Skeleton — placeholder shimmer for loading content.
 *
 * Replaces the "Loading…" text rendered by content-list / content-detail
 * dialog while data is in flight. Pair with a layout that matches the
 * post-load skeleton so the page doesn't jump on success.
 */
export function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div aria-hidden className={cn("animate-pulse rounded-md bg-muted", className)} {...props} />
  );
}

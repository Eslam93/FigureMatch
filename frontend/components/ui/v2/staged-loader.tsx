// SPDX-FileCopyrightText: 2026 Eslam Hamed
//
// SPDX-License-Identifier: MIT

"use client";

import * as React from "react";

import { cn } from "@/lib/utils";

/**
 * v2 StagedLoader — promoted out of components/features so any flow can use it.
 *
 * Generalised: the v1 version had "Analyzing topic… / Drafting… / Polishing…"
 * hard-coded for the generate flow. v2 accepts a `stages` prop, defaults to
 * the original strings for backwards compat, and exposes the interval.
 */

const DEFAULT_STAGES: ReadonlyArray<string> = ["Analyzing topic…", "Drafting…", "Polishing…"];

export interface StagedLoaderProps {
  active: boolean;
  stages?: ReadonlyArray<string>;
  /** Milliseconds between stages. Defaults to 1500. */
  intervalMs?: number;
  className?: string;
}

export function StagedLoader({
  active,
  stages = DEFAULT_STAGES,
  intervalMs = 1500,
  className,
}: StagedLoaderProps) {
  const [stageIndex, setStageIndex] = React.useState(0);

  React.useEffect(() => {
    if (!active) {
      setStageIndex(0);
      return;
    }
    const handle = window.setInterval(() => {
      setStageIndex((prev) => (prev + 1) % stages.length);
    }, intervalMs);
    return () => window.clearInterval(handle);
  }, [active, stages.length, intervalMs]);

  if (!active) return null;

  return (
    <div
      className={cn(
        "flex items-center gap-3 rounded-md border bg-card p-4 text-sm text-muted-foreground",
        className,
      )}
      role="status"
      aria-live="polite"
    >
      <span className="h-2 w-2 animate-pulse rounded-full bg-brand" aria-hidden />
      <span data-testid="staged-loader-label">{stages[stageIndex]}</span>
    </div>
  );
}

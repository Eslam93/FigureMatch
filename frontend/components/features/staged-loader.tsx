// SPDX-FileCopyrightText: 2026 Eslam Hamed
//
// SPDX-License-Identifier: MIT

"use client";

import { useEffect, useState } from "react";

/**
 * Three-phase loading indicator for the generate flow.
 *
 * Why staged labels instead of a spinner: the brief calls out staged
 * loading explicitly (§7.0). For a ~3-8s wait, a static spinner reads
 * as broken; a cycling label communicates that something is happening
 * even though no SSE stream is available (content generation is
 * intentionally non-streaming).
 */

const STAGES: ReadonlyArray<string> = ["Analyzing topic…", "Drafting…", "Polishing…"];

const STAGE_INTERVAL_MS = 1500;

export function StagedLoader({ active }: { active: boolean }) {
  const [stageIndex, setStageIndex] = useState(0);

  useEffect(() => {
    if (!active) {
      setStageIndex(0);
      return;
    }
    const handle = window.setInterval(() => {
      setStageIndex((prev) => (prev + 1) % STAGES.length);
    }, STAGE_INTERVAL_MS);
    return () => window.clearInterval(handle);
  }, [active]);

  if (!active) return null;

  return (
    <div
      className="flex items-center gap-3 rounded-md border bg-card p-4 text-sm text-muted-foreground"
      role="status"
      aria-live="polite"
    >
      <span className="h-2 w-2 animate-pulse rounded-full bg-primary" aria-hidden />
      <span data-testid="staged-loader-label">{STAGES[stageIndex]}</span>
    </div>
  );
}

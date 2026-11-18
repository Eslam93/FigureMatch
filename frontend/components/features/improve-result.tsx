// SPDX-FileCopyrightText: 2026 Eslam Hamed
//
// SPDX-License-Identifier: MIT

"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";

import type { ImprovementResponse } from "@/lib/improver/hooks";

/**
 * Side-by-side render of the original + improved text plus the
 * explanation bullets and changes_summary block.
 *
 * The two-pane layout is the easiest readable diff for marketing
 * copy — a token-level diff library would surface every word change
 * but obscures the overall shape. If demand grows, swap in a real
 * diff lib later (e.g., `diff`); for now: two panes.
 */
export function ImproveResult({ data }: { data: ImprovementResponse }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(data.improved_text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard refused — text still on-screen */
    }
  };

  const summary = data.changes_summary;
  const wordsDelta = data.improved_word_count - data.original_word_count;

  return (
    <article
      className="space-y-6 rounded-lg border bg-card p-6"
      aria-live="polite"
      data-testid="improve-result"
    >
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div className="text-xs text-muted-foreground">
          <span className="font-mono">{data.model_id}</span>
          {" · "}
          <span>{data.input_tokens + data.output_tokens} tokens</span>
          {" · "}
          <span>
            {data.original_word_count} → {data.improved_word_count} words (
            {wordsDelta >= 0 ? "+" : ""}
            {wordsDelta})
          </span>
        </div>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={handleCopy}
          data-testid="improve-result-copy"
        >
          {copied ? "Copied" : "Copy improved"}
        </Button>
      </header>

      <div className="grid gap-4 lg:grid-cols-2">
        <section>
          <h3 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
            Original
          </h3>
          <pre
            className="mt-2 overflow-auto whitespace-pre-wrap rounded-md border bg-background p-3 text-sm"
            data-testid="improve-result-original"
          >
            {data.original_text}
          </pre>
        </section>
        <section>
          <h3 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
            Improved
          </h3>
          <pre
            className="mt-2 overflow-auto whitespace-pre-wrap rounded-md border bg-background p-3 text-sm"
            data-testid="improve-result-improved"
          >
            {data.improved_text}
          </pre>
        </section>
      </div>

      <section>
        <h3 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          What changed
        </h3>
        <ul
          className="mt-2 list-disc space-y-1 pl-5 text-sm"
          data-testid="improve-result-explanation"
        >
          {data.explanation.map((line, i) => (
            <li key={i}>{line}</li>
          ))}
        </ul>
      </section>

      <section className="grid gap-3 rounded-md border bg-background p-3 text-sm sm:grid-cols-2">
        <div>
          <p className="text-xs uppercase tracking-wide text-muted-foreground">Tone shift</p>
          <p className="mt-1">{summary.tone_shift || "—"}</p>
        </div>
        <div>
          <p className="text-xs uppercase tracking-wide text-muted-foreground">Length change</p>
          <p className="mt-1">{summary.length_change_pct.toFixed(1)}%</p>
        </div>
        <div>
          <p className="text-xs uppercase tracking-wide text-muted-foreground">Key additions</p>
          <p className="mt-1">{summary.key_additions.join(", ") || "—"}</p>
        </div>
        <div>
          <p className="text-xs uppercase tracking-wide text-muted-foreground">Key removals</p>
          <p className="mt-1">{summary.key_removals.join(", ") || "—"}</p>
        </div>
      </section>
    </article>
  );
}

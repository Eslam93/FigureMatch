"use client";

import { useState } from "react";
import ReactMarkdown from "react-markdown";

import { ImagePanel } from "@/components/features/image-panel";
import { Button } from "@/components/ui/button";
import { Alert } from "@/components/ui/v2";

import type { GenerateResponse } from "@/lib/content/hooks";

/**
 * Render a successful generate response.
 *
 * The body is always `rendered_text` (markdown for blog posts). When
 * `result_parse_status` is "failed" we show a small banner so the user
 * knows the LLM struggled, but the demo still flows — `rendered_text`
 * holds the raw model output verbatim in that case, which is usable.
 */
export function GenerateResult({ data }: { data: GenerateResponse }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(data.rendered_text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard refused (likely insecure context) — leave the
      // button alone; the markdown is still on-screen for manual copy.
    }
  };

  const isDegraded = data.result_parse_status === "failed";

  return (
    <article className="space-y-4 rounded-lg border bg-card p-6" aria-live="polite">
      <header className="flex items-center justify-between gap-4">
        <div className="text-xs text-muted-foreground">
          <span data-testid="generate-result-model">{data.usage.model_id}</span>
          {" · "}
          <span data-testid="generate-result-tokens">
            {data.usage.input_tokens + data.usage.output_tokens} tokens
          </span>
          {" · "}
          <span>{data.word_count} words</span>
        </div>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={handleCopy}
          data-testid="generate-result-copy"
        >
          {copied ? "Copied" : "Copy"}
        </Button>
      </header>

      {isDegraded ? (
        <Alert variant="warning" title="Generated in fallback mode">
          Formatting may be inconsistent — the raw model output is shown below.
        </Alert>
      ) : null}

      <div
        className="prose prose-sm max-w-none dark:prose-invert"
        data-testid="generate-result-body"
      >
        {isDegraded ? (
          <pre className="overflow-auto whitespace-pre-wrap text-sm">{data.rendered_text}</pre>
        ) : (
          <ReactMarkdown>{data.rendered_text}</ReactMarkdown>
        )}
      </div>

      <ImagePanel contentId={data.content_id} disabled={isDegraded} />
    </article>
  );
}

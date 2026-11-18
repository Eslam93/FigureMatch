// SPDX-FileCopyrightText: 2026 Eslam Hamed
//
// SPDX-License-Identifier: MIT

"use client";

import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/v2";
import { Label } from "@/components/ui/label";

import {
  IMAGE_STYLES,
  type ImageStyle,
  useImageGenerateMutation,
  useImageListQuery,
} from "@/lib/content/image-hooks";

interface Props {
  contentId: string;
  /** Disables the generate button — e.g. when the upstream content
   *  failed to parse and there's no rendered text to base an image on. */
  disabled?: boolean;
  className?: string;
}

/**
 * Per-content image panel.
 *
 * - Style picker (six values from the brief).
 * - Generate / Regenerate button — first generation enables the
 *   "current" image; subsequent calls produce a new row that
 *   supersedes the previous current.
 * - Thumbnail strip of previous versions when there's more than one.
 */
export function ImagePanel({ contentId, disabled, className }: Props) {
  const [style, setStyle] = useState<ImageStyle>("photorealistic");
  const list = useImageListQuery(contentId);
  const mutation = useImageGenerateMutation();

  const current = list.data?.data.find((image) => image.is_current);
  const previousVersions = (list.data?.data ?? []).filter((image) => !image.is_current);
  const hasAnyImage = (list.data?.data.length ?? 0) > 0;

  const handleGenerate = () => {
    mutation.mutate(
      { contentId, style },
      {
        onError: (err) => toast.error(err.message),
        onSuccess: () => toast.success("Image generated."),
      },
    );
  };

  const isPending = mutation.isPending;

  return (
    <section
      className={"space-y-4 rounded-lg border bg-card p-4 " + (className ?? "")}
      aria-label="Image"
      data-testid="image-panel"
    >
      <header className="flex items-center justify-between gap-3">
        <h3 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          Image
        </h3>
        {current ? (
          <span className="text-xs text-muted-foreground" data-testid="image-panel-model">
            {current.model_id}
          </span>
        ) : null}
      </header>

      <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
        <div className="space-y-1">
          <Label htmlFor="image-style">Style</Label>
          <select
            id="image-style"
            className="h-9 rounded-md border border-input bg-background px-3 text-sm"
            value={style}
            onChange={(e) => setStyle(e.target.value as ImageStyle)}
            disabled={disabled || isPending}
            data-testid="image-style"
          >
            {IMAGE_STYLES.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>
        <Button
          type="button"
          variant="brand"
          onClick={handleGenerate}
          disabled={disabled}
          loading={isPending}
          data-testid="image-generate"
        >
          {hasAnyImage ? "Regenerate" : "Generate image"}
        </Button>
      </div>

      {list.isPending && !mutation.isPending ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : null}

      {current ? (
        <figure className="space-y-2">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={current.cdn_url}
            alt={current.image_prompt}
            className="block aspect-square w-full max-w-md rounded-md border bg-background object-cover"
            data-testid="image-panel-current"
          />
          <figcaption className="text-xs text-muted-foreground">
            {current.style ?? "—"} · {current.width}×{current.height}
          </figcaption>
        </figure>
      ) : !list.isPending ? (
        <p className="text-sm text-muted-foreground" data-testid="image-panel-empty">
          No image yet. Pick a style and hit Generate.
        </p>
      ) : null}

      {previousVersions.length > 0 ? (
        <div className="space-y-2">
          <p className="text-xs uppercase tracking-wide text-muted-foreground">Previous versions</p>
          <div className="flex gap-2 overflow-x-auto" data-testid="image-panel-history">
            {previousVersions.map((image) => (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                key={image.id}
                src={image.cdn_url}
                alt={image.image_prompt}
                className="h-16 w-16 flex-shrink-0 rounded border bg-background object-cover opacity-70 transition hover:opacity-100"
                title={image.style ?? undefined}
              />
            ))}
          </div>
        </div>
      ) : null}
    </section>
  );
}

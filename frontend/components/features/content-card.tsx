// SPDX-FileCopyrightText: 2026 Eslam Hamed
//
// SPDX-License-Identifier: MIT

"use client";

import { Button } from "@/components/ui/button";

import type { ContentListItem } from "@/lib/content/hooks";

const TYPE_LABEL: Record<ContentListItem["content_type"], string> = {
  blog_post: "Blog post",
  linkedin_post: "LinkedIn post",
  email: "Email",
  ad_copy: "Ad copy",
};

interface Props {
  item: ContentListItem;
  onOpen: () => void;
  onDelete: () => void;
  isDeleting: boolean;
}

/**
 * Single row in the dashboard list.
 *
 * Click anywhere except the Delete button to open detail. Delete is
 * disabled while the mutation is in flight so a double-click can't
 * fire two requests.
 */
export function ContentCard({ item, onOpen, onDelete, isDeleting }: Props) {
  const flatPreview = item.preview.replace(/\s+/g, " ").trim();
  const created = new Date(item.created_at).toLocaleString();
  return (
    <article
      role="button"
      tabIndex={0}
      data-testid={`content-card-${item.id}`}
      className="group flex cursor-pointer flex-col gap-3 rounded-lg border bg-card p-4 transition hover:border-primary/60 hover:shadow-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      onClick={onOpen}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onOpen();
        }
      }}
    >
      <header className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs uppercase tracking-wide text-muted-foreground">
            {TYPE_LABEL[item.content_type]}
          </p>
          <h3 className="mt-1 truncate text-base font-semibold" title={item.topic}>
            {item.topic}
          </h3>
        </div>
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={isDeleting}
          onClick={(e) => {
            e.stopPropagation();
            onDelete();
          }}
          data-testid={`content-card-delete-${item.id}`}
          aria-label="Delete this content"
        >
          {isDeleting ? "Deleting…" : "Delete"}
        </Button>
      </header>

      <p
        className="line-clamp-3 text-sm text-muted-foreground"
        data-testid={`content-card-preview-${item.id}`}
      >
        {flatPreview}
      </p>

      <footer className="flex items-center gap-3 text-xs text-muted-foreground">
        <span data-testid={`content-card-words-${item.id}`}>{item.word_count} words</span>
        <span>·</span>
        <span className="font-mono">{item.model_id}</span>
        <span>·</span>
        <time dateTime={item.created_at}>{created}</time>
        {item.result_parse_status === "failed" ? (
          <span className="ml-auto rounded-full border border-amber-500/40 bg-amber-50 px-2 py-0.5 text-amber-900 dark:bg-amber-950/40 dark:text-amber-200">
            fallback
          </span>
        ) : null}
      </footer>
    </article>
  );
}

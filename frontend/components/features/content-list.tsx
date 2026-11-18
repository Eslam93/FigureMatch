// SPDX-FileCopyrightText: 2026 Eslam Hamed
//
// SPDX-License-Identifier: MIT

"use client";

import { useState } from "react";
import { toast } from "sonner";

import { ContentCard } from "@/components/features/content-card";
import { ContentDetailDialog } from "@/components/features/content-detail-dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

import {
  type ContentType,
  useContentListQuery,
  useDeleteContentMutation,
  useRestoreContentMutation,
} from "@/lib/content/hooks";

const FILTER_OPTIONS: ReadonlyArray<{ value: "" | ContentType; label: string }> = [
  { value: "", label: "All types" },
  { value: "blog_post", label: "Blog post" },
  { value: "linkedin_post", label: "LinkedIn post" },
  { value: "email", label: "Email" },
  { value: "ad_copy", label: "Ad copy" },
];

const PAGE_SIZE = 12;

/**
 * Dashboard content list.
 *
 * - Filter by content type (client-controlled query param)
 * - Free-text search over `rendered_text` (server-side GIN FTS)
 * - Click a card to open the detail dialog
 * - Delete pushes a sonner toast with an Undo action that restores the
 *   row before the 24-hour window expires
 */
export function ContentList() {
  const [page, setPage] = useState(1);
  const [contentType, setContentType] = useState<ContentType | "">("");
  const [searchInput, setSearchInput] = useState("");
  const [searchApplied, setSearchApplied] = useState("");
  const [openDetailId, setOpenDetailId] = useState<string | null>(null);

  const list = useContentListQuery({
    page,
    pageSize: PAGE_SIZE,
    contentType: contentType || undefined,
    q: searchApplied || undefined,
  });
  const deleteMutation = useDeleteContentMutation();
  const restoreMutation = useRestoreContentMutation();

  const handleDelete = (id: string) => {
    deleteMutation.mutate(id, {
      onSuccess: () => {
        toast("Content moved to trash.", {
          description: "Restorable for 24 hours.",
          action: {
            label: "Undo",
            onClick: () => {
              restoreMutation.mutate(id, {
                onError: (err) => toast.error(err.message),
                onSuccess: () => toast.success("Content restored."),
              });
            },
          },
        });
      },
      onError: (err) => toast.error(err.message),
    });
  };

  const applySearch = () => {
    setPage(1);
    setSearchApplied(searchInput.trim());
  };

  const pagination = list.data?.meta.pagination;

  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-bold">Your content</h1>
        <p className="text-sm text-muted-foreground">
          Everything you&apos;ve generated, newest first. Filter by type, search the body, or open a
          card for the full text.
        </p>
      </header>

      <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
        <div className="space-y-1">
          <Label htmlFor="filter-type">Type</Label>
          <select
            id="filter-type"
            className="h-9 rounded-md border border-input bg-background px-3 text-sm"
            value={contentType}
            onChange={(e) => {
              setContentType(e.target.value as ContentType | "");
              setPage(1);
            }}
            data-testid="content-list-filter"
          >
            {FILTER_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>

        <div className="flex-1 space-y-1">
          <Label htmlFor="search">Search</Label>
          <Input
            id="search"
            placeholder="Search inside your content…"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                applySearch();
              }
            }}
            data-testid="content-list-search"
          />
        </div>

        <Button
          type="button"
          variant="outline"
          onClick={applySearch}
          data-testid="content-list-search-submit"
        >
          Search
        </Button>
      </div>

      {list.isPending ? (
        <p className="text-sm text-muted-foreground" data-testid="content-list-loading">
          Loading…
        </p>
      ) : list.isError ? (
        <p className="text-sm text-destructive" role="alert">
          {list.error.message}
        </p>
      ) : list.data && list.data.data.length === 0 ? (
        <div
          className="rounded-lg border border-dashed bg-card p-12 text-center"
          data-testid="content-list-empty"
        >
          <p className="text-sm text-muted-foreground">
            Nothing here yet. Head over to the Generate page to draft your first piece.
          </p>
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3" data-testid="content-list-grid">
          {list.data?.data.map((item) => (
            <ContentCard
              key={item.id}
              item={item}
              onOpen={() => setOpenDetailId(item.id)}
              onDelete={() => handleDelete(item.id)}
              isDeleting={deleteMutation.isPending && deleteMutation.variables === item.id}
            />
          ))}
        </div>
      )}

      {pagination && pagination.total_pages > 1 ? (
        <nav
          className="flex items-center justify-between border-t pt-4 text-sm"
          aria-label="Pagination"
          data-testid="content-list-pagination"
        >
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={pagination.page <= 1}
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            data-testid="content-list-prev"
          >
            Previous
          </Button>
          <span className="text-muted-foreground">
            Page {pagination.page} of {pagination.total_pages} · {pagination.total} total
          </span>
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={pagination.page >= pagination.total_pages}
            onClick={() => setPage((p) => p + 1)}
            data-testid="content-list-next"
          >
            Next
          </Button>
        </nav>
      ) : null}

      <ContentDetailDialog contentId={openDetailId} onClose={() => setOpenDetailId(null)} />
    </div>
  );
}

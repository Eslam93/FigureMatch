"use client";

import { useState } from "react";
import ReactMarkdown from "react-markdown";
import { toast } from "sonner";

import { ImagePanel } from "@/components/features/image-panel";
import { Button } from "@/components/ui/button";
import { Modal } from "@/components/ui/modal";
import { Alert } from "@/components/ui/v2";

import { useContentDetailQuery } from "@/lib/content/hooks";

interface Props {
  contentId: string | null;
  onClose: () => void;
}

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

/**
 * Download the piece as Markdown by hitting the export route with the
 * current access token and triggering a browser download from the blob.
 *
 * We bypass the openapi-fetch client deliberately — the response is
 * `text/markdown` with `Content-Disposition: attachment`, not JSON,
 * and openapi-fetch is shaped around typed JSON responses. The token
 * is read lazily so SSR bundles don't drag the Zustand store in.
 */
async function downloadMarkdown(contentId: string): Promise<void> {
  const { useAuthStore } = await import("@/lib/auth-store");
  const token = useAuthStore.getState().accessToken;
  const response = await fetch(`${API_BASE_URL}/content/${contentId}/export?format=md`, {
    method: "GET",
    headers: token ? { authorization: `Bearer ${token}` } : undefined,
    credentials: "include",
  });
  if (!response.ok) {
    throw new Error(`Export failed (${response.status})`);
  }
  // Filename comes back in Content-Disposition; pull it out for the
  // browser download. Falls back to a generic name if the server
  // didn't set the header (shouldn't happen, but defensive).
  const dispositionHeader = response.headers.get("content-disposition") ?? "";
  const filenameMatch = /filename="?([^"]+)"?/i.exec(dispositionHeader);
  const filename = filenameMatch?.[1] ?? "content.md";

  const blob = await response.blob();
  const objectUrl = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = objectUrl;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
  URL.revokeObjectURL(objectUrl);
}

/**
 * Modal that fetches and renders one content piece in full.
 *
 * `contentId === null` means "closed". The query is gated on the id so
 * it doesn't fire while the modal is hidden. Copy reaches into the
 * detail's `rendered_text` so what the user sees is exactly what they
 * paste.
 */
export function ContentDetailDialog({ contentId, onClose }: Props) {
  const open = contentId !== null;
  const detail = useContentDetailQuery(contentId);
  const [copied, setCopied] = useState(false);
  const [downloading, setDownloading] = useState(false);

  const handleCopy = async () => {
    if (!detail.data) return;
    try {
      await navigator.clipboard.writeText(detail.data.rendered_text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard refused — text is still visible */
    }
  };

  const handleDownload = async () => {
    if (!detail.data) return;
    setDownloading(true);
    try {
      await downloadMarkdown(detail.data.id);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Download failed.");
    } finally {
      setDownloading(false);
    }
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={detail.data?.topic ?? "Loading…"}
      data-testid="content-detail-dialog"
    >
      {detail.isPending ? (
        <p className="text-sm text-muted-foreground">Loading content…</p>
      ) : detail.isError ? (
        <p className="text-sm text-destructive" role="alert">
          {detail.error.message}
        </p>
      ) : detail.data ? (
        <div className="space-y-4">
          <header className="flex items-center justify-between gap-4 text-xs text-muted-foreground">
            <div>
              <span className="font-mono">{detail.data.model_id}</span>
              {" · "}
              <span>{detail.data.word_count} words</span>
            </div>
            <div className="flex gap-2">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={handleDownload}
                disabled={downloading}
                data-testid="content-detail-download"
              >
                {downloading ? "Downloading…" : "Download .md"}
              </Button>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={handleCopy}
                data-testid="content-detail-copy"
              >
                {copied ? "Copied" : "Copy"}
              </Button>
            </div>
          </header>

          {detail.data.result_parse_status === "failed" ? (
            <Alert variant="warning" title="Generated in fallback mode">
              Formatting may be inconsistent — the raw model output is shown below.
            </Alert>
          ) : null}

          <div
            className="prose prose-sm max-w-none dark:prose-invert"
            data-testid="content-detail-body"
          >
            {detail.data.result_parse_status === "failed" ? (
              <pre className="overflow-auto whitespace-pre-wrap text-sm">
                {detail.data.rendered_text}
              </pre>
            ) : (
              <ReactMarkdown>{detail.data.rendered_text}</ReactMarkdown>
            )}
          </div>

          <ImagePanel
            contentId={detail.data.id}
            disabled={detail.data.result_parse_status === "failed"}
          />
        </div>
      ) : null}
    </Modal>
  );
}

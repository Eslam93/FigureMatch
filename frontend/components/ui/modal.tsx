// SPDX-FileCopyrightText: 2026 Eslam Hamed
//
// SPDX-License-Identifier: MIT

"use client";

import { useEffect, useRef } from "react";

import { cn } from "@/lib/utils";

interface ModalProps {
  open: boolean;
  onClose: () => void;
  title?: string;
  children: React.ReactNode;
  className?: string;
  "data-testid"?: string;
}

/**
 * Lightweight controlled modal — fixed overlay + escape-to-close +
 * click-backdrop-to-close. Avoids pulling in `@radix-ui/react-dialog`
 * for this slice; the dashboard's detail view doesn't need focus
 * traps or nested-trigger semantics. If a richer dialog is needed
 * later (e.g., a wizard with focus management), upgrade to Radix.
 */
export function Modal({
  open,
  onClose,
  title,
  children,
  className,
  "data-testid": dataTestId,
}: ModalProps) {
  const overlayRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    // Prevent background scroll while open.
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      ref={overlayRef}
      role="dialog"
      aria-modal="true"
      aria-label={title}
      data-testid={dataTestId}
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-background/80 p-4 backdrop-blur-sm"
      onClick={(e) => {
        if (e.target === overlayRef.current) onClose();
      }}
    >
      <div
        className={cn(
          "relative my-12 w-full max-w-3xl rounded-lg border bg-card p-6 shadow-xl",
          className,
        )}
      >
        {title ? (
          <header className="mb-4 flex items-center justify-between gap-4">
            <h2 className="text-lg font-semibold">{title}</h2>
            <button
              type="button"
              onClick={onClose}
              className="rounded-md p-1 text-muted-foreground hover:bg-accent hover:text-foreground"
              aria-label="Close"
              data-testid="modal-close"
            >
              ×
            </button>
          </header>
        ) : null}
        {children}
      </div>
    </div>
  );
}

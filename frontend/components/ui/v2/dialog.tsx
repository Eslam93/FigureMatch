// SPDX-FileCopyrightText: 2026 Eslam Hamed
//
// SPDX-License-Identifier: MIT

"use client";

import * as React from "react";

import { cn } from "@/lib/utils";

import { Button } from "./button";

/**
 * v2 Dialog — drop-in replacement for the v1 Modal with proper focus
 * management.
 *
 * Differences vs v1 Modal:
 *   - Focus trap (Tab/Shift+Tab stays inside the dialog).
 *   - Initial focus lands on the first focusable element inside content;
 *     restores focus to the trigger on close.
 *   - Composable header / body / footer parts that match the rest of v2.
 *   - Still framework-agnostic — no @radix-ui/react-dialog dependency.
 *
 * If your team later wants nested triggers or portal-out-of-iframe support,
 * swap the implementation for Radix Dialog without changing the JSX shape
 * at call sites: the parts (Dialog, DialogHeader, DialogTitle, …) mirror
 * Radix's exported names.
 */

interface DialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Optional initial focus target. Defaults to the first focusable child. */
  initialFocusRef?: React.RefObject<HTMLElement | null>;
  className?: string;
  children: React.ReactNode;
  /** Accessible label when there's no visible <DialogTitle>. */
  "aria-label"?: string;
  "data-testid"?: string;
}

const FOCUSABLE_SELECTOR =
  'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

export function Dialog({
  open,
  onOpenChange,
  initialFocusRef,
  className,
  children,
  "aria-label": ariaLabel,
  "data-testid": dataTestId,
}: DialogProps) {
  const overlayRef = React.useRef<HTMLDivElement | null>(null);
  const contentRef = React.useRef<HTMLDivElement | null>(null);
  const previouslyFocused = React.useRef<HTMLElement | null>(null);

  React.useEffect(() => {
    if (!open) return;

    previouslyFocused.current = document.activeElement as HTMLElement | null;

    const node = contentRef.current;
    const target =
      initialFocusRef?.current ??
      (node?.querySelector(FOCUSABLE_SELECTOR) as HTMLElement | null) ??
      node;
    target?.focus();

    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onOpenChange(false);
        return;
      }
      if (e.key === "Tab" && contentRef.current) {
        const focusables = Array.from(
          contentRef.current.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR),
        ).filter((el) => !el.hasAttribute("data-focus-guard"));
        if (focusables.length === 0) {
          e.preventDefault();
          return;
        }
        const first = focusables[0];
        const last = focusables[focusables.length - 1];
        const active = document.activeElement as HTMLElement | null;
        if (e.shiftKey && active === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && active === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };

    document.addEventListener("keydown", onKey);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prevOverflow;
      previouslyFocused.current?.focus?.();
    };
  }, [open, onOpenChange, initialFocusRef]);

  if (!open) return null;

  return (
    <div
      ref={overlayRef}
      data-testid={dataTestId}
      className={
        "fixed inset-0 z-50 flex items-start justify-center overflow-y-auto " +
        "bg-background/80 p-4 backdrop-blur-sm" +
        "animate-in fade-in duration-base"
      }
      onClick={(e) => {
        if (e.target === overlayRef.current) onOpenChange(false);
      }}
    >
      <div
        ref={contentRef}
        role="dialog"
        aria-modal="true"
        aria-label={ariaLabel}
        tabIndex={-1}
        className={cn(
          "relative my-12 w-full max-w-3xl rounded-lg border bg-card text-card-foreground shadow-elev-lg",
          "animate-in fade-in zoom-in-95 duration-base",
          "focus:outline-none",
          className,
        )}
      >
        {children}
      </div>
    </div>
  );
}

export function DialogHeader({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={cn("flex items-start justify-between gap-4 p-6 pb-2", className)} {...props} />
  );
}

export function DialogTitle({ className, ...props }: React.HTMLAttributes<HTMLHeadingElement>) {
  return <h2 className={cn("text-lg font-semibold", className)} {...props} />;
}

export function DialogDescription({
  className,
  ...props
}: React.HTMLAttributes<HTMLParagraphElement>) {
  return <p className={cn("text-sm text-muted-foreground", className)} {...props} />;
}

export function DialogBody({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("space-y-4 px-6 pb-6", className)} {...props} />;
}

export function DialogFooter({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "flex flex-col-reverse gap-2 border-t bg-surface-sunken/40 p-4 sm:flex-row sm:justify-end",
        className,
      )}
      {...props}
    />
  );
}

export function DialogCloseButton({ onClose }: { onClose: () => void }) {
  return (
    <Button
      type="button"
      variant="ghost"
      size="icon"
      onClick={onClose}
      aria-label="Close"
      data-testid="dialog-close"
    >
      <span aria-hidden className="text-lg leading-none">
        ×
      </span>
    </Button>
  );
}

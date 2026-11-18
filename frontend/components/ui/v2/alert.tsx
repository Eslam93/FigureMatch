// SPDX-FileCopyrightText: 2026 Eslam Hamed
//
// SPDX-License-Identifier: MIT

"use client";

import { cva, type VariantProps } from "class-variance-authority";
import { AlertCircle, AlertTriangle, CheckCircle2, Info, X } from "lucide-react";
import * as React from "react";

import { cn } from "@/lib/utils";

/**
 * v2 Alert / Banner.
 *
 * Collapses TWO repeated patterns across features:
 *
 * (1) Destructive banner — 5 instances of:
 *       "rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive"
 *
 * (2) Warning fallback banner — 3 instances of hard-coded amber Tailwind
 *     colors that don't theme:
 *       "border-amber-500/40 bg-amber-50 text-amber-900 dark:bg-amber-950/40 dark:text-amber-200"
 *
 * v2 routes both through tokens (--destructive, --warning, --success, --info)
 * so dark mode is consistent and a future re-theme touches one file.
 *
 * Usage:
 *   <Alert variant="destructive">Couldn't save brand voice.</Alert>
 *   <Alert variant="warning" title="Fallback rendering">…</Alert>
 *   <Alert variant="success" onDismiss={() => …}>Content restored.</Alert>
 */

const alertVariants = cva("relative flex w-full items-start gap-3 rounded-md border p-3 text-sm", {
  variants: {
    variant: {
      info: "border-info/30 bg-info-subtle text-info-subtle-foreground [&_[data-slot=icon]]:text-info",
      success:
        "border-success/30 bg-success-subtle text-success-subtle-foreground [&_[data-slot=icon]]:text-success",
      warning:
        "border-warning/40 bg-warning-subtle text-warning-subtle-foreground [&_[data-slot=icon]]:text-warning",
      destructive:
        "border-destructive/40 bg-destructive/10 text-destructive [&_[data-slot=icon]]:text-destructive",
    },
  },
  defaultVariants: { variant: "info" },
});

const ICON_BY_VARIANT = {
  info: Info,
  success: CheckCircle2,
  warning: AlertTriangle,
  destructive: AlertCircle,
} as const;

export interface AlertProps
  extends Omit<React.HTMLAttributes<HTMLDivElement>, "title">, VariantProps<typeof alertVariants> {
  title?: React.ReactNode;
  /** Hide the leading icon. */
  hideIcon?: boolean;
  /** Show a dismiss button. Called when clicked. */
  onDismiss?: () => void;
}

const Alert = React.forwardRef<HTMLDivElement, AlertProps>(
  ({ className, variant = "info", title, hideIcon, onDismiss, children, role, ...props }, ref) => {
    const Icon = ICON_BY_VARIANT[variant ?? "info"];
    const resolvedRole =
      role ?? (variant === "destructive" || variant === "warning" ? "alert" : "status");

    return (
      <div
        ref={ref}
        role={resolvedRole}
        className={cn(alertVariants({ variant }), className)}
        {...props}
      >
        {!hideIcon ? (
          <Icon data-slot="icon" className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
        ) : null}
        <div className="min-w-0 flex-1 space-y-1">
          {title ? <p className="font-medium leading-tight">{title}</p> : null}
          {children ? <div className="leading-snug">{children}</div> : null}
        </div>
        {onDismiss ? (
          <button
            type="button"
            onClick={onDismiss}
            className="ml-2 rounded-sm opacity-70 transition-opacity hover:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus"
            aria-label="Dismiss"
          >
            <X className="h-4 w-4" aria-hidden />
          </button>
        ) : null}
      </div>
    );
  },
);
Alert.displayName = "Alert";

export { Alert, alertVariants };

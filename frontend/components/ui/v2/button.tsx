// SPDX-FileCopyrightText: 2023 shadcn
// SPDX-FileCopyrightText: 2026 Eslam Hamed
//
// SPDX-License-Identifier: MIT

"use client";

import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { Loader2 } from "lucide-react";
import * as React from "react";

import { cn } from "@/lib/utils";

/**
 * v2 Button.
 *
 * Improvements over v1:
 *   - `loading` prop: swaps content for a spinner + keeps button width stable
 *     (no more manual "Generating…" / "Deleting…" strings in feature code).
 *   - `brand` variant for primary CTA — uses the new --brand token so the
 *     focus ring lands on a real accent, not near-black.
 *   - `success` variant for non-destructive confirmations.
 *   - Focus ring uses --focus-ring (visible, brand-tinted).
 *   - `leftIcon` / `rightIcon` props remove the boilerplate of icon+text layouts.
 */

const buttonVariants = cva(
  "relative inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md text-sm font-medium " +
    "transition-colors duration-fast ease-out-soft " +
    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus focus-visible:ring-offset-2 focus-visible:ring-offset-focus " +
    "disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        brand: "bg-brand text-brand-foreground hover:bg-brand/90",
        default: "bg-primary text-primary-foreground hover:bg-primary/90",
        secondary: "bg-secondary text-secondary-foreground hover:bg-secondary/80",
        outline: "border border-input bg-background hover:bg-accent hover:text-accent-foreground",
        ghost: "hover:bg-accent hover:text-accent-foreground",
        destructive: "bg-destructive text-destructive-foreground hover:bg-destructive/90",
        success: "bg-success text-success-foreground hover:bg-success/90",
        link: "text-brand underline-offset-4 hover:underline",
      },
      size: {
        sm: "h-9 rounded-md px-3 text-sm",
        default: "h-10 px-4 py-2",
        lg: "h-11 rounded-md px-6 text-base",
        icon: "h-10 w-10",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof buttonVariants> {
  /** Render as the child element (Radix Slot). */
  asChild?: boolean;
  /** Show a spinner and disable the button. Keeps width stable. */
  loading?: boolean;
  /** Optional icon rendered before the label. Ignored when `loading`. */
  leftIcon?: React.ReactNode;
  /** Optional icon rendered after the label. */
  rightIcon?: React.ReactNode;
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  (
    {
      className,
      variant,
      size,
      asChild = false,
      loading = false,
      leftIcon,
      rightIcon,
      disabled,
      children,
      ...props
    },
    ref,
  ) => {
    const Comp = asChild ? Slot : "button";
    const isDisabled = disabled || loading;

    return (
      <Comp
        ref={ref}
        className={cn(buttonVariants({ variant, size, className }))}
        disabled={isDisabled}
        data-loading={loading || undefined}
        aria-busy={loading || undefined}
        {...props}
      >
        {loading ? (
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
        ) : leftIcon ? (
          <span className="inline-flex shrink-0" aria-hidden>
            {leftIcon}
          </span>
        ) : null}
        {children}
        {!loading && rightIcon ? (
          <span className="inline-flex shrink-0" aria-hidden>
            {rightIcon}
          </span>
        ) : null}
      </Comp>
    );
  },
);
Button.displayName = "Button";

export { Button, buttonVariants };

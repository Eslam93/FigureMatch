// SPDX-FileCopyrightText: 2023 shadcn
// SPDX-FileCopyrightText: 2026 Eslam Hamed
//
// SPDX-License-Identifier: MIT

"use client";

import * as LabelPrimitive from "@radix-ui/react-label";
import * as React from "react";

import { cn } from "@/lib/utils";

/**
 * v2 Label.
 *
 * Adds an explicit `required` prop instead of every feature file rendering
 * `<span className="text-destructive">*</span>` by hand.
 */
export interface LabelProps extends React.ComponentPropsWithoutRef<typeof LabelPrimitive.Root> {
  required?: boolean;
  optional?: boolean;
}

const Label = React.forwardRef<React.ElementRef<typeof LabelPrimitive.Root>, LabelProps>(
  ({ className, required, optional, children, ...props }, ref) => (
    <LabelPrimitive.Root
      ref={ref}
      className={cn(
        "inline-flex items-center gap-1 text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70",
        className,
      )}
      {...props}
    >
      {children}
      {required ? (
        <span className="text-destructive" aria-hidden>
          *
        </span>
      ) : null}
      {optional ? (
        <span className="text-xs font-normal text-muted-foreground">(optional)</span>
      ) : null}
    </LabelPrimitive.Root>
  ),
);
Label.displayName = "Label";

export { Label };

// SPDX-FileCopyrightText: 2023 shadcn
// SPDX-FileCopyrightText: 2026 Eslam Hamed
//
// SPDX-License-Identifier: MIT

import * as React from "react";

import { cn } from "@/lib/utils";

/**
 * v2 Input.
 *
 * Adds:
 *   - Visual error state driven by `aria-invalid` (no JS prop drilling needed —
 *     just set `aria-invalid={!!error}` on the input from your form library).
 *   - Branded focus ring via --focus-ring.
 *   - Optional `leadingIcon` / `trailingIcon` slots.
 */

export interface InputProps extends React.ComponentProps<"input"> {
  leadingIcon?: React.ReactNode;
  trailingIcon?: React.ReactNode;
}

const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ className, type, leadingIcon, trailingIcon, ...props }, ref) => {
    const base =
      "flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm " +
      "ring-offset-background transition-colors duration-fast " +
      "file:border-0 file:bg-transparent file:text-sm file:font-medium " +
      "placeholder:text-muted-foreground " +
      "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus focus-visible:ring-offset-2 focus-visible:ring-offset-focus " +
      "disabled:cursor-not-allowed disabled:opacity-50 " +
      "aria-[invalid=true]:border-destructive aria-[invalid=true]:focus-visible:ring-destructive";

    if (!leadingIcon && !trailingIcon) {
      return <input type={type} ref={ref} className={cn(base, className)} {...props} />;
    }

    return (
      <div className="relative">
        {leadingIcon ? (
          <span
            className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground"
            aria-hidden
          >
            {leadingIcon}
          </span>
        ) : null}
        <input
          type={type}
          ref={ref}
          className={cn(base, leadingIcon && "pl-9", trailingIcon && "pr-9", className)}
          {...props}
        />
        {trailingIcon ? (
          <span
            className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground"
            aria-hidden
          >
            {trailingIcon}
          </span>
        ) : null}
      </div>
    );
  },
);
Input.displayName = "Input";

export { Input };

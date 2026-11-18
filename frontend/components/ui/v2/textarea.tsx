// SPDX-FileCopyrightText: 2026 Eslam Hamed
//
// SPDX-License-Identifier: MIT

import * as React from "react";

import { cn } from "@/lib/utils";

/**
 * v2 Textarea — replaces the inline-styled `<textarea>` blocks that
 * appear in brand-voice-form.tsx and improve-form.tsx. Matches Input's
 * focus + invalid styles so forms read consistently.
 */
const Textarea = React.forwardRef<HTMLTextAreaElement, React.ComponentProps<"textarea">>(
  ({ className, ...props }, ref) => {
    return (
      <textarea
        ref={ref}
        className={cn(
          "flex min-h-[120px] w-full rounded-md border border-input bg-background p-3 text-sm " +
            "ring-offset-background transition-colors duration-fast" +
            "placeholder:text-muted-foreground" +
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus focus-visible:ring-offset-2 focus-visible:ring-offset-focus" +
            "disabled:cursor-not-allowed disabled:opacity-50" +
            "aria-[invalid=true]:border-destructive aria-[invalid=true]:focus-visible:ring-destructive",
          className,
        )}
        {...props}
      />
    );
  },
);
Textarea.displayName = "Textarea";

export { Textarea };

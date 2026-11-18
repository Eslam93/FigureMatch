// SPDX-FileCopyrightText: 2026 Eslam Hamed
//
// SPDX-License-Identifier: MIT

import * as React from "react";

import { cn } from "@/lib/utils";

/**
 * v2 Select — native `<select>` styled to match Input/Textarea.
 *
 * Why native (not Radix Select):
 *   - All current uses (filter, brand-voice picker, image style, improve goal)
 *     are simple lists of options — native gives free a11y + mobile UX.
 *   - Keeps the bundle small. Upgrade to a Radix Select primitive later
 *     if/when designs call for grouped options or rich item rendering.
 *
 * Eliminates the duplicated inline string seen 4× in features:
 *   "h-9 ... rounded-md border border-input bg-background px-3 text-sm"
 */
const Select = React.forwardRef<HTMLSelectElement, React.ComponentProps<"select">>(
  ({ className, children, ...props }, ref) => {
    return (
      <select
        ref={ref}
        className={cn(
          "flex h-10 w-full appearance-none rounded-md border border-input bg-background px-3 pr-9 text-sm",
          "ring-offset-background transition-colors duration-fast",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus focus-visible:ring-offset-2 focus-visible:ring-offset-focus",
          "disabled:cursor-not-allowed disabled:opacity-50",
          // Custom chevron via inline SVG background — keeps native open behaviour.
          // Single-quoted outer string so the SVG's double quotes don't need escaping.
          'bg-[image:url("data:image/svg+xml;utf8,%3Csvg%20xmlns%3D%27http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%27%20viewBox%3D%270%200%2020%2020%27%20fill%3D%27none%27%20stroke%3D%27%23737373%27%20stroke-width%3D%271.5%27%3E%3Cpath%20d%3D%27M6%208l4%204%204-4%27%2F%3E%3C%2Fsvg%3E")] bg-[length:1rem] bg-[right_0.6rem_center] bg-no-repeat',
          "aria-[invalid=true]:border-destructive aria-[invalid=true]:focus-visible:ring-destructive",
          className,
        )}
        {...props}
      >
        {children}
      </select>
    );
  },
);
Select.displayName = "Select";

export { Select };

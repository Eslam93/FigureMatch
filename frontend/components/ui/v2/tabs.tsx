// SPDX-FileCopyrightText: 2023 shadcn
// SPDX-FileCopyrightText: 2026 Eslam Hamed
//
// SPDX-License-Identifier: MIT

"use client";

import * as React from "react";

import { cn } from "@/lib/utils";

/**
 * v2 Tabs — replaces the bespoke ContentTypeTabs in generate-form.tsx.
 *
 * Why a small custom primitive (not @radix-ui/react-tabs):
 *   - generate-form's tabs are controlled by a form field, not a tab
 *     panel. Radix Tabs ties content panels to triggers; that's overkill.
 *   - This component focuses on the trigger pattern only — a tablist of
 *     buttons that emit value-change events. Composable with anything.
 *
 * If you later need real panels-with-content, swap in Radix Tabs at the
 * caller — the API surface here intentionally mirrors Radix.
 */

interface TabOption<TValue extends string> {
  value: TValue;
  label: React.ReactNode;
  /** When false the tab is rendered disabled with an optional tooltip. */
  enabled?: boolean;
  tooltip?: string;
}

interface TabsProps<TValue extends string> {
  value: TValue;
  onValueChange: (next: TValue) => void;
  options: ReadonlyArray<TabOption<TValue>>;
  disabled?: boolean;
  className?: string;
  "aria-label"?: string;
  "data-testid"?: string;
}

export function Tabs<TValue extends string>({
  value,
  onValueChange,
  options,
  disabled,
  className,
  "aria-label": ariaLabel,
  "data-testid": dataTestId,
}: TabsProps<TValue>) {
  return (
    <div
      role="tablist"
      aria-label={ariaLabel}
      data-testid={dataTestId}
      className={cn("flex flex-wrap gap-2", className)}
    >
      {options.map((opt) => {
        const isActive = opt.value === value;
        const isEnabled = opt.enabled !== false;
        const isClickable = isEnabled && !disabled;
        return (
          <button
            key={opt.value}
            type="button"
            role="tab"
            aria-selected={isActive}
            aria-disabled={!isEnabled || undefined}
            title={isEnabled ? undefined : opt.tooltip}
            disabled={!isClickable}
            onClick={() => isClickable && onValueChange(opt.value)}
            data-testid={`tab-${opt.value}`}
            className={cn(
              "rounded-md border px-3 py-1.5 text-sm font-medium transition-colors duration-fast",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus focus-visible:ring-offset-2",
              isActive
                ? "border-brand bg-brand text-brand-foreground"
                : "border-border bg-card hover:bg-accent hover:text-accent-foreground",
              !isEnabled && "cursor-not-allowed opacity-50",
            )}
          >
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}

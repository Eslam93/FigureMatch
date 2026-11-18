// SPDX-FileCopyrightText: 2026 Eslam Hamed
//
// SPDX-License-Identifier: MIT

import * as React from "react";

import { cn } from "@/lib/utils";

/**
 * v2 EmptyState — single primitive for the dashed-border "nothing here yet"
 * blocks rendered by content-list and brand-voices-list. Adds room for an
 * icon, a title, a description, and a primary CTA.
 */
export interface EmptyStateProps extends Omit<React.HTMLAttributes<HTMLDivElement>, "title"> {
  icon?: React.ReactNode;
  title?: React.ReactNode;
  description?: React.ReactNode;
  action?: React.ReactNode;
}

export function EmptyState({
  icon,
  title,
  description,
  action,
  className,
  children,
  ...props
}: EmptyStateProps) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-3 rounded-lg border border-dashed bg-card p-12 text-center",
        className,
      )}
      {...props}
    >
      {icon ? <div className="text-muted-foreground">{icon}</div> : null}
      {title ? <h3 className="text-base font-semibold">{title}</h3> : null}
      {description ? <p className="max-w-sm text-sm text-muted-foreground">{description}</p> : null}
      {children}
      {action ? <div className="mt-2">{action}</div> : null}
    </div>
  );
}

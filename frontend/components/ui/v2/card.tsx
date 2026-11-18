// SPDX-FileCopyrightText: 2026 Eslam Hamed
//
// SPDX-License-Identifier: MIT

import * as React from "react";

import { cn } from "@/lib/utils";

/**
 * v2 Card primitive set.
 *
 * Replaces the duplicated `"rounded-lg border bg-card p-4/p-6"` pattern
 * seen 8+ times across content-card, brand-voices-list, generate-result,
 * image-panel, improve-result, etc.
 *
 * Composition mirrors shadcn convention: <Card>, <CardHeader>, <CardTitle>,
 * <CardDescription>, <CardBody>, <CardFooter>.
 *
 * `interactive` adds the hover/focus styles that ContentCard wires up by hand.
 */

interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  /** Applies hover + focus-visible styles. Use when the card is itself a button/link. */
  interactive?: boolean;
  /** Visual elevation. Defaults to "flat" (border only). */
  elevation?: "flat" | "raised" | "floating";
}

const elevationClass: Record<NonNullable<CardProps["elevation"]>, string> = {
  flat: "",
  raised: "shadow-elev-sm",
  floating: "shadow-elev-md",
};

const Card = React.forwardRef<HTMLDivElement, CardProps>(
  ({ className, interactive, elevation = "flat", ...props }, ref) => (
    <div
      ref={ref}
      className={cn(
        "rounded-lg border bg-card text-card-foreground",
        elevationClass[elevation],
        interactive &&
          "cursor-pointer transition-colors duration-fast hover:border-brand/60 hover:shadow-elev-sm " +
            "focus:outline-none focus-visible:ring-2 focus-visible:ring-focus focus-visible:ring-offset-2",
        className,
      )}
      {...props}
    />
  ),
);
Card.displayName = "Card";

const CardHeader = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn("flex flex-col gap-1.5 p-6", className)} {...props} />
  ),
);
CardHeader.displayName = "CardHeader";

const CardTitle = React.forwardRef<HTMLHeadingElement, React.HTMLAttributes<HTMLHeadingElement>>(
  ({ className, ...props }, ref) => (
    <h3
      ref={ref}
      className={cn("text-base font-semibold leading-tight tracking-tight", className)}
      {...props}
    />
  ),
);
CardTitle.displayName = "CardTitle";

const CardDescription = React.forwardRef<
  HTMLParagraphElement,
  React.HTMLAttributes<HTMLParagraphElement>
>(({ className, ...props }, ref) => (
  <p ref={ref} className={cn("text-sm text-muted-foreground", className)} {...props} />
));
CardDescription.displayName = "CardDescription";

const CardBody = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn("p-6 pt-0", className)} {...props} />
  ),
);
CardBody.displayName = "CardBody";

const CardFooter = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn("flex items-center gap-2 p-6 pt-0", className)} {...props} />
  ),
);
CardFooter.displayName = "CardFooter";

export { Card, CardHeader, CardTitle, CardDescription, CardBody, CardFooter };

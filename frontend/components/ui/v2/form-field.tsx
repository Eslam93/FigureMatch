// SPDX-FileCopyrightText: 2026 Eslam Hamed
//
// SPDX-License-Identifier: MIT

"use client";

import * as React from "react";

import { cn } from "@/lib/utils";

import { Label } from "./label";

/**
 * v2 FormField — the single biggest ergonomics win.
 *
 * Replaces this 10-line pattern repeated 12+ times across feature forms:
 *
 *   <div className="space-y-2">
 *     <Label htmlFor="topic">Topic <span className="text-destructive">*</span></Label>
 *     <Input id="topic" aria-invalid={errors.topic ? true : undefined} {...register("topic")} />
 *     {errors.topic ? <p className="text-sm text-destructive" role="alert">{errors.topic.message}</p> : null}
 *   </div>
 *
 * With v2:
 *
 *   <FormField label="Topic" required error={errors.topic?.message}>
 *     <Input {...register("topic")} />
 *   </FormField>
 *
 * Wires up id/htmlFor, aria-invalid, aria-describedby, role="alert", and
 * description text. The child control receives id/aria-* via React.cloneElement.
 */

/**
 * The minimal shape we read off the child when cloning. Anything that
 * looks like a form control will already accept these props, so the
 * explicit typing here unblocks React 19's stricter `cloneElement`.
 */
type ControlProps = {
  id?: string;
  "aria-invalid"?: boolean | "true" | "false";
  "aria-describedby"?: string;
};

interface FormFieldProps {
  label: React.ReactNode;
  required?: boolean;
  optional?: boolean;
  /** Helper text shown under the label, before any error. */
  description?: React.ReactNode;
  /** Error message — when present, wires up aria-invalid + role="alert". */
  error?: React.ReactNode;
  /** Optional explicit id; otherwise a stable React-generated one is used. */
  htmlFor?: string;
  className?: string;
  children: React.ReactElement<ControlProps>;
}

export function FormField({
  label,
  required,
  optional,
  description,
  error,
  htmlFor,
  className,
  children,
}: FormFieldProps) {
  const generatedId = React.useId();
  const id = htmlFor ?? generatedId;
  const errorId = `${id}-error`;
  const descriptionId = `${id}-desc`;

  const describedBy =
    [error ? errorId : null, description ? descriptionId : null].filter(Boolean).join(" ") ||
    undefined;

  const childProps = children.props;
  const nextProps: ControlProps = {
    id,
    "aria-invalid": error ? true : childProps["aria-invalid"],
    "aria-describedby": describedBy ?? childProps["aria-describedby"],
  };
  const control = React.cloneElement(children, nextProps);

  return (
    <div className={cn("space-y-2", className)}>
      <Label htmlFor={id} required={required} optional={optional}>
        {label}
      </Label>
      {description ? (
        <p id={descriptionId} className="text-xs text-muted-foreground">
          {description}
        </p>
      ) : null}
      {control}
      {error ? (
        <p id={errorId} role="alert" className="text-sm text-destructive">
          {error}
        </p>
      ) : null}
    </div>
  );
}

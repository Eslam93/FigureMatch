// SPDX-FileCopyrightText: 2026 Eslam Hamed
//
// SPDX-License-Identifier: MIT

/**
 * v2 design-system barrel.
 *
 * Import everything from one path:
 *   import { Button, FormField, Input, Alert, Card } from "@/components/ui/v2";
 *
 * The v1 components in `components/ui/*` are untouched — v2 is additive.
 * See ./README.md for migration guidance.
 */

export { Alert, alertVariants, type AlertProps } from "./alert";
export { Badge, badgeVariants, type BadgeProps } from "./badge";
export { Button, buttonVariants, type ButtonProps } from "./button";
export { Card, CardBody, CardDescription, CardFooter, CardHeader, CardTitle } from "./card";
export {
  Dialog,
  DialogBody,
  DialogCloseButton,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "./dialog";
export { EmptyState, type EmptyStateProps } from "./empty-state";
export { FormField } from "./form-field";
export { Input, type InputProps } from "./input";
export { Label, type LabelProps } from "./label";
export { Select } from "./select";
export { Skeleton } from "./skeleton";
export { Spinner } from "./spinner";
export { StagedLoader, type StagedLoaderProps } from "./staged-loader";
export { Tabs } from "./tabs";
export { Textarea } from "./textarea";

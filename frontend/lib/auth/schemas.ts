// SPDX-FileCopyrightText: 2026 Eslam Hamed
//
// SPDX-License-Identifier: MIT

import { z } from "zod";

/**
 * Mirrors the backend's validation (see backend/app/schemas/auth.py).
 * Both schemas extend Pydantic's Field constraints; the frontend gets
 * the first pass at validation for UX, the backend remains the source
 * of truth.
 */

export const loginSchema = z.object({
  email: z.string().email("Enter a valid email"),
  password: z.string().min(1, "Password is required"),
});

export type LoginInput = z.infer<typeof loginSchema>;

export const registerSchema = z.object({
  email: z.string().email("Enter a valid email"),
  password: z
    .string()
    .min(8, "Password must be at least 8 characters")
    .max(128, "Password must be at most 128 characters")
    .refine((p) => /[A-Za-z]/.test(p), {
      message: "Password must contain at least one letter",
    })
    .refine((p) => /\d/.test(p), {
      message: "Password must contain at least one digit",
    })
    .refine((p) => new TextEncoder().encode(p).length <= 72, {
      message:
        "Password must be at most 72 bytes when UTF-8 encoded " +
        "(bcrypt silently truncates beyond that)",
    }),
  full_name: z.string().min(1, "Name is required").max(200, "Name must be at most 200 characters"),
});

export type RegisterInput = z.infer<typeof registerSchema>;

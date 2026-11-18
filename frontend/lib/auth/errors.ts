// SPDX-FileCopyrightText: 2026 Eslam Hamed
//
// SPDX-License-Identifier: MIT

/**
 * Map backend error envelope codes to user-facing messages.
 *
 * The backend always returns errors in the shape
 *   { error: { code, message, details }, meta: { request_id } }
 * — see backend/app/core/exceptions.py. The `message` is human-
 * readable but generic; we surface a more concrete UX message keyed
 * on `code`, falling back to the backend's message if the code is
 * unknown.
 */

const CODE_MESSAGES: Record<string, string> = {
  INVALID_CREDENTIALS: "Email or password is incorrect.",
  EMAIL_TAKEN: "An account with this email already exists.",
  WEAK_PASSWORD: "Password doesn't meet the strength requirements.",
  VALIDATION_FAILED: "Some fields don't look right — check below.",
  RATE_LIMITED: "Too many attempts. Please wait a minute and try again.",
  MISSING_REFRESH_TOKEN: "Session expired. Please sign in again.",
  INVALID_REFRESH_TOKEN: "Session expired. Please sign in again.",
};

export function authErrorMessage(
  errorBody: unknown,
  fallback = "Something went wrong. Please try again.",
): string {
  if (typeof errorBody !== "object" || errorBody === null) return fallback;
  const env = errorBody as {
    error?: { code?: string; message?: string };
  };
  const code = env.error?.code;
  if (code && CODE_MESSAGES[code]) return CODE_MESSAGES[code];
  return env.error?.message ?? fallback;
}

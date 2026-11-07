/**
 * Error copy for AI-provider failures.
 *
 * The content, image, improver and brand-voice hooks all turn an error
 * envelope into a message with generateErrorMessage, so these tests go
 * through it: AI codes get the shared copy, the domain codes keep
 * theirs, and an unknown code falls back to the backend's message.
 */

import { describe, expect, it } from "vitest";

import { generateErrorMessage } from "@/lib/content/hooks";
import { AI_ERROR_MESSAGES } from "@/lib/errors/ai-codes";

// The AI-provider codes in the backend's error contract.
const CONTRACT_CODES = [
  "AI_PROVIDER_AUTH_FAILED",
  "AI_RATE_LIMITED",
  "AI_UNAVAILABLE",
  "AI_TIMEOUT",
  "AI_OUTPUT_TRUNCATED",
  "AI_CONTENT_REJECTED",
  "AI_PROVIDER_MISCONFIGURED",
  "PROVIDER_ERROR",
];

function envelope(code: string, message = "Message from the backend.") {
  return { error: { code, message, details: {} }, meta: { request_id: "req-1" } };
}

describe("AI provider error messages", () => {
  it("maps AI provider codes to friendly copy", () => {
    expect(generateErrorMessage(envelope("AI_RATE_LIMITED"))).toBe(
      "The AI provider is busy. Wait a moment and try again.",
    );
    expect(generateErrorMessage(envelope("AI_UNAVAILABLE"))).toBe(
      "The AI provider is unavailable right now. Try again in a few minutes.",
    );
    expect(generateErrorMessage(envelope("AI_CONTENT_REJECTED"))).toBe(
      "The AI provider declined this request. Try rephrasing it.",
    );
  });

  it("has copy for exactly the codes in the backend contract", () => {
    expect(Object.keys(AI_ERROR_MESSAGES).sort()).toEqual([...CONTRACT_CODES].sort());
    for (const code of CONTRACT_CODES) {
      expect(generateErrorMessage(envelope(code))).toBe(AI_ERROR_MESSAGES[code]);
    }
  });

  it.each(["AI_PROVIDER_AUTH_FAILED", "AI_PROVIDER_MISCONFIGURED"])(
    "says %s is a server problem, not the user's, and retrying won't help",
    (code) => {
      const message = generateErrorMessage(envelope(code));
      expect(message).toMatch(/server configuration problem, not something you did wrong/);
      expect(message).toMatch(/Trying again won't help until it's fixed/);
    },
  );

  it("keeps the domain-specific entries", () => {
    expect(generateErrorMessage(envelope("RATE_LIMITED"))).toBe(
      "You've hit the per-minute generate limit. Wait a minute and try again.",
    );
    expect(generateErrorMessage(envelope("CONTENT_NOT_FOUND"))).toBe(
      "That content doesn't exist anymore.",
    );
  });

  it("falls back to the backend's message for an unknown code", () => {
    expect(generateErrorMessage(envelope("SOMETHING_NEW", "A sentence from the backend."))).toBe(
      "A sentence from the backend.",
    );
  });

  it("falls back to the caller's fallback when the body is not an envelope", () => {
    expect(generateErrorMessage(undefined, "Bad Gateway")).toBe("Bad Gateway");
  });
});

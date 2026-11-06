/**
 * Friendly copy for the error codes the backend returns when the AI
 * provider fails. The envelope's own message is safe to show, but this
 * copy says plainly whether trying again helps, and that the two
 * operator problems are not the user's fault.
 *
 * Error-code maps spread this object instead of repeating the codes,
 * so the copy can't drift apart between features.
 */
export const AI_ERROR_MESSAGES: Readonly<Record<string, string>> = {
  AI_PROVIDER_AUTH_FAILED:
    "The AI provider rejected the server's API key. This is a server configuration problem, not something you did wrong. Trying again won't help until it's fixed.",
  AI_PROVIDER_MISCONFIGURED:
    "The server isn't set up to use the AI provider. This is a server configuration problem, not something you did wrong. Trying again won't help until it's fixed.",
  AI_RATE_LIMITED: "The AI provider is busy. Wait a moment and try again.",
  AI_UNAVAILABLE: "The AI provider is unavailable right now. Try again in a few minutes.",
  AI_TIMEOUT: "The AI provider took too long to respond. Try again.",
  AI_OUTPUT_TRUNCATED: "The AI provider's reply was cut off before it finished. Try again.",
  AI_CONTENT_REJECTED: "The AI provider declined this request. Try rephrasing it.",
  PROVIDER_ERROR: "Something went wrong with the AI provider. Try again.",
};

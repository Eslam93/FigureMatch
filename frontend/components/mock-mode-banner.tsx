"use client";

import { Alert } from "@/components/ui/v2";
import { useMetaQuery } from "@/lib/meta/hooks";

/**
 * Full-width strip under the protected header, shown only while the
 * backend runs the mock AI provider, so nobody mistakes canned sample
 * text for real output.
 *
 * Renders nothing while /meta loads, when it fails (an older backend
 * has no /meta) and for every other provider mode. It uses
 * role="status" rather than the warning variant's default "alert": it
 * is a standing notice, so screen readers should not interrupt for it.
 */
export function MockModeBanner() {
  const meta = useMetaQuery();

  if (meta.data?.provider_mode !== "mock") return null;

  return (
    <Alert variant="warning" role="status" className="rounded-none border-x-0 border-t-0 px-6">
      Mock mode: generated content is canned sample text, not written from your input. Set
      AI_PROVIDER_MODE=openai and OPENAI_API_KEY on the backend for real generation.
    </Alert>
  );
}

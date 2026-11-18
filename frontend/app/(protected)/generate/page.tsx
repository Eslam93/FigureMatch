// SPDX-FileCopyrightText: 2026 Eslam Hamed
//
// SPDX-License-Identifier: MIT

import { GenerateForm } from "@/components/features/generate-form";

/**
 * /generate — Slice 1 ships blog-post generation against the mock or
 * OpenAI providers (server-selected via AI_PROVIDER_MODE). The form
 * widens to LinkedIn / email / ad-copy in Slice 2 without page-level
 * changes; the tab strip is already there, just disabled.
 */
export default function GeneratePage() {
  return <GenerateForm />;
}

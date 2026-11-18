// SPDX-FileCopyrightText: 2026 Eslam Hamed
//
// SPDX-License-Identifier: MIT

"use client";

import { ContentList } from "@/components/features/content-list";

/**
 * Dashboard landing page (inside the protected layout).
 *
 * Slice 4 replaces the Phase-2 welcome stub with the real content
 * list — paginated, filterable, searchable, with a per-card delete +
 * undo affordance.
 */
export default function DashboardPage() {
  return <ContentList />;
}

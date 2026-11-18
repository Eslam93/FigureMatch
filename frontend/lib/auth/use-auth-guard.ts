// SPDX-FileCopyrightText: 2026 Eslam Hamed
//
// SPDX-License-Identifier: MIT

"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { useMeQuery } from "./use-me";

/**
 * Auth guard hook used by the protected layout.
 *
 * Calls /auth/me on mount. The API client's 401 interceptor handles
 * one refresh-and-retry transparently before this query sees a real
 * error. If the query still errors, the user is unauthenticated —
 * redirect to /login with router.replace so the protected route
 * doesn't pollute browser history.
 *
 * Returns the query so callers can render loading state + the user's
 * data when authenticated.
 */
export function useAuthGuard() {
  const router = useRouter();
  const me = useMeQuery();

  useEffect(() => {
    if (me.isError) {
      router.replace("/login");
    }
  }, [me.isError, router]);

  return me;
}

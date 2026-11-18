// SPDX-FileCopyrightText: 2026 Eslam Hamed
//
// SPDX-License-Identifier: MIT

"use client";

import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";

import { authErrorMessage } from "./errors";

/**
 * Fetch the authenticated user via GET /auth/me.
 *
 * The API client's 401 interceptor already handles refresh-and-retry,
 * so this query disables React-Query's retry — a 401 here means the
 * refresh attempt already failed. The auth-guard hook reads
 * `isError` to redirect to /login.
 */
export function useMeQuery() {
  return useQuery({
    queryKey: ["auth", "me"],
    queryFn: async () => {
      const { data, error, response } = await api.GET("/auth/me");
      if (error || !data) {
        throw new Error(authErrorMessage(error, response.statusText));
      }
      return data;
    },
    retry: false,
    refetchOnWindowFocus: false,
    staleTime: 5 * 60 * 1000, // 5 minutes — `/me` is mostly static
  });
}

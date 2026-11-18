// SPDX-FileCopyrightText: 2026 Eslam Hamed
//
// SPDX-License-Identifier: MIT

"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";

import { api } from "@/lib/api";
import { useAuthStore } from "@/lib/auth-store";

import { authErrorMessage } from "./errors";
import type { LoginInput, RegisterInput } from "./schemas";

/**
 * Auth mutation hooks. All three follow the same shape:
 *   - call the backend endpoint via the typed client
 *   - on success, update the auth store + navigate
 *   - on error, surface a friendly message via the mutation's
 *     `error` field for the form to render
 *
 * Refresh / logout don't need hooks at this level — the API client
 * interceptor handles refresh automatically, and logout is one call
 * away from anywhere via `useLogout`.
 */

export function useLoginMutation() {
  const router = useRouter();
  const setAccessToken = useAuthStore((s) => s.setAccessToken);

  return useMutation({
    mutationFn: async (input: LoginInput) => {
      const { data, error, response } = await api.POST("/auth/login", {
        body: input,
      });
      if (error || !data) {
        throw new Error(authErrorMessage(error, response.statusText));
      }
      return data;
    },
    onSuccess: (data) => {
      setAccessToken(data.access_token);
      router.push("/dashboard");
    },
  });
}

export function useRegisterMutation() {
  const router = useRouter();
  const setAccessToken = useAuthStore((s) => s.setAccessToken);

  return useMutation({
    mutationFn: async (input: RegisterInput) => {
      const { data, error, response } = await api.POST("/auth/register", {
        body: input,
      });
      if (error || !data) {
        throw new Error(authErrorMessage(error, response.statusText));
      }
      return data;
    },
    onSuccess: (data) => {
      setAccessToken(data.access_token);
      router.push("/dashboard");
    },
  });
}

export function useLogoutMutation() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const clearAccessToken = useAuthStore((s) => s.clearAccessToken);

  return useMutation({
    mutationFn: async () => {
      // Logout is idempotent at the backend; ignore non-204 returns.
      await api.POST("/auth/logout", {});
    },
    onSettled: () => {
      clearAccessToken();
      // Wipe every cached query — `["auth", "me"]`, the dashboard
      // lists, brand voices, etc. — so a second user signing in on
      // the same browser never observes the first user's data while
      // a stale query rehydrates. `clear()` is the bluntest option;
      // selective removal would have to track every query key in
      // the app.
      queryClient.clear();
      router.push("/login");
    },
  });
}

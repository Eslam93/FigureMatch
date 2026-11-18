// SPDX-FileCopyrightText: 2026 Eslam Hamed
//
// SPDX-License-Identifier: MIT

/**
 * Typed API client wrapper around openapi-fetch.
 *
 * Schema generation (`pnpm gen:api`) downloads the live OpenAPI spec
 * from the deployed backend and writes it to `types/api.d.ts`. Until
 * the backend is live, a hand-stubbed `paths` type lives there and
 * gets replaced on first gen.
 *
 * The client sends `credentials: 'include'` so the httpOnly refresh
 * cookie flows on cross-origin requests once Amplify + App Runner
 * are wired.
 *
 * 401 handling:
 *   - On any 401 (except from /auth/* itself), the response middleware
 *     calls /auth/refresh
 *   - If refresh succeeds, the new access token is stored and the
 *     original request is retried once
 *   - If refresh fails, the access token is cleared and the response
 *     middleware passes the original 401 through — the caller's
 *     auth-guard hook (P2.9c) redirects to /login
 *
 * In-flight refreshes are deduplicated: if multiple requests 401
 * simultaneously, they all wait on the single refresh promise.
 *
 * Body preservation: openapi-fetch consumes the request body when it
 * dispatches. `request.clone()` in `onResponse` would return a clone
 * whose body is also marked consumed — useless for retry. The
 * `onRequest` hook captures the serialized body into a WeakMap keyed
 * on the request before dispatch, and the retry path reads it back.
 */

import createClient, { type Middleware } from "openapi-fetch";

import type { paths } from "@/types/api";

const baseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

// Per-request cached body so the 401 retry has something to send. Keyed
// by Request to avoid leaking references; entries are GC'd once the
// caller drops the request.
const requestBodyCache: WeakMap<Request, string> = new WeakMap();

// Single-flight refresh — multiple concurrent 401s share one /auth/refresh
// call. Resolves to true on success (caller retries) or false on failure.
let inflightRefresh: Promise<boolean> | null = null;

async function refreshAccessToken(): Promise<boolean> {
  // Lazy-import the store so SSR doesn't drag Zustand into the server bundle.
  const { useAuthStore } = await import("@/lib/auth-store");
  try {
    const response = await fetch(`${baseUrl}/auth/refresh`, {
      method: "POST",
      credentials: "include",
    });
    if (!response.ok) {
      useAuthStore.getState().clearAccessToken();
      return false;
    }
    const data = (await response.json()) as { access_token?: string };
    if (!data.access_token) {
      useAuthStore.getState().clearAccessToken();
      return false;
    }
    useAuthStore.getState().setAccessToken(data.access_token);
    return true;
  } catch {
    useAuthStore.getState().clearAccessToken();
    return false;
  }
}

const authMiddleware: Middleware = {
  async onRequest({ request }) {
    if (typeof window !== "undefined") {
      const { useAuthStore } = await import("@/lib/auth-store");
      const token = useAuthStore.getState().accessToken;
      if (token) {
        request.headers.set("authorization", `Bearer ${token}`);
      }
      // Cache the body BEFORE openapi-fetch consumes it. The 401
      // retry path reads from this cache. GET/HEAD have no body, so
      // skip the read (request.clone().text() on a bodyless request
      // returns "" but still costs a clone).
      if (request.method !== "GET" && request.method !== "HEAD") {
        try {
          const body = await request.clone().text();
          requestBodyCache.set(request, body);
        } catch {
          // If the body can't be cloned (rare — already consumed by
          // an upstream middleware), the retry simply won't have a
          // body. The request fails on retry instead of corrupting
          // state.
        }
      }
    }
    return request;
  },

  async onResponse({ request, response }) {
    // Don't recurse on /auth/refresh, and skip retries on the auth
    // endpoints the user is explicitly invoking (login/register/logout)
    // — those 401s mean "credentials wrong", not "session expired".
    const url = new URL(request.url);
    const isAuthEndpoint =
      url.pathname.endsWith("/auth/refresh") ||
      url.pathname.endsWith("/auth/login") ||
      url.pathname.endsWith("/auth/register") ||
      url.pathname.endsWith("/auth/logout");
    if (response.status !== 401 || isAuthEndpoint) {
      return response;
    }
    if (typeof window === "undefined") return response;

    if (!inflightRefresh) {
      inflightRefresh = refreshAccessToken().finally(() => {
        inflightRefresh = null;
      });
    }
    const refreshed = await inflightRefresh;
    if (!refreshed) return response;

    // Retry the original request with the fresh token + cached body.
    const { useAuthStore } = await import("@/lib/auth-store");
    const newToken = useAuthStore.getState().accessToken;
    const retryHeaders = new Headers(request.headers);
    if (newToken) retryHeaders.set("authorization", `Bearer ${newToken}`);
    const body =
      request.method === "GET" || request.method === "HEAD"
        ? undefined
        : requestBodyCache.get(request);
    return fetch(request.url, {
      method: request.method,
      headers: retryHeaders,
      body,
      credentials: "include",
    });
  },
};

export const api = createClient<paths>({
  baseUrl,
  credentials: "include",
});

api.use(authMiddleware);

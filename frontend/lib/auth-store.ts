// SPDX-FileCopyrightText: 2026 Eslam Hamed
//
// SPDX-License-Identifier: MIT

import { create } from "zustand";

/**
 * In-memory auth store.
 *
 * Holds the access token ONLY in memory — never persisted to
 * localStorage / sessionStorage / cookies on the client side. The
 * refresh token is server-set as an httpOnly cookie by the backend
 * and never readable by JS (that's the whole point of httpOnly).
 *
 * On page reload, the access token is gone. The 401 interceptor in
 * `lib/api.ts` calls /auth/refresh on the next API call — if the
 * refresh cookie is still valid, the user transparently gets a fresh
 * access token and the request retries. If the refresh cookie is
 * also gone (logged out, or 30-day TTL elapsed), the interceptor
 * routes the user to /login.
 *
 * This matches the brief's auth strategy: in-memory access tokens
 * are immune to XSS exfiltration; httpOnly refresh cookies are
 * immune to JS-side theft.
 */
interface AuthState {
  accessToken: string | null;
  setAccessToken: (token: string | null) => void;
  clearAccessToken: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  accessToken: null,
  setAccessToken: (token) => set({ accessToken: token }),
  clearAccessToken: () => set({ accessToken: null }),
}));

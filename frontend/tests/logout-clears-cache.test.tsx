// SPDX-FileCopyrightText: 2026 Eslam Hamed
//
// SPDX-License-Identifier: MIT

/**
 * Logout must clear the TanStack Query cache so a second user signing
 * in on the same browser never observes the first user's data while a
 * stale `["auth", "me"]` (or any other) query rehydrates.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useLogoutMutation } from "@/lib/auth/hooks";

// Stub out the API client so the mutation resolves synchronously and
// doesn't issue real fetch. `next/navigation` is also mocked because
// `useRouter()` isn't available in a test render without it.
vi.mock("@/lib/api", () => ({
  api: {
    POST: vi.fn(async () => ({ data: null, error: null, response: { ok: true } })),
  },
}));

const routerPush = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: routerPush }),
}));

describe("useLogoutMutation cache hygiene", () => {
  beforeEach(() => {
    routerPush.mockReset();
  });

  it("calls queryClient.clear() on settle", async () => {
    const queryClient = new QueryClient({
      defaultOptions: { mutations: { retry: false }, queries: { retry: false } },
    });
    const clearSpy = vi.spyOn(queryClient, "clear");

    // Pre-populate a cached query to make the clear observable.
    queryClient.setQueryData(["auth", "me"], { id: "user-1", email: "a@b.c" });
    expect(queryClient.getQueryData(["auth", "me"])).not.toBeUndefined();

    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );

    const { result } = renderHook(() => useLogoutMutation(), { wrapper });
    result.current.mutate();
    await waitFor(() => expect(clearSpy).toHaveBeenCalled());
    expect(queryClient.getQueryData(["auth", "me"])).toBeUndefined();
    expect(routerPush).toHaveBeenCalledWith("/login");
  });
});

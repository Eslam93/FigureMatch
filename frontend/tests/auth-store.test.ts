// SPDX-FileCopyrightText: 2026 Eslam Hamed
//
// SPDX-License-Identifier: MIT

import { beforeEach, describe, expect, it } from "vitest";

import { useAuthStore } from "@/lib/auth-store";

describe("useAuthStore", () => {
  beforeEach(() => {
    useAuthStore.getState().clearAccessToken();
  });

  it("starts with a null access token", () => {
    expect(useAuthStore.getState().accessToken).toBeNull();
  });

  it("stores a token via setAccessToken", () => {
    useAuthStore.getState().setAccessToken("test-token");
    expect(useAuthStore.getState().accessToken).toBe("test-token");
  });

  it("clears the token via clearAccessToken", () => {
    useAuthStore.getState().setAccessToken("test-token");
    useAuthStore.getState().clearAccessToken();
    expect(useAuthStore.getState().accessToken).toBeNull();
  });
});

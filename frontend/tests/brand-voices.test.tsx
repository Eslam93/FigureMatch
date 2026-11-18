// SPDX-FileCopyrightText: 2026 Eslam Hamed
//
// SPDX-License-Identifier: MIT

/**
 * Component test for the brand-voices list + create flow.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { BrandVoicesList } from "@/components/features/brand-voices-list";

import type { BrandVoice } from "@/lib/brand-voices/hooks";

const mocks = vi.hoisted(() => ({
  listResponse: { data: [] as BrandVoice[] },
  createMutate: vi.fn(),
  updateMutate: vi.fn(),
  deleteMutate: vi.fn(),
}));

const sample = (overrides: Partial<BrandVoice> = {}): BrandVoice => ({
  id: overrides.id ?? "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
  name: overrides.name ?? "Direct",
  description: overrides.description ?? "Direct and honest.",
  tone_descriptors: overrides.tone_descriptors ?? ["direct", "warm"],
  banned_words: overrides.banned_words ?? ["leverage"],
  sample_text: overrides.sample_text ?? null,
  target_audience: overrides.target_audience ?? null,
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
  deleted_at: null,
});

vi.mock("@/lib/brand-voices/hooks", () => ({
  useBrandVoicesQuery: () => ({
    data: mocks.listResponse,
    isPending: false,
    isError: false,
    error: null,
  }),
  useCreateBrandVoiceMutation: () => ({
    mutate: mocks.createMutate,
    isPending: false,
  }),
  useUpdateBrandVoiceMutation: () => ({
    mutate: mocks.updateMutate,
    isPending: false,
  }),
  useDeleteBrandVoiceMutation: () => ({
    mutate: mocks.deleteMutate,
    isPending: false,
    variables: undefined,
  }),
}));

vi.mock("sonner", () => ({
  toast: Object.assign(vi.fn(), { error: vi.fn(), success: vi.fn() }),
  Toaster: () => null,
}));

function renderWithProviders(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

describe("BrandVoicesList", () => {
  beforeEach(() => {
    mocks.createMutate.mockReset();
    mocks.updateMutate.mockReset();
    mocks.deleteMutate.mockReset();
    mocks.listResponse = { data: [] };
  });

  it("renders the empty state when there are no voices", () => {
    renderWithProviders(<BrandVoicesList />);
    expect(screen.getByTestId("bv-empty")).toBeInTheDocument();
  });

  it("renders a row per voice and shows tone descriptors", () => {
    mocks.listResponse = { data: [sample()] };
    renderWithProviders(<BrandVoicesList />);
    const row = screen.getByTestId("bv-row-aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa");
    expect(row).toHaveTextContent("Direct");
    expect(row).toHaveTextContent("direct · warm");
  });

  it("opens the create form when the New button is clicked", async () => {
    const user = userEvent.setup();
    renderWithProviders(<BrandVoicesList />);
    await user.click(screen.getByTestId("bv-create"));
    expect(screen.getByTestId("brand-voice-form")).toBeInTheDocument();
  });

  it("submits the create mutation with the parsed CSV lists", async () => {
    const user = userEvent.setup();
    renderWithProviders(<BrandVoicesList />);
    await user.click(screen.getByTestId("bv-create"));
    await user.type(screen.getByTestId("bv-name"), "My voice");
    await user.type(screen.getByTestId("bv-tone"), "direct, warm");
    await user.type(screen.getByTestId("bv-banned"), "leverage,synergy");
    await user.click(screen.getByTestId("bv-submit"));
    expect(mocks.createMutate).toHaveBeenCalledTimes(1);
    const payload = mocks.createMutate.mock.calls[0][0];
    expect(payload).toMatchObject({
      name: "My voice",
      tone_descriptors: ["direct", "warm"],
      banned_words: ["leverage", "synergy"],
    });
  });
});

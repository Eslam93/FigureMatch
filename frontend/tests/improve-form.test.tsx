// SPDX-FileCopyrightText: 2026 Eslam Hamed
//
// SPDX-License-Identifier: MIT

/**
 * Component test for ImproveForm.
 *
 * Covers: validation gates (min length + required audience), submit
 * shape, result-panel rendering on success.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ImproveForm } from "@/components/features/improve-form";

import type { ImprovementResponse } from "@/lib/improver/hooks";

const SAMPLE_RESPONSE: ImprovementResponse = {
  id: "00000000-0000-0000-0000-000000000010",
  original_text: "The original draft that we are improving for the test.",
  improved_text: "The crisper improved draft for the test.",
  goal: "persuasive",
  new_audience: null,
  explanation: ["Tightened the opening.", "Replaced filler with a verb."],
  changes_summary: {
    tone_shift: "softened_to_direct",
    length_change_pct: -25.5,
    key_additions: ["concrete claim"],
    key_removals: ["filler"],
  },
  original_word_count: 11,
  improved_word_count: 7,
  model_id: "mock-llm-v1",
  input_tokens: 20,
  output_tokens: 30,
  cost_usd: "0",
  created_at: new Date().toISOString(),
  deleted_at: null,
};

const mocks = vi.hoisted(() => ({
  mutateFn: vi.fn(),
  resetFn: vi.fn(),
}));

let mutationState: {
  mutate: typeof mocks.mutateFn;
  reset: typeof mocks.resetFn;
  isPending: boolean;
  isError: boolean;
  isSuccess: boolean;
  data?: ImprovementResponse;
  error: Error | null;
} = {
  mutate: mocks.mutateFn,
  reset: mocks.resetFn,
  isPending: false,
  isError: false,
  isSuccess: false,
  data: undefined,
  error: null,
};

vi.mock("@/lib/improver/hooks", async () => {
  const actual =
    await vi.importActual<typeof import("@/lib/improver/hooks")>("@/lib/improver/hooks");
  return {
    ...actual,
    useImproveMutation: () => mutationState,
  };
});

function renderWithProviders(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

describe("ImproveForm", () => {
  beforeEach(() => {
    mocks.mutateFn.mockReset();
    mocks.resetFn.mockReset();
    mutationState = {
      mutate: mocks.mutateFn,
      reset: mocks.resetFn,
      isPending: false,
      isError: false,
      isSuccess: false,
      data: undefined,
      error: null,
    };
  });

  it("blocks submit when the original text is shorter than 10 chars", async () => {
    const user = userEvent.setup();
    renderWithProviders(<ImproveForm />);
    await user.type(screen.getByTestId("improve-original"), "too short");
    await user.click(screen.getByTestId("improve-submit"));
    expect(mocks.mutateFn).not.toHaveBeenCalled();
    expect(screen.getByTestId("improve-validation")).toHaveTextContent(/at least 10 characters/i);
  });

  it("requires a new audience when goal=audience_rewrite", async () => {
    const user = userEvent.setup();
    renderWithProviders(<ImproveForm />);
    await user.type(
      screen.getByTestId("improve-original"),
      "Some text long enough to pass the min length gate.",
    );
    await user.selectOptions(screen.getByTestId("improve-goal"), "audience_rewrite");
    await user.click(screen.getByTestId("improve-submit"));
    expect(mocks.mutateFn).not.toHaveBeenCalled();
    expect(screen.getByTestId("improve-validation")).toHaveTextContent(/who the new audience/i);
  });

  it("submits the right payload when inputs are valid", async () => {
    const user = userEvent.setup();
    renderWithProviders(<ImproveForm />);
    await user.type(
      screen.getByTestId("improve-original"),
      "Make this draft more persuasive please.",
    );
    await user.click(screen.getByTestId("improve-submit"));
    expect(mocks.mutateFn).toHaveBeenCalledTimes(1);
    const payload = mocks.mutateFn.mock.calls[0][0];
    expect(payload).toMatchObject({
      original_text: "Make this draft more persuasive please.",
      goal: "persuasive",
    });
  });

  it("renders the side-by-side result panel on success", () => {
    mutationState = { ...mutationState, isSuccess: true, data: SAMPLE_RESPONSE };
    renderWithProviders(<ImproveForm />);
    const result = screen.getByTestId("improve-result");
    expect(within(result).getByTestId("improve-result-original")).toHaveTextContent(
      "The original draft",
    );
    expect(within(result).getByTestId("improve-result-improved")).toHaveTextContent(
      "The crisper improved",
    );
    const explanation = within(result).getByTestId("improve-result-explanation");
    expect(explanation.children.length).toBe(2);
  });
});

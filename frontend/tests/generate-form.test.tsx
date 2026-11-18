// SPDX-FileCopyrightText: 2026 Eslam Hamed
//
// SPDX-License-Identifier: MIT

/**
 * Component-level test for the /generate flow.
 *
 * Mocks `useGenerateMutation` so we can exercise the form + result
 * panel without standing up the API client or TanStack Query. The
 * mutation hook surface (`isPending`, `isError`, `isSuccess`, `data`,
 * `mutate`) is the contract; this test treats it as one.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { GenerateForm } from "@/components/features/generate-form";

import type { GenerateResponse } from "@/lib/content/hooks";

const FAKE_RESPONSE: GenerateResponse = {
  content_id: "11111111-1111-1111-1111-111111111111",
  content_type: "blog_post" as const,
  result: {
    title: "Mocked Title",
    meta_description: "Short description.",
    intro: "Intro text.",
    sections: [{ heading: "H", body: "B" }],
    conclusion: "Done.",
    suggested_tags: ["mock"],
  },
  rendered_text: "# Mocked Title\n\nIntro text.\n\n## H\n\nB\n\nDone.\n\nTags: #mock",
  result_parse_status: "ok" as const,
  word_count: 7,
  usage: {
    model_id: "mock-llm-v1",
    input_tokens: 10,
    output_tokens: 20,
    cost_usd: "0",
  },
  created_at: new Date().toISOString(),
};

const mockMutate = vi.fn();
const mockReset = vi.fn();

vi.mock("@/lib/content/hooks", () => {
  return {
    useGenerateMutation: () => mutationState,
    generateErrorMessage: (e: unknown, fb = "fallback") => fb,
  };
});

// Brand-voice dropdown fetches at mount — stub the query so the test
// doesn't fire a real fetch.
vi.mock("@/lib/brand-voices/hooks", () => ({
  useBrandVoicesQuery: () => ({
    data: { data: [] },
    isPending: false,
    isError: false,
    error: null,
  }),
}));

// ImagePanel is rendered when generation succeeds — stub its hooks so
// the test doesn't fire a real fetch against the (missing) backend.
vi.mock("@/lib/content/image-hooks", () => ({
  IMAGE_STYLES: [
    { value: "photorealistic", label: "Photorealistic" },
    { value: "illustration", label: "Illustration" },
  ],
  useImageListQuery: () => ({
    data: { data: [] },
    isPending: false,
    isError: false,
    error: null,
  }),
  useImageGenerateMutation: () => ({
    mutate: vi.fn(),
    isPending: false,
  }),
}));

vi.mock("sonner", () => ({
  toast: Object.assign(vi.fn(), { error: vi.fn(), success: vi.fn() }),
  Toaster: () => null,
}));

// Mutable state the mocked hook returns. Tests flip this to walk through
// idle → pending → success / error.
let mutationState: {
  mutate: typeof mockMutate;
  reset: typeof mockReset;
  isPending: boolean;
  isError: boolean;
  isSuccess: boolean;
  data: GenerateResponse | undefined;
  error: Error | null;
} = {
  mutate: mockMutate,
  reset: mockReset,
  isPending: false,
  isError: false,
  isSuccess: false,
  data: undefined,
  error: null,
};

function renderWithProviders(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

describe("GenerateForm", () => {
  beforeEach(() => {
    mockMutate.mockReset();
    mockReset.mockReset();
    mutationState = {
      mutate: mockMutate,
      reset: mockReset,
      isPending: false,
      isError: false,
      isSuccess: false,
      data: undefined,
      error: null,
    };
  });

  it("shows every content type enabled and clickable", () => {
    renderWithProviders(<GenerateForm />);
    const tabs = screen.getByTestId("content-type-tabs");
    const blogTab = within(tabs).getByTestId("content-type-tab-blog_post");
    expect(blogTab).toHaveAttribute("aria-selected", "true");
    expect(blogTab).not.toBeDisabled();

    for (const value of ["linkedin_post", "email", "ad_copy"]) {
      const tab = within(tabs).getByTestId(`content-type-tab-${value}`);
      expect(tab).not.toBeDisabled();
      expect(tab).toHaveAttribute("aria-disabled", "false");
      expect(tab).not.toHaveAttribute("title");
    }
  });

  it("switches content type when a different tab is clicked", async () => {
    const user = userEvent.setup();
    renderWithProviders(<GenerateForm />);
    const tabs = screen.getByTestId("content-type-tabs");
    await user.click(within(tabs).getByTestId("content-type-tab-linkedin_post"));
    await user.type(screen.getByTestId("generate-topic"), "A meaningful topic");
    await user.click(screen.getByTestId("generate-submit"));
    expect(mockMutate).toHaveBeenCalledTimes(1);
    expect(mockMutate.mock.calls[0][0]).toMatchObject({
      content_type: "linkedin_post",
      topic: "A meaningful topic",
    });
  });

  it("blocks submit when topic is below the min length", async () => {
    const user = userEvent.setup();
    renderWithProviders(<GenerateForm />);
    await user.type(screen.getByTestId("generate-topic"), "ab");
    await user.click(screen.getByTestId("generate-submit"));
    expect(mockMutate).not.toHaveBeenCalled();
    expect(await screen.findByText(/Topic needs at least 3 characters/i)).toBeInTheDocument();
  });

  it("submits valid input and shows staged loader while pending", async () => {
    const user = userEvent.setup();
    renderWithProviders(<GenerateForm />);
    await user.type(screen.getByTestId("generate-topic"), "A meaningful topic");
    await user.type(screen.getByTestId("generate-tone"), "informative");

    // Simulate "pending" before clicking so the loader is in the tree.
    mutationState = { ...mutationState, isPending: true };
    await user.click(screen.getByTestId("generate-submit"));
    expect(mockMutate).toHaveBeenCalledTimes(1);
    expect(mockMutate.mock.calls[0][0]).toMatchObject({
      content_type: "blog_post",
      topic: "A meaningful topic",
      tone: "informative",
    });
    expect(screen.getByTestId("staged-loader-label")).toBeInTheDocument();
  });

  it("renders the result markdown and copy button on success", async () => {
    mutationState = {
      ...mutationState,
      isSuccess: true,
      data: FAKE_RESPONSE,
    };
    renderWithProviders(<GenerateForm />);
    const body = screen.getByTestId("generate-result-body");
    expect(within(body).getByRole("heading", { level: 1 })).toHaveTextContent("Mocked Title");
    expect(screen.getByTestId("generate-result-copy")).toBeInTheDocument();
    expect(screen.getByTestId("generate-result-model")).toHaveTextContent("mock-llm-v1");
  });

  it("shows the fallback-mode banner on FAILED parse status", () => {
    const failedData: GenerateResponse = {
      ...FAKE_RESPONSE,
      result: null,
      result_parse_status: "failed",
      rendered_text: "{ raw model output that never parsed }",
    };
    mutationState = {
      ...mutationState,
      isSuccess: true,
      data: failedData,
    };
    renderWithProviders(<GenerateForm />);
    expect(screen.getByText(/Generated in fallback mode/i)).toBeInTheDocument();
    // Raw text rendered inside a <pre>, not as markdown.
    const body = screen.getByTestId("generate-result-body");
    expect(body.querySelector("pre")).not.toBeNull();
  });

  it("renders an error banner with a dismiss button on failure", async () => {
    const user = userEvent.setup();
    mutationState = {
      ...mutationState,
      isError: true,
      error: new Error("Too many requests"),
    };
    renderWithProviders(<GenerateForm />);
    expect(screen.getByTestId("generate-error")).toHaveTextContent("Too many requests");
    // v2 Alert renders its dismiss button with aria-label="Dismiss" instead
    // of a custom test-id. Scope the lookup to the alert so we hit the right
    // button if a future toast also gets one.
    const errorAlert = screen.getByTestId("generate-error");
    await user.click(within(errorAlert).getByRole("button", { name: /dismiss/i }));
    await waitFor(() => expect(mockReset).toHaveBeenCalled());
  });
});

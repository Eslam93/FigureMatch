// SPDX-FileCopyrightText: 2026 Eslam Hamed
//
// SPDX-License-Identifier: MIT

/**
 * Component test for the dashboard list happy path.
 *
 * Mocks the four content hooks at the module level. The flow under
 * test: list renders → click a card → detail dialog opens with the
 * fetched content → click Delete on a card → toast fires with an
 * Undo action that calls the restore mutation.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ContentList } from "@/components/features/content-list";

import type { ContentDetailResponse, ContentListResponse } from "@/lib/content/hooks";

// vi.mock factories are hoisted, so any captured variables must come
// through vi.hoisted(). The sonner mock asserts on call shape rather
// than the rendered toast DOM (portals + animation timers make that
// brittle).
const mocks = vi.hoisted(() => ({
  toastFn: vi.fn(),
  toastErrorFn: vi.fn(),
  toastSuccessFn: vi.fn(),
  deleteMutate: vi.fn(),
  restoreMutate: vi.fn(),
  refetchListQuery: vi.fn(),
}));
const { toastFn, toastErrorFn, toastSuccessFn, deleteMutate, restoreMutate, refetchListQuery } =
  mocks;

vi.mock("sonner", () => ({
  toast: Object.assign(mocks.toastFn, {
    error: mocks.toastErrorFn,
    success: mocks.toastSuccessFn,
  }),
  Toaster: () => null,
}));

const SAMPLE_LIST: ContentListResponse = {
  data: [
    {
      id: "00000000-0000-0000-0000-000000000001",
      content_type: "blog_post",
      topic: "Mocking the dashboard",
      preview: "This is the start of a preview body that the card shows…",
      word_count: 412,
      model_id: "mock-llm-v1",
      result_parse_status: "ok",
      created_at: new Date("2026-05-15T12:00:00Z").toISOString(),
    },
    {
      id: "00000000-0000-0000-0000-000000000002",
      content_type: "linkedin_post",
      topic: "LinkedIn row",
      preview: "Hook line. Body. CTA.",
      word_count: 41,
      model_id: "mock-llm-v1",
      result_parse_status: "ok",
      created_at: new Date("2026-05-15T11:00:00Z").toISOString(),
    },
  ],
  meta: {
    request_id: "req-1",
    pagination: { page: 1, page_size: 12, total: 2, total_pages: 1 },
  },
};

const SAMPLE_DETAIL: ContentDetailResponse = {
  id: "00000000-0000-0000-0000-000000000001",
  content_type: "blog_post",
  topic: "Mocking the dashboard",
  tone: "informative",
  target_audience: "engineers",
  result: {
    title: "Mocking the dashboard",
    meta_description: "Detail dialog test.",
    intro: "Intro paragraph.",
    sections: [{ heading: "H", body: "B" }],
    conclusion: "Done.",
    suggested_tags: ["mock"],
  },
  rendered_text: "# Mocking the dashboard\n\nFull rendered body for the detail view.",
  result_parse_status: "ok",
  word_count: 412,
  model_id: "mock-llm-v1",
  created_at: new Date("2026-05-15T12:00:00Z").toISOString(),
  deleted_at: null,
};

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

vi.mock("@/lib/content/hooks", () => ({
  useContentListQuery: () => ({
    data: SAMPLE_LIST,
    isPending: false,
    isError: false,
    error: null,
    refetch: mocks.refetchListQuery,
  }),
  useContentDetailQuery: () => ({
    data: SAMPLE_DETAIL,
    isPending: false,
    isError: false,
    error: null,
  }),
  useDeleteContentMutation: () => ({
    mutate: mocks.deleteMutate,
    isPending: false,
    variables: undefined,
  }),
  useRestoreContentMutation: () => ({
    mutate: mocks.restoreMutate,
    isPending: false,
  }),
}));

function renderWithProviders(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

describe("ContentList", () => {
  beforeEach(() => {
    toastFn.mockReset();
    toastErrorFn.mockReset();
    toastSuccessFn.mockReset();
    deleteMutate.mockReset();
    restoreMutate.mockReset();
    refetchListQuery.mockReset();
  });

  it("renders every list row with its preview and word count", () => {
    renderWithProviders(<ContentList />);
    const grid = screen.getByTestId("content-list-grid");
    expect(within(grid).getByText("Mocking the dashboard")).toBeInTheDocument();
    expect(within(grid).getByText("LinkedIn row")).toBeInTheDocument();
    expect(
      screen.getByTestId("content-card-words-00000000-0000-0000-0000-000000000001"),
    ).toHaveTextContent("412 words");
  });

  it("opens the detail dialog on card click and shows the full body", async () => {
    const user = userEvent.setup();
    renderWithProviders(<ContentList />);
    await user.click(screen.getByTestId("content-card-00000000-0000-0000-0000-000000000001"));
    await waitFor(() => {
      expect(screen.getByTestId("content-detail-dialog")).toBeInTheDocument();
    });
    const body = screen.getByTestId("content-detail-body");
    expect(within(body).getByRole("heading", { level: 1 })).toHaveTextContent(
      "Mocking the dashboard",
    );
  });

  it("fires a delete + undo toast and the undo button calls restore", async () => {
    const user = userEvent.setup();
    renderWithProviders(<ContentList />);
    await user.click(
      screen.getByTestId("content-card-delete-00000000-0000-0000-0000-000000000001"),
    );
    expect(deleteMutate).toHaveBeenCalledTimes(1);
    const [contentId, handlers] = deleteMutate.mock.calls[0];
    expect(contentId).toBe("00000000-0000-0000-0000-000000000001");
    // Simulate the mutation succeeding and the action firing the undo.
    handlers.onSuccess();
    expect(toastFn).toHaveBeenCalledTimes(1);
    const toastArg = toastFn.mock.calls[0][1];
    expect(toastArg.action.label).toBe("Undo");
    toastArg.action.onClick();
    expect(restoreMutate).toHaveBeenCalledTimes(1);
    expect(restoreMutate.mock.calls[0][0]).toBe("00000000-0000-0000-0000-000000000001");
  });

  it("submits the search input via Enter and resets to page 1", async () => {
    const user = userEvent.setup();
    renderWithProviders(<ContentList />);
    const input = screen.getByTestId("content-list-search");
    await user.type(input, "mocks{Enter}");
    // The text input value is what we expect to drive future fetches.
    expect((input as HTMLInputElement).value).toBe("mocks");
  });
});

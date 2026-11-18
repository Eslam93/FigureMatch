// SPDX-FileCopyrightText: 2026 Eslam Hamed
//
// SPDX-License-Identifier: MIT

/**
 * Component test for ImagePanel.
 *
 * Asserts: empty-state copy when no image exists, current-image
 * rendering when one does, regenerate button label flip, mutation
 * call shape on click.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ImagePanel } from "@/components/features/image-panel";

import type { GeneratedImage } from "@/lib/content/image-hooks";

const mocks = vi.hoisted(() => ({
  listResponse: { data: [] as GeneratedImage[] },
  generateMutate: vi.fn(),
}));

const sample = (overrides: Partial<GeneratedImage> = {}): GeneratedImage => ({
  id: overrides.id ?? "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
  content_piece_id: "11111111-1111-1111-1111-111111111111",
  style: "photorealistic",
  provider: "openai",
  model_id: "mock-image-v1",
  width: 1024,
  height: 1024,
  cdn_url: "http://localhost:8000/local-images/fake.png",
  image_prompt: "A test image",
  negative_prompt: null,
  cost_usd: "0",
  is_current: true,
  created_at: new Date().toISOString(),
  ...overrides,
});

vi.mock("@/lib/content/image-hooks", () => ({
  IMAGE_STYLES: [
    { value: "photorealistic", label: "Photorealistic" },
    { value: "illustration", label: "Illustration" },
    { value: "minimalist", label: "Minimalist" },
  ],
  useImageListQuery: () => ({
    data: mocks.listResponse,
    isPending: false,
    isError: false,
    error: null,
  }),
  useImageGenerateMutation: () => ({
    mutate: mocks.generateMutate,
    isPending: false,
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

describe("ImagePanel", () => {
  beforeEach(() => {
    mocks.generateMutate.mockReset();
    mocks.listResponse = { data: [] };
  });

  it("shows the empty-state message and a Generate button when no image exists", () => {
    renderWithProviders(<ImagePanel contentId="11111111-1111-1111-1111-111111111111" />);
    expect(screen.getByTestId("image-panel-empty")).toBeInTheDocument();
    expect(screen.getByTestId("image-generate")).toHaveTextContent("Generate image");
  });

  it("renders the current image and flips the button to Regenerate when one exists", () => {
    mocks.listResponse = { data: [sample()] };
    renderWithProviders(<ImagePanel contentId="11111111-1111-1111-1111-111111111111" />);
    expect(screen.getByTestId("image-panel-current")).toHaveAttribute(
      "src",
      "http://localhost:8000/local-images/fake.png",
    );
    expect(screen.getByTestId("image-generate")).toHaveTextContent("Regenerate");
  });

  it("renders the previous-versions strip when there is more than one image", () => {
    mocks.listResponse = {
      data: [
        sample({ id: "current" }),
        sample({ id: "prev-1", is_current: false }),
        sample({ id: "prev-2", is_current: false }),
      ],
    };
    renderWithProviders(<ImagePanel contentId="11111111-1111-1111-1111-111111111111" />);
    const history = screen.getByTestId("image-panel-history");
    expect(history.children.length).toBe(2);
  });

  it("calls the generate mutation with the selected style on click", async () => {
    const user = userEvent.setup();
    renderWithProviders(<ImagePanel contentId="11111111-1111-1111-1111-111111111111" />);
    await user.selectOptions(screen.getByTestId("image-style"), "illustration");
    await user.click(screen.getByTestId("image-generate"));
    expect(mocks.generateMutate).toHaveBeenCalledTimes(1);
    const [args] = mocks.generateMutate.mock.calls[0];
    expect(args).toEqual({
      contentId: "11111111-1111-1111-1111-111111111111",
      style: "illustration",
    });
  });

  it("disables the Generate button when the panel is marked disabled", () => {
    renderWithProviders(<ImagePanel contentId="11111111-1111-1111-1111-111111111111" disabled />);
    expect(screen.getByTestId("image-generate")).toBeDisabled();
  });
});

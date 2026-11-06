/**
 * Component test for MockModeBanner, run against the real useMetaQuery
 * hook with the API client mocked.
 *
 * Covers: the banner shows when GET /meta reports the mock provider,
 * and renders nothing for the other modes, while /meta is loading, and
 * when /meta fails (an older backend has no /meta). A failure is
 * retried once, not more.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { MockModeBanner } from "@/components/mock-mode-banner";
import { useMetaQuery, type MetaResponse } from "@/lib/meta/hooks";

const mocks = vi.hoisted(() => ({ get: vi.fn() }));

vi.mock("@/lib/api", () => ({
  api: { GET: mocks.get },
}));

const BANNER_COPY =
  "Mock mode: generated content is canned sample text, not written from your input. " +
  "Set AI_PROVIDER_MODE=openai and OPENAI_API_KEY on the backend for real generation.";

function metaAnswer(providerMode: MetaResponse["provider_mode"]) {
  return {
    data: { provider_mode: providerMode, app_version: "0.1.0" },
    error: undefined,
    response: { status: 200, statusText: "OK" },
  };
}

/**
 * Appears once /meta has answered, so "renders nothing" is checked
 * against the answer and not against the loading state.
 */
function MetaSettled() {
  const meta = useMetaQuery();
  return meta.isPending ? null : <span data-testid="meta-settled" />;
}

function renderBanner() {
  // retryDelay 0 lets the hook's one retry run without a real wait.
  const queryClient = new QueryClient({ defaultOptions: { queries: { retryDelay: 0 } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MockModeBanner />
      <MetaSettled />
    </QueryClientProvider>,
  );
}

describe("MockModeBanner", () => {
  beforeEach(() => {
    mocks.get.mockReset();
  });

  it("shows the banner when the backend runs the mock provider", async () => {
    mocks.get.mockResolvedValue(metaAnswer("mock"));
    renderBanner();

    expect(await screen.findByRole("status")).toHaveTextContent(BANNER_COPY);
    expect(mocks.get).toHaveBeenCalledWith("/meta");
  });

  it.each(["openai", "bedrock"] as const)("renders nothing in %s mode", async (mode) => {
    mocks.get.mockResolvedValue(metaAnswer(mode));
    renderBanner();

    await screen.findByTestId("meta-settled");
    expect(screen.queryByText(/Mock mode/)).not.toBeInTheDocument();
  });

  it("renders nothing while /meta is loading", () => {
    mocks.get.mockReturnValue(new Promise(() => {}));
    renderBanner();

    expect(screen.queryByTestId("meta-settled")).not.toBeInTheDocument();
    expect(screen.queryByText(/Mock mode/)).not.toBeInTheDocument();
  });

  it("renders nothing when /meta fails, and retries only once", async () => {
    mocks.get.mockResolvedValue({
      data: undefined,
      error: {
        error: { code: "NOT_FOUND", message: "Not Found", details: {} },
        meta: { request_id: null },
      },
      response: { status: 404, statusText: "Not Found" },
    });
    renderBanner();

    await screen.findByTestId("meta-settled");
    expect(screen.queryByText(/Mock mode/)).not.toBeInTheDocument();
    expect(mocks.get).toHaveBeenCalledTimes(2);
  });
});

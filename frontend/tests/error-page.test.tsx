/**
 * Component test for app/error.tsx, the route-level error boundary.
 *
 * Covers: "Try again" calls `reset`, the raw error message stays off
 * the screen, and the error is logged to the console instead.
 */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import RouteError from "@/app/error";

describe("RouteError", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("calls reset when Try again is clicked and never shows the raw message", async () => {
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
    const reset = vi.fn();
    const error = new Error("internal detail that must stay hidden");
    const user = userEvent.setup();

    render(<RouteError error={error} reset={reset} />);

    expect(screen.getByRole("heading", { name: "Something went wrong" })).toBeInTheDocument();
    expect(screen.queryByText(/internal detail/)).not.toBeInTheDocument();
    expect(consoleError).toHaveBeenCalledWith(error);

    await user.click(screen.getByRole("button", { name: "Try again" }));

    expect(reset).toHaveBeenCalledTimes(1);
  });
});

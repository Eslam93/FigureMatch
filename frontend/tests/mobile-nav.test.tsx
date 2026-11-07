/**
 * Component test for MobileNav, the menu that replaces the sidebar
 * below `md`.
 *
 * Covers: opening the panel with the shared nav items, closing on
 * Escape (focus goes back to the menu button, but focus outside the
 * menu stays put), closing when an item is selected, when the route
 * changes underneath it, and when focus or a press lands outside the
 * menu.
 */

import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { MobileNav } from "@/components/mobile-nav";
import { NAV_ITEMS } from "@/components/nav-links";

const router = vi.hoisted(() => ({ pathname: "/dashboard" }));

vi.mock("next/navigation", () => ({
  usePathname: () => router.pathname,
}));

// The real next/link needs the App Router context to navigate. A plain
// anchor is enough here: the tests only care that a click on an item
// reaches the component.
vi.mock("next/link", () => ({
  default: ({
    href,
    children,
    onClick,
    ...props
  }: React.AnchorHTMLAttributes<HTMLAnchorElement> & { href: string }) => (
    <a
      href={href}
      onClick={(event) => {
        event.preventDefault();
        onClick?.(event);
      }}
      {...props}
    >
      {children}
    </a>
  ),
}));

function menuButton() {
  return screen.getByRole("button", { name: "Menu" });
}

/** MobileNav followed by page content, the way the header sits above <main>. */
function renderWithPage() {
  render(
    <>
      <MobileNav />
      <main>
        <p>Page text</p>
        <button type="button">Page action</button>
      </main>
    </>,
  );
}

describe("MobileNav", () => {
  beforeEach(() => {
    router.pathname = "/dashboard";
  });

  it("opens a panel with every nav item and marks the active one", async () => {
    const user = userEvent.setup();
    render(<MobileNav />);
    expect(menuButton()).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("navigation")).not.toBeInTheDocument();

    await user.click(menuButton());

    expect(menuButton()).toHaveAttribute("aria-expanded", "true");
    const panel = screen.getByRole("navigation", { name: "Main" });
    expect(menuButton()).toHaveAttribute("aria-controls", panel.id);
    expect(within(panel).getAllByRole("link")).toHaveLength(NAV_ITEMS.length);
    expect(within(panel).getByRole("link", { name: "Dashboard" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(within(panel).getByRole("link", { name: "Generate" })).not.toHaveAttribute(
      "aria-current",
    );
  });

  it("closes on Escape and returns focus to the menu button", async () => {
    const user = userEvent.setup();
    render(<MobileNav />);
    await user.click(menuButton());
    await user.tab();
    expect(screen.getByRole("link", { name: "Dashboard" })).toHaveFocus();

    await user.keyboard("{Escape}");

    expect(menuButton()).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("navigation")).not.toBeInTheDocument();
    expect(menuButton()).toHaveFocus();
  });

  it("closes on Escape without moving focus that is outside the menu", async () => {
    const user = userEvent.setup();
    renderWithPage();
    const pageAction = screen.getByRole("button", { name: "Page action" });
    pageAction.focus();
    // fireEvent.click opens the menu without moving focus, so focus is
    // still on the page when Escape is pressed.
    fireEvent.click(menuButton());
    expect(menuButton()).toHaveAttribute("aria-expanded", "true");

    await user.keyboard("{Escape}");

    expect(menuButton()).toHaveAttribute("aria-expanded", "false");
    expect(pageAction).toHaveFocus();
  });

  it("closes when an item is selected", async () => {
    const user = userEvent.setup();
    render(<MobileNav />);
    await user.click(menuButton());

    await user.click(screen.getByRole("link", { name: "Generate" }));

    expect(menuButton()).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("navigation")).not.toBeInTheDocument();
  });

  it("closes when the route changes", async () => {
    const user = userEvent.setup();
    const { rerender } = render(<MobileNav />);
    await user.click(menuButton());
    expect(menuButton()).toHaveAttribute("aria-expanded", "true");

    router.pathname = "/generate";
    rerender(<MobileNav />);

    expect(menuButton()).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("navigation")).not.toBeInTheDocument();
  });

  it("closes when focus moves past the last item", async () => {
    const user = userEvent.setup();
    renderWithPage();
    await user.click(menuButton());
    const links = within(screen.getByRole("navigation", { name: "Main" })).getAllByRole("link");
    for (const link of links) {
      await user.tab();
      expect(link).toHaveFocus();
    }

    await user.tab();

    expect(screen.getByRole("button", { name: "Page action" })).toHaveFocus();
    expect(menuButton()).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("navigation")).not.toBeInTheDocument();
  });

  it("closes on a press outside the menu but not inside it", async () => {
    const user = userEvent.setup();
    renderWithPage();
    await user.click(menuButton());

    await user.click(screen.getByRole("navigation", { name: "Main" }));
    expect(menuButton()).toHaveAttribute("aria-expanded", "true");

    await user.click(screen.getByText("Page text"));

    expect(menuButton()).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("navigation")).not.toBeInTheDocument();
  });
});

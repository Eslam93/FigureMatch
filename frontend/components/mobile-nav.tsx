"use client";

import { Menu, X } from "lucide-react";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { NavLinks } from "@/components/nav-links";
import { Button } from "@/components/ui/v2";

const PANEL_ID = "mobile-nav-panel";

/**
 * Navigation for screens below `md`, where the sidebar is hidden.
 *
 * The menu button sits in the protected header and toggles a panel with
 * the same items as the sidebar. The panel covers the top of the page,
 * so it closes as soon as a press or focus lands outside the menu. It
 * also closes on Escape, when an item is selected and whenever the
 * route changes.
 */
export function MobileNav() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const [lastPathname, setLastPathname] = useState(pathname);
  const wrapperRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);

  // Close on any route change (back/forward, redirects). Adjusting the
  // state while rendering, instead of in an effect, means the new page
  // never paints with the stale panel still open.
  if (pathname !== lastPathname) {
    setLastPathname(pathname);
    setOpen(false);
  }

  useEffect(() => {
    if (!open) return;
    // The panel sits on top of the page. Close it once a press or focus
    // lands outside the menu, so it never hides the control in use.
    const closeIfOutside = (event: Event) => {
      if (event.target instanceof Element && !wrapperRef.current?.contains(event.target)) {
        setOpen(false);
      }
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      setOpen(false);
      // Only take focus back from inside the menu; focus elsewhere stays put.
      if (wrapperRef.current?.contains(document.activeElement)) {
        buttonRef.current?.focus();
      }
    };
    document.addEventListener("pointerdown", closeIfOutside);
    document.addEventListener("focusin", closeIfOutside);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", closeIfOutside);
      document.removeEventListener("focusin", closeIfOutside);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  return (
    <div ref={wrapperRef} className="md:hidden">
      <Button
        ref={buttonRef}
        type="button"
        variant="ghost"
        size="icon"
        aria-label="Menu"
        aria-expanded={open}
        aria-controls={PANEL_ID}
        onClick={() => setOpen((current) => !current)}
      >
        {open ? <X className="h-5 w-5" aria-hidden /> : <Menu className="h-5 w-5" aria-hidden />}
      </Button>
      <nav
        id={PANEL_ID}
        aria-label="Main"
        hidden={!open}
        className="absolute inset-x-0 top-full z-40 space-y-1 border-b bg-card p-4 shadow-elev-md"
      >
        <NavLinks onNavigate={() => setOpen(false)} />
      </nav>
    </div>
  );
}

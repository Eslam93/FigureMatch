"use client";

import { LayoutDashboard, Mic, PenSquare, Settings, Sparkles } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { Route } from "next";

import { cn } from "@/lib/utils";

/**
 * Nav items for the protected app, shared by the desktop sidebar and
 * the mobile menu. Links use route literals so typedRoutes catches
 * future typos.
 */
export const NAV_ITEMS: ReadonlyArray<{
  href: Route;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
}> = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/generate", label: "Generate", icon: Sparkles },
  { href: "/improve", label: "Improve", icon: PenSquare },
  { href: "/brand-voices", label: "Brand voices", icon: Mic },
  { href: "/settings", label: "Settings", icon: Settings },
];

interface NavLinksProps {
  /** Runs when an item is selected, e.g. to close the mobile menu. */
  onNavigate?: () => void;
}

/**
 * Renders NAV_ITEMS as links. `usePathname` highlights the active item
 * (and marks it `aria-current="page"`) so the user always knows where
 * they are.
 */
export function NavLinks({ onNavigate }: NavLinksProps) {
  const pathname = usePathname();
  return (
    <>
      {NAV_ITEMS.map((item) => {
        const Icon = item.icon;
        const active = pathname === item.href;
        return (
          <Link
            key={item.href}
            href={item.href}
            onClick={onNavigate}
            aria-current={active ? "page" : undefined}
            className={cn(
              "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
              active
                ? "bg-accent text-accent-foreground"
                : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
            )}
          >
            <Icon className="h-4 w-4" />
            {item.label}
          </Link>
        );
      })}
    </>
  );
}

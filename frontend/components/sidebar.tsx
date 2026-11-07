"use client";

import Link from "next/link";

import { NavLinks } from "@/components/nav-links";

/**
 * Desktop sidebar for the protected layout. Hidden below `md`, where
 * MobileNav offers the same items from the header.
 */
export function Sidebar() {
  return (
    <aside className="hidden w-60 shrink-0 border-r bg-card md:flex md:flex-col">
      <div className="border-b px-6 py-4">
        <Link href="/dashboard" className="text-lg font-bold">
          MagnaCMS
        </Link>
      </div>
      <nav className="flex-1 space-y-1 p-4">
        <NavLinks />
      </nav>
    </aside>
  );
}

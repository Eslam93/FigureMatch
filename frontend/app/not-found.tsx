"use client";

import Link from "next/link";

import { buttonVariants } from "@/components/ui/v2";

/**
 * 404 page for unknown URLs; the static export writes it to
 * out/404.html. It is a client component because `buttonVariants`
 * lives in the v2 Button module, which is client-only.
 */
export default function NotFound() {
  return (
    <main className="container flex min-h-screen flex-col items-center justify-center gap-4 py-12 text-center">
      <p className="font-mono text-sm text-muted-foreground">404</p>
      <h1 className="text-3xl font-bold tracking-tight">Page not found</h1>
      <p className="max-w-md text-muted-foreground">
        The page you are looking for does not exist or has moved.
      </p>
      <Link href="/" className={buttonVariants({ variant: "brand" })}>
        Back to home
      </Link>
    </main>
  );
}

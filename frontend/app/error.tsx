"use client";

import { useEffect } from "react";

import { Button } from "@/components/ui/v2";

interface RouteErrorProps {
  error: Error & { digest?: string };
  reset: () => void;
}

/**
 * Error boundary for every route below the root layout. The raw error
 * goes to the console only: its message can carry internals, so the
 * user sees a generic message and a way to retry.
 */
export default function RouteError({ error, reset }: RouteErrorProps) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <main className="container flex min-h-screen flex-col items-center justify-center gap-4 py-12 text-center">
      <h1 className="text-2xl font-bold tracking-tight">Something went wrong</h1>
      <p className="max-w-md text-muted-foreground">
        An unexpected error stopped this page from loading. Try again, or reload the page if it
        keeps happening.
      </p>
      <Button variant="brand" onClick={() => reset()}>
        Try again
      </Button>
    </main>
  );
}

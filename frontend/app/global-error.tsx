"use client";

import "./globals.css";

import { useEffect } from "react";

import { Button } from "@/components/ui/v2";

interface GlobalErrorProps {
  error: Error & { digest?: string };
  reset: () => void;
}

/**
 * Last-resort boundary for errors thrown by the root layout itself. It
 * replaces that layout, so it renders its own <html> and <body>.
 * Everything below the root layout is handled by app/error.tsx.
 */
export default function GlobalError({ error, reset }: GlobalErrorProps) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <html lang="en">
      <body className="flex min-h-screen flex-col items-center justify-center gap-4 bg-background p-6 text-center text-foreground antialiased">
        <h1 className="text-2xl font-bold tracking-tight">Something went wrong</h1>
        <p className="max-w-md text-muted-foreground">
          MagnaCMS hit an unexpected error. Try again, or reload the page.
        </p>
        <Button variant="brand" onClick={() => reset()}>
          Try again
        </Button>
      </body>
    </html>
  );
}

import Link from "next/link";

import { Button } from "@/components/ui/button";

export default function LandingPage() {
  return (
    <main className="container flex min-h-screen flex-col items-center justify-center gap-6 py-12 text-center">
      <h1 className="text-4xl font-bold tracking-tight md:text-6xl">FigureMatch</h1>
      <p className="max-w-2xl text-lg text-muted-foreground">
        AI Content Marketing Suite. Generate, manage, and improve marketing content with AI — every
        piece paired with an AI-generated image in one flow.
      </p>
      <div className="flex gap-4">
        <Button asChild>
          <Link href="/login">Sign in</Link>
        </Button>
        <Button asChild variant="outline">
          <Link href="/register">Create account</Link>
        </Button>
      </div>
    </main>
  );
}

"use client";

import { MobileNav } from "@/components/mobile-nav";
import { Sidebar } from "@/components/sidebar";
import { UserMenu } from "@/components/user-menu";
import { useAuthGuard } from "@/lib/auth/use-auth-guard";

/**
 * Protected route shell.
 *
 * Auth guard runs on mount: calls /auth/me (with the API client's
 * transparent refresh-and-retry on 401). If the user is
 * unauthenticated, redirects to /login. While the guard query is
 * pending, renders a minimal loading state; when it resolves,
 * renders the full app shell (sidebar + top nav + content). Below `md`
 * the sidebar is hidden and the header's menu button takes over.
 *
 * Routes under (protected)/* share this layout. Public routes
 * (landing, /login, /register) live outside it.
 */
export default function ProtectedLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  const me = useAuthGuard();

  if (me.isPending) {
    return (
      <main className="flex min-h-screen items-center justify-center">
        <div className="text-sm text-muted-foreground">Loading…</div>
      </main>
    );
  }

  if (me.isError || !me.data) {
    // Redirect already in flight from useAuthGuard's effect. Render
    // nothing to avoid a flash of auth-restricted content.
    return null;
  }

  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <div className="flex flex-1 flex-col">
        <header className="relative flex items-center justify-between border-b bg-card px-6 py-3 md:justify-end">
          <MobileNav />
          <UserMenu email={me.data.email} fullName={me.data.full_name} />
        </header>
        <main className="flex-1 overflow-auto p-6">{children}</main>
      </div>
    </div>
  );
}

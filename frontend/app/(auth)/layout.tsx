// SPDX-FileCopyrightText: 2026 Eslam Hamed
//
// SPDX-License-Identifier: MIT

/**
 * Layout for the (auth) route group. Centered card on a muted
 * background, used by both /login and /register. Keeps the auth
 * shell visually distinct from the protected app shell.
 */

export default function AuthLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <main className="flex min-h-screen items-center justify-center bg-muted/30 px-4 py-12">
      <div className="w-full max-w-md rounded-lg border bg-card p-8 shadow-sm">{children}</div>
    </main>
  );
}

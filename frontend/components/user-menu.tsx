// SPDX-FileCopyrightText: 2026 Eslam Hamed
//
// SPDX-License-Identifier: MIT

"use client";

import { LogOut } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useLogoutMutation } from "@/lib/auth/hooks";

interface UserMenuProps {
  email: string;
  fullName: string;
}

/**
 * Top-right user identity + logout button.
 *
 * No dropdown wrapper yet — a full shadcn DropdownMenu lands when
 * we have more than one action to expose (Settings, theme switcher,
 * account, …). For now the email + a sign-out button is enough.
 */
export function UserMenu({ email, fullName }: UserMenuProps) {
  const logout = useLogoutMutation();

  return (
    <div className="flex items-center gap-3">
      <div className="text-right">
        <p className="text-sm font-medium">{fullName}</p>
        <p className="text-xs text-muted-foreground">{email}</p>
      </div>
      <Button
        variant="ghost"
        size="icon"
        onClick={() => logout.mutate()}
        disabled={logout.isPending}
        aria-label="Sign out"
      >
        <LogOut className="h-4 w-4" />
      </Button>
    </div>
  );
}

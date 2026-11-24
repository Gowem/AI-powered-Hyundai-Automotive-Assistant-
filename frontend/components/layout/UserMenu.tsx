"use client";

import { useQueryClient } from "@tanstack/react-query";
import { ChevronsUpDown, LogOut } from "lucide-react";
import { useRouter } from "next/navigation";

import { ThemeToggle } from "@/components/layout/ThemeToggle";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useMe } from "@/hooks/queries";
import { api } from "@/lib/api";

export function UserMenu() {
  const { data: me } = useMe();
  const qc = useQueryClient();
  const router = useRouter();
  const initial = (me?.full_name || me?.email || "?").charAt(0).toUpperCase();

  async function logout() {
    try {
      await api("/api/auth/logout", { method: "POST" });
    } finally {
      qc.clear();
      router.replace("/login");
      router.refresh();
    }
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger className="hover:bg-accent focus-visible:ring-ring/50 flex w-full items-center gap-2.5 rounded-lg p-2 text-left outline-none focus-visible:ring-[3px]">
        <span className="bg-primary/10 text-primary flex size-8 shrink-0 items-center justify-center rounded-full text-sm font-semibold">
          {initial}
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm font-medium">{me?.full_name || "Account"}</span>
          <span className="text-muted-foreground block truncate text-xs">{me?.email ?? "…"}</span>
        </span>
        <ChevronsUpDown className="text-muted-foreground size-4" />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" side="top" className="w-60">
        <DropdownMenuLabel className="truncate font-normal">
          <span className="text-muted-foreground block text-xs">Signed in as</span>
          <span className="block truncate">{me?.email}</span>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <div className="flex items-center justify-between px-2 py-1.5 text-sm">
          <span>Theme</span>
          <ThemeToggle />
        </div>
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={logout}>
          <LogOut /> Log out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

"use client";

import { FileText, MessageSquare, Plus } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { Brand, Disclaimer } from "@/components/layout/Brand";
import { ConversationList } from "@/components/layout/ConversationList";
import { UserMenu } from "@/components/layout/UserMenu";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/chat", label: "Chat", icon: MessageSquare },
  { href: "/documents", label: "Documents", icon: FileText },
];

export function SidebarContent({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  return (
    <div className="flex h-full flex-col">
      <div className="px-4 pt-4 pb-3">
        <Link href="/chat" onClick={onNavigate} aria-label="Hyundai Assistant home">
          <Brand />
        </Link>
      </div>
      <div className="px-3">
        <Button asChild className="w-full justify-start">
          <Link href="/chat" onClick={onNavigate}>
            <Plus /> New chat
          </Link>
        </Button>
      </div>
      <nav className="mt-4 space-y-0.5 px-3" aria-label="Main">
        {NAV.map(({ href, label, icon: Icon }) => {
          const active = pathname === href || pathname.startsWith(`${href}/`);
          return (
            <Link
              key={href}
              href={href}
              onClick={onNavigate}
              aria-current={active ? "page" : undefined}
              className={cn(
                "hover:bg-accent flex items-center gap-2.5 rounded-md px-2.5 py-2 text-sm font-medium",
                active && "bg-accent text-foreground",
                !active && "text-muted-foreground",
              )}
            >
              <Icon className="size-4" /> {label}
            </Link>
          );
        })}
      </nav>
      <div className="text-muted-foreground mt-5 px-5 pb-1.5 text-[11px] font-semibold tracking-wider uppercase">
        Recent chats
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto px-3 pb-3">
        <ConversationList onNavigate={onNavigate} />
      </div>
      <div className="border-t p-3">
        <UserMenu />
        <Disclaimer className="mt-2 px-2" />
      </div>
    </div>
  );
}

export function Sidebar() {
  return (
    <aside className="bg-sidebar hidden w-72 shrink-0 border-r lg:block" aria-label="Sidebar">
      <div className="sticky top-0 h-dvh">
        <SidebarContent />
      </div>
    </aside>
  );
}

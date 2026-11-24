"use client";

import { Loader2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { MobileNav } from "@/components/layout/MobileNav";
import { Sidebar } from "@/components/layout/Sidebar";
import { useMe } from "@/hooks/queries";
import { ApiError } from "@/lib/api";

export function AppShell({ children }: { children: React.ReactNode }) {
  const { data, error, isLoading } = useMe();
  const router = useRouter();

  useEffect(() => {
    if (error instanceof ApiError && error.status === 401) {
      const next = encodeURIComponent(window.location.pathname);
      // the cookie may be stale: log out on the server to clear it, then go to login
      fetch("/api/auth/logout", { method: "POST", credentials: "include" }).finally(() =>
        router.replace(`/login?next=${next}`),
      );
    }
  }, [error, router]);

  if (error && !(error instanceof ApiError && error.status === 401)) {
    return (
      <div className="flex min-h-dvh flex-col items-center justify-center gap-3 p-6 text-center">
        <p className="font-medium">Could not reach the server.</p>
        <p className="text-muted-foreground max-w-sm text-sm">
          The backend may be waking up (free hosting can take ~50 seconds on the first request).
        </p>
        <button className="text-primary text-sm font-medium underline" onClick={() => window.location.reload()}>
          Try again
        </button>
      </div>
    );
  }

  if (isLoading || !data) {
    return (
      <div className="flex min-h-dvh items-center justify-center" aria-busy="true">
        <Loader2 className="text-muted-foreground size-6 animate-spin" aria-label="Loading" />
      </div>
    );
  }

  return (
    <div className="flex min-h-dvh">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <MobileNav />
        {children}
      </div>
    </div>
  );
}

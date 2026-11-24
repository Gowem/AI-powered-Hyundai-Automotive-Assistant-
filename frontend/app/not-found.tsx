import { Car } from "lucide-react";
import Link from "next/link";

import { Button } from "@/components/ui/button";

export default function NotFound() {
  return (
    <main className="flex min-h-dvh flex-col items-center justify-center gap-4 p-6 text-center">
      <div className="bg-primary/10 text-primary flex size-14 items-center justify-center rounded-2xl">
        <Car className="size-7" />
      </div>
      <h1 className="text-2xl font-semibold">Page not found</h1>
      <p className="text-muted-foreground max-w-sm text-sm">
        The page you are looking for doesn&apos;t exist or may have been moved.
      </p>
      <Button asChild>
        <Link href="/chat">Back to chat</Link>
      </Button>
    </main>
  );
}

import { Car } from "lucide-react";

import { cn } from "@/lib/utils";

export function Brand({ className }: { className?: string }) {
  return (
    <div className={cn("flex items-center gap-2.5", className)}>
      <div className="bg-brand flex size-8 items-center justify-center rounded-lg text-white shadow-sm dark:text-[#0f1726]">
        <Car className="size-4.5" aria-hidden />
      </div>
      <span className="text-[15px] font-semibold tracking-tight">Hyundai Assistant</span>
    </div>
  );
}

export function Disclaimer({ className }: { className?: string }) {
  return (
    <p className={cn("text-muted-foreground text-[11px] leading-snug", className)}>
      Unofficial demo. Answers are generated from uploaded brochures.
    </p>
  );
}

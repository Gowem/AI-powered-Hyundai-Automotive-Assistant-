import { Check, Loader2 } from "lucide-react";

import type { StreamStage } from "@/lib/types";
import { cn } from "@/lib/utils";

const STAGES: { key: StreamStage; label: string }[] = [
  { key: "understanding", label: "Understanding your question…" },
  { key: "retrieving", label: "Searching brochures…" },
  { key: "writing", label: "Writing answer…" },
];

export function StreamingIndicator({ stage }: { stage: StreamStage }) {
  const idx = STAGES.findIndex((s) => s.key === stage);
  return (
    <ol className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs" aria-label="Progress">
      {STAGES.map((s, i) => (
        <li
          key={s.key}
          className={cn(
            "flex items-center gap-1.5",
            i < idx && "text-muted-foreground",
            i === idx && "text-foreground font-medium",
            i > idx && "text-muted-foreground/50",
          )}
        >
          {i < idx ? (
            <Check className="size-3.5 text-emerald-600" />
          ) : i === idx ? (
            <Loader2 className="text-primary size-3.5 animate-spin" />
          ) : (
            <span className="size-3.5 rounded-full border" />
          )}
          {s.label}
        </li>
      ))}
    </ol>
  );
}

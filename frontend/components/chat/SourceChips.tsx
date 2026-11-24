"use client";

import { FileText } from "lucide-react";

import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { Source } from "@/lib/types";
import { cn } from "@/lib/utils";

import { openSourcePdf } from "./openSource";

export function SourceChips({
  sources,
  messageId,
  highlighted,
}: {
  sources: Source[];
  messageId: string;
  highlighted: number | null;
}) {
  if (!sources.length) return null;
  return (
    <div className="mt-3 border-t pt-3">
      <p className="text-muted-foreground mb-2 text-xs font-medium">Sources</p>
      <ul className="flex flex-wrap gap-1.5">
        {sources.map((s) => (
          <li key={s.n} id={`src-${messageId}-${s.n}`}>
            <Tooltip>
              <TooltipTrigger asChild>
                <button
                  type="button"
                  onClick={() => openSourcePdf(s.document_id, s.page)}
                  className={cn(
                    "bg-muted/60 hover:bg-accent focus-visible:ring-ring/50 inline-flex max-w-[260px] items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs outline-none focus-visible:ring-[3px]",
                    highlighted === s.n && "ring-primary bg-primary/10 ring-2",
                  )}
                  aria-label={`Open source ${s.n}: ${s.document_name}, page ${s.page}`}
                >
                  <span className="bg-primary text-primary-foreground flex size-4 items-center justify-center rounded-full text-[10px] font-semibold">
                    {s.n}
                  </span>
                  <FileText className="text-muted-foreground size-3 shrink-0" />
                  <span className="truncate">
                    {s.document_name} · p.{s.page}
                  </span>
                </button>
              </TooltipTrigger>
              <TooltipContent side="top" className="max-w-sm">
                {s.snippet}…
              </TooltipContent>
            </Tooltip>
          </li>
        ))}
      </ul>
    </div>
  );
}

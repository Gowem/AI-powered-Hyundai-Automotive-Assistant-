"use client";

import { Car, Check, Copy, RefreshCw } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { ChatMessage, StreamStage } from "@/lib/types";

import { Markdown } from "./Markdown";
import { SourceChips } from "./SourceChips";
import { StreamingIndicator } from "./StreamingIndicator";

export type UIMessage = ChatMessage & { streaming?: boolean; stage?: StreamStage; error?: boolean };

export function MessageBubble({
  message,
  isLast,
  onRegenerate,
  busy,
}: {
  message: UIMessage;
  isLast: boolean;
  onRegenerate?: () => void;
  busy: boolean;
}) {
  const [highlight, setHighlight] = useState<number | null>(null);
  const [copied, setCopied] = useState(false);

  if (message.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="bg-primary text-primary-foreground max-w-[85%] rounded-2xl rounded-br-md px-4 py-2.5 text-sm whitespace-pre-wrap shadow-xs sm:max-w-[75%]">
          {message.content}
        </div>
      </div>
    );
  }

  function onCite(n: number) {
    const el = document.getElementById(`src-${message.id}-${n}`);
    el?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    setHighlight(n);
    window.setTimeout(() => setHighlight(null), 1800);
  }

  async function copy() {
    try {
      await navigator.clipboard.writeText(message.content);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      toast.error("Could not copy to clipboard");
    }
  }

  const waiting = message.streaming && !message.content;
  return (
    <div className="flex gap-3">
      <div className="bg-brand mt-0.5 hidden size-7 shrink-0 items-center justify-center rounded-lg text-white sm:flex dark:text-[#0f1726]">
        <Car className="size-3.5" aria-hidden />
      </div>
      <div className="bg-card min-w-0 flex-1 rounded-2xl border px-4 py-3 shadow-xs sm:px-5">
        {message.streaming && message.stage && (
          <div className={waiting ? "" : "mb-2 border-b pb-2"}>
            <StreamingIndicator stage={message.stage} />
          </div>
        )}
        {message.content && (
          <div aria-live={message.streaming ? "polite" : undefined} aria-busy={message.streaming}>
            <Markdown content={message.content} onCite={onCite} />
          </div>
        )}
        {message.error && (
          <p className="text-destructive mt-1 text-sm" role="alert">
            {message.content ? "" : "The assistant could not answer. "}Please try again.
          </p>
        )}
        {!message.streaming && message.sources && (
          <SourceChips sources={message.sources} messageId={message.id} highlighted={highlight} />
        )}
        {!message.streaming && message.content && (
          <div className="text-muted-foreground mt-2 flex gap-1">
            <Tooltip>
              <TooltipTrigger asChild>
                <Button variant="ghost" size="icon-sm" onClick={copy} aria-label="Copy answer">
                  {copied ? <Check className="text-emerald-600" /> : <Copy />}
                </Button>
              </TooltipTrigger>
              <TooltipContent>Copy answer</TooltipContent>
            </Tooltip>
            {isLast && onRegenerate && (
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button variant="ghost" size="icon-sm" onClick={onRegenerate} disabled={busy} aria-label="Regenerate">
                    <RefreshCw />
                  </Button>
                </TooltipTrigger>
                <TooltipContent>Regenerate answer</TooltipContent>
              </Tooltip>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

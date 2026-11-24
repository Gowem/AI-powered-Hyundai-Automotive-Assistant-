"use client";

import { ArrowUp, Square } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const MAX = 2000;

export function Composer({
  onSend,
  onStop,
  busy,
  initialFocus,
}: {
  onSend: (text: string) => void;
  onStop: () => void;
  busy: boolean;
  initialFocus?: boolean;
}) {
  const [value, setValue] = useState("");
  const ref = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (initialFocus) ref.current?.focus();
  }, [initialFocus]);

  function submit() {
    const text = value.trim();
    if (!text || busy || text.length > MAX) return;
    onSend(text);
    setValue("");
  }

  const over = value.length > MAX;
  return (
    <div className="bg-background/95 sticky bottom-0 z-20 border-t backdrop-blur supports-[backdrop-filter]:bg-background/80">
      <form
        className="mx-auto w-full max-w-3xl px-3 py-3 sm:px-6"
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
      >
        <div
          className={cn(
            "bg-card focus-within:border-ring focus-within:ring-ring/30 flex items-end gap-2 rounded-2xl border p-2 shadow-sm focus-within:ring-[3px]",
            over && "border-destructive",
          )}
        >
          <label htmlFor="composer" className="sr-only">
            Ask about Hyundai vehicles
          </label>
          <textarea
            id="composer"
            ref={ref}
            value={value}
            rows={1}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                e.preventDefault();
                submit();
              }
            }}
            placeholder="Ask about features, specs, variants or comparisons…"
            className="placeholder:text-muted-foreground max-h-48 min-h-10 flex-1 resize-none bg-transparent px-2 py-2 text-[15px] outline-none field-sizing-content sm:text-sm"
          />
          {busy ? (
            <Button type="button" size="icon" variant="secondary" onClick={onStop} aria-label="Stop generating">
              <Square className="fill-current" />
            </Button>
          ) : (
            <Button type="submit" size="icon" disabled={!value.trim() || over} aria-label="Send message">
              <ArrowUp />
            </Button>
          )}
        </div>
        <div className="text-muted-foreground mt-1.5 flex justify-between px-1 text-[11px]">
          <span className="hidden sm:inline">Enter to send · Shift+Enter for a new line</span>
          <span className={cn("ml-auto", over && "text-destructive font-medium")}>
            {value.length > MAX * 0.8 ? `${value.length}/${MAX}` : ""}
          </span>
        </div>
      </form>
    </div>
  );
}

"use client";

import { useEffect, useRef } from "react";

import { MessageBubble, type UIMessage } from "./MessageBubble";

export function MessageList({
  messages,
  busy,
  onRegenerate,
}: {
  messages: UIMessage[];
  busy: boolean;
  onRegenerate: () => void;
}) {
  const bottom = useRef<HTMLDivElement>(null);
  const last = messages[messages.length - 1];
  const contentLength = last?.content.length ?? 0;

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: busy ? "auto" : "smooth", block: "end" });
  }, [messages.length, contentLength, busy]);

  const lastAssistant = [...messages].reverse().find((m) => m.role === "assistant");
  return (
    <div className="mx-auto w-full max-w-3xl space-y-5 px-3 py-6 sm:px-6">
      {messages.map((m) => (
        <MessageBubble
          key={m.id}
          message={m}
          isLast={m.id === lastAssistant?.id && m.id === last?.id}
          onRegenerate={onRegenerate}
          busy={busy}
        />
      ))}
      <div ref={bottom} />
    </div>
  );
}

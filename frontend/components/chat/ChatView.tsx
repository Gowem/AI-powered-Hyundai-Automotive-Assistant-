"use client";

import { useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Car, Loader2 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { Skeleton } from "@/components/ui/skeleton";
import { useConversation, useDocuments } from "@/hooks/queries";
import { api, ApiError, parseError, redirectToLogin } from "@/lib/api";
import { readSSE } from "@/lib/sse";
import type { ChatAnswer, Conversation, ConversationDetail, Source, StreamStage } from "@/lib/types";

import { Composer } from "./Composer";
import type { UIMessage } from "./MessageBubble";
import { MessageList } from "./MessageList";
import { SuggestedPrompts } from "./SuggestedPrompts";

const STREAM_PREF = "hyundai.streaming";
const tempId = () => `tmp-${Math.random().toString(36).slice(2)}`;

type Done = { message_id: string; user_message_id: string; conversation_title: string; content: string };

export function ChatView({ conversationId }: { conversationId: string | null }) {
  const qc = useQueryClient();
  const router = useRouter();
  const { data: conv, isLoading, error } = useConversation(conversationId);
  const { data: docs } = useDocuments();
  const [messages, setMessages] = useState<UIMessage[]>([]);
  const [busy, setBusy] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const convIdRef = useRef<string | null>(conversationId);

  useEffect(() => {
    if (conv && !busy) setMessages(conv.messages);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conv]);

  useEffect(() => () => abortRef.current?.abort(), []);

  const patchLast = useCallback((patch: Partial<UIMessage> | ((m: UIMessage) => Partial<UIMessage>)) => {
    setMessages((prev) => {
      const copy = [...prev];
      const last = copy[copy.length - 1];
      if (!last) return prev;
      copy[copy.length - 1] = { ...last, ...(typeof patch === "function" ? patch(last) : patch) };
      return copy;
    });
  }, []);

  async function sendNonStream(id: string, content: string, signal: AbortSignal, regenerate: boolean) {
    const ans = await api<ChatAnswer>(`/api/chat/conversations/${id}/messages?stream=false`, {
      method: "POST",
      json: { content, regenerate },
      signal,
    });
    return {
      done: {
        message_id: ans.message_id,
        user_message_id: ans.user_message_id,
        conversation_title: ans.conversation_title,
        content: ans.content,
      },
      sources: ans.sources,
    };
  }

  async function sendStream(id: string, content: string, signal: AbortSignal, regenerate: boolean) {
    const res = await fetch(`/api/chat/conversations/${id}/messages`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
      body: JSON.stringify({ content, regenerate }),
      signal,
    });
    if (res.status === 401) redirectToLogin();
    if (!res.ok) throw new ApiError(res.status, await parseError(res));
    if (!res.headers.get("content-type")?.includes("text/event-stream")) throw new Error("stream-unsupported");
    let done: Done | null = null;
    let sources: Source[] = [];
    let text = "";
    for await (const ev of readSSE(res, signal)) {
      const data = ev.data as Record<string, unknown>;
      if (ev.event === "status") patchLast({ stage: data.stage as StreamStage });
      else if (ev.event === "token") {
        text += String(data.text ?? "");
        patchLast({ content: text, stage: "writing" });
      } else if (ev.event === "sources") sources = (data.sources as Source[]) ?? [];
      else if (ev.event === "done") done = data as unknown as Done;
      else if (ev.event === "error") throw new ApiError(500, String(data.message ?? "Generation failed"));
    }
    if (!done) throw new Error("stream-incomplete");
    return { done, sources };
  }

  async function run(content: string, regenerate = false) {
    if (busy) return;
    setBusy(true);
    const controller = new AbortController();
    abortRef.current = controller;
    const assistantId = tempId();
    setMessages((prev) => {
      let base = prev;
      if (regenerate && base[base.length - 1]?.role === "assistant") base = base.slice(0, -1);
      const next: UIMessage[] = regenerate
        ? base
        : [...base, { id: tempId(), role: "user", content, sources: null, intent: null, created_at: new Date().toISOString() }];
      return [
        ...next,
        {
          id: assistantId,
          role: "assistant",
          content: "",
          sources: null,
          intent: null,
          created_at: new Date().toISOString(),
          streaming: true,
          stage: "understanding",
        },
      ];
    });

    let id = convIdRef.current;
    const isNew = !id;
    try {
      if (!id) {
        const created = await api<Conversation>("/api/chat/conversations", { method: "POST", json: {} });
        id = created.id;
        convIdRef.current = id;
      }
      let result: { done: Done; sources: Source[] };
      const preferStream = typeof window !== "undefined" && localStorage.getItem(STREAM_PREF) !== "off";
      if (preferStream) {
        try {
          result = await sendStream(id, content, controller.signal, regenerate);
        } catch (err) {
          if (controller.signal.aborted || (err instanceof ApiError && err.status !== 500)) throw err;
          // Streaming failed (e.g. a buffering proxy). Fall back to the JSON endpoint and remember it.
          console.warn("Streaming failed, falling back to non-stream mode", err);
          if (err instanceof Error && err.message === "stream-unsupported") localStorage.setItem(STREAM_PREF, "off");
          patchLast({ content: "", stage: "writing" });
          result = await sendNonStream(id, content, controller.signal, true);
        }
      } else {
        result = await sendNonStream(id, content, controller.signal, regenerate);
      }
      const { done, sources } = result;
      setMessages((prev) => {
        const copy = [...prev];
        const last = copy[copy.length - 1];
        copy[copy.length - 1] = {
          ...last,
          id: done.message_id,
          content: done.content,
          sources,
          streaming: false,
          stage: undefined,
        };
        const userIdx = copy.length - 2;
        if (copy[userIdx]?.role === "user") copy[userIdx] = { ...copy[userIdx], id: done.user_message_id };
        // keep the cache in sync so navigating to /chat/[id] shows the messages instantly
        qc.setQueryData<ConversationDetail>(["conversation", id], (old) => ({
          id: id!,
          title: done.conversation_title,
          created_at: old?.created_at ?? new Date().toISOString(),
          updated_at: new Date().toISOString(),
          messages: copy.map(({ streaming: _s, stage: _st, error: _e, ...m }) => m),
        }));
        return copy;
      });
      qc.invalidateQueries({ queryKey: ["conversations"] });
      if (isNew) router.replace(`/chat/${id}`);
    } catch (err) {
      if (controller.signal.aborted) {
        patchLast((m) => ({
          streaming: false,
          stage: undefined,
          content: m.content ? `${m.content}\n\n*Stopped.*` : "*Stopped.*",
        }));
      } else {
        const msg = err instanceof Error ? err.message : "Something went wrong";
        toast.error(msg);
        patchLast({ streaming: false, stage: undefined, error: true });
      }
      if (id) {
        qc.invalidateQueries({ queryKey: ["conversations"] });
        if (isNew) {
          qc.removeQueries({ queryKey: ["conversation", id] });
          router.replace(`/chat/${id}`);
        }
      }
    } finally {
      setBusy(false);
      abortRef.current = null;
    }
  }

  function regenerate() {
    const lastUser = [...messages].reverse().find((m) => m.role === "user");
    if (lastUser) run(lastUser.content, true);
  }

  const noDocs = docs && docs.ready_count === 0;
  const processing = docs?.items.some((d) => d.status === "queued" || d.status === "processing");

  if (conversationId && isLoading) {
    return (
      <div className="mx-auto w-full max-w-3xl space-y-4 px-6 py-8">
        <Skeleton className="ml-auto h-10 w-2/3" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }
  if (conversationId && error) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-3 p-6 text-center">
        <p className="font-medium">Conversation not found</p>
        <Link href="/chat" className="text-primary text-sm underline">
          Start a new chat
        </Link>
      </div>
    );
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      {noDocs && (
        <div className="border-b bg-amber-50 px-4 py-2.5 text-sm text-amber-900 dark:bg-amber-500/10 dark:text-amber-200">
          <div className="mx-auto flex max-w-3xl items-center gap-2">
            <AlertTriangle className="size-4 shrink-0" />
            <span>
              {processing ? "Brochures are still being processed. " : "No brochures indexed yet. "}
              <Link href="/documents" className="font-medium underline underline-offset-2">
                {processing ? "Check progress" : "Upload brochures to start."}
              </Link>
            </span>
            {processing && <Loader2 className="size-3.5 animate-spin" />}
          </div>
        </div>
      )}
      <main className="flex-1">
        {messages.length === 0 ? (
          <div className="mx-auto flex w-full max-w-3xl flex-col px-4 pt-10 pb-6 sm:px-6 sm:pt-16">
            <div className="bg-brand mb-5 flex size-12 items-center justify-center rounded-2xl text-white shadow-sm dark:text-[#0f1726]">
              <Car className="size-6" />
            </div>
            <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">How can I help you choose your Hyundai?</h1>
            <p className="text-muted-foreground mt-2 max-w-xl text-sm sm:text-base">
              Ask about features, specifications, variants and comparisons. Every answer is grounded in the uploaded
              brochures and cites the page it came from.
            </p>
            <div className="mt-8">
              <SuggestedPrompts onPick={(t) => run(t)} disabled={busy} />
            </div>
          </div>
        ) : (
          <MessageList messages={messages} busy={busy} onRegenerate={regenerate} />
        )}
      </main>
      <Composer onSend={(t) => run(t)} onStop={() => abortRef.current?.abort()} busy={busy} initialFocus />
    </div>
  );
}

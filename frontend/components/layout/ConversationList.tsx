"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { MessageSquare, MoreHorizontal, Pencil, Trash2 } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useConversations } from "@/hooks/queries";
import { api } from "@/lib/api";
import type { Conversation } from "@/lib/types";
import { cn } from "@/lib/utils";

export function ConversationList({ onNavigate }: { onNavigate?: () => void }) {
  const { data, isLoading, isError } = useConversations();
  const pathname = usePathname();
  const router = useRouter();
  const qc = useQueryClient();
  const [renaming, setRenaming] = useState<Conversation | null>(null);
  const [deleting, setDeleting] = useState<Conversation | null>(null);
  const [title, setTitle] = useState("");

  const rename = useMutation({
    mutationFn: (c: { id: string; title: string }) =>
      api<Conversation>(`/api/chat/conversations/${c.id}`, { method: "PATCH", json: { title: c.title } }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["conversations"] });
      setRenaming(null);
    },
    onError: (e: Error) => toast.error(e.message),
  });
  const remove = useMutation({
    mutationFn: (id: string) => api(`/api/chat/conversations/${id}`, { method: "DELETE" }),
    onSuccess: (_d, id) => {
      qc.invalidateQueries({ queryKey: ["conversations"] });
      qc.removeQueries({ queryKey: ["conversation", id] });
      if (pathname === `/chat/${id}`) router.push("/chat");
      setDeleting(null);
      toast.success("Conversation deleted");
    },
    onError: (e: Error) => toast.error(e.message),
  });

  if (isLoading)
    return (
      <div className="space-y-2 px-2">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-8 w-full" />
        ))}
      </div>
    );
  if (isError) return <p className="text-muted-foreground px-3 text-xs">Could not load conversations.</p>;
  if (!data?.items.length) return <p className="text-muted-foreground px-3 text-xs">No conversations yet.</p>;

  return (
    <>
      <ul className="space-y-0.5" aria-label="Conversations">
        {data.items.map((c) => {
          const active = pathname === `/chat/${c.id}`;
          return (
            <li key={c.id} className="group relative">
              <Link
                href={`/chat/${c.id}`}
                onClick={onNavigate}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "hover:bg-accent flex items-center gap-2 rounded-md py-1.5 pr-8 pl-2.5 text-sm",
                  active && "bg-accent font-medium",
                )}
              >
                <MessageSquare className="text-muted-foreground size-3.5 shrink-0" />
                <span className="truncate">{c.title}</span>
              </Link>
              <DropdownMenu>
                <DropdownMenuTrigger
                  aria-label={`Options for ${c.title}`}
                  className="hover:bg-background focus-visible:ring-ring/50 absolute top-1/2 right-1 flex size-6 -translate-y-1/2 items-center justify-center rounded opacity-100 outline-none focus-visible:ring-2 lg:opacity-0 lg:group-hover:opacity-100 lg:focus-visible:opacity-100 data-[state=open]:opacity-100"
                >
                  <MoreHorizontal className="size-4" />
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  <DropdownMenuItem
                    onSelect={() => {
                      setTitle(c.title);
                      setRenaming(c);
                    }}
                  >
                    <Pencil /> Rename
                  </DropdownMenuItem>
                  <DropdownMenuItem variant="destructive" onSelect={() => setDeleting(c)}>
                    <Trash2 /> Delete
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </li>
          );
        })}
      </ul>

      <Dialog open={!!renaming} onOpenChange={(o) => !o && setRenaming(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Rename conversation</DialogTitle>
          </DialogHeader>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (renaming && title.trim()) rename.mutate({ id: renaming.id, title: title.trim() });
            }}
            className="grid gap-4"
          >
            <Input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={120} aria-label="Title" autoFocus />
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setRenaming(null)}>
                Cancel
              </Button>
              <Button type="submit" disabled={!title.trim() || rename.isPending}>
                Save
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <AlertDialog open={!!deleting} onOpenChange={(o) => !o && setDeleting(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete this conversation?</AlertDialogTitle>
            <AlertDialogDescription>
              &ldquo;{deleting?.title}&rdquo; and all its messages will be permanently deleted.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={() => deleting && remove.mutate(deleting.id)}>Delete</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}

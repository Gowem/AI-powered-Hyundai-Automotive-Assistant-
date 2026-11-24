"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ExternalLink, MoreHorizontal, Pencil, RotateCw, Trash2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { openSourcePdf } from "@/components/chat/openSource";
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
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useVehicleModels } from "@/hooks/queries";
import { api } from "@/lib/api";
import type { DocumentItem } from "@/lib/types";

export function DocumentActions({ doc }: { doc: DocumentItem }) {
  const qc = useQueryClient();
  const { data: models } = useVehicleModels();
  const [renameOpen, setRenameOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [name, setName] = useState(doc.display_name);
  const [model, setModel] = useState(doc.vehicle_model);
  const busy = doc.status === "queued" || doc.status === "processing";
  const refresh = () => qc.invalidateQueries({ queryKey: ["documents"] });

  const patch = useMutation({
    mutationFn: () =>
      api<DocumentItem>(`/api/documents/${doc.id}`, {
        method: "PATCH",
        json: { display_name: name.trim(), ...(model !== doc.vehicle_model ? { vehicle_model: model } : {}) },
      }),
    onSuccess: () => {
      refresh();
      setRenameOpen(false);
      toast.success("Document updated");
    },
    onError: (e: Error) => toast.error(e.message),
  });
  const reprocess = useMutation({
    mutationFn: () => api<DocumentItem>(`/api/documents/${doc.id}/reprocess`, { method: "POST" }),
    onSuccess: () => {
      refresh();
      toast.success("Re-processing started");
    },
    onError: (e: Error) => toast.error(e.message),
  });
  const remove = useMutation({
    mutationFn: () => api(`/api/documents/${doc.id}`, { method: "DELETE" }),
    onSuccess: () => {
      refresh();
      toast.success("Document deleted");
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const modelOptions = Array.from(new Set([...(models?.models ?? []), doc.vehicle_model]));

  return (
    <>
      <div className="flex items-center justify-end gap-1">
        <Button variant="outline" size="sm" onClick={() => openSourcePdf(doc.id)} aria-label={`View ${doc.display_name}`}>
          <ExternalLink /> <span className="hidden sm:inline">View</span>
        </Button>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon-sm" aria-label={`More actions for ${doc.display_name}`}>
              <MoreHorizontal />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem disabled={!doc.owner_is_me} onSelect={() => setRenameOpen(true)}>
              <Pencil /> Rename / change model
            </DropdownMenuItem>
            <DropdownMenuItem disabled={!doc.owner_is_me || busy} onSelect={() => reprocess.mutate()}>
              <RotateCw /> Reprocess
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem variant="destructive" disabled={!doc.owner_is_me} onSelect={() => setDeleteOpen(true)}>
              <Trash2 /> Delete
            </DropdownMenuItem>
            {!doc.owner_is_me && (
              <p className="text-muted-foreground px-2 py-1.5 text-[11px]">Only the uploader can modify this document.</p>
            )}
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      <Dialog open={renameOpen} onOpenChange={setRenameOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Edit document</DialogTitle>
          </DialogHeader>
          <form
            className="grid gap-4"
            onSubmit={(e) => {
              e.preventDefault();
              if (name.trim()) patch.mutate();
            }}
          >
            <div className="grid gap-2">
              <Label htmlFor={`dn-${doc.id}`}>Display name</Label>
              <Input id={`dn-${doc.id}`} value={name} onChange={(e) => setName(e.target.value)} maxLength={200} />
            </div>
            <div className="grid gap-2">
              <Label htmlFor={`vm-${doc.id}`}>Vehicle model</Label>
              <Select value={model} onValueChange={setModel}>
                <SelectTrigger id={`vm-${doc.id}`}>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {modelOptions.map((m) => (
                    <SelectItem key={m} value={m}>
                      {m}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setRenameOpen(false)}>
                Cancel
              </Button>
              <Button type="submit" disabled={!name.trim() || patch.isPending}>
                Save
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <AlertDialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete this brochure?</AlertDialogTitle>
            <AlertDialogDescription>
              &ldquo;{doc.display_name}&rdquo; and its indexed content will be removed for everyone. This cannot be
              undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={() => remove.mutate()}>Delete</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}

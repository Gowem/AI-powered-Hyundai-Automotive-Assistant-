"use client";

import { FileStack, Search, Upload } from "lucide-react";
import { useDeferredValue, useState } from "react";

import { DocumentsTable } from "@/components/documents/DocumentsTable";
import { UploadDialog } from "@/components/documents/UploadDialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { useDocuments } from "@/hooks/queries";

const ALL = "all";

export default function DocumentsPage() {
  const [q, setQ] = useState("");
  const [model, setModel] = useState(ALL);
  const [status, setStatus] = useState(ALL);
  const deferredQ = useDeferredValue(q);
  const all = useDocuments();
  const filtered = useDocuments({
    q: deferredQ.trim() || undefined,
    vehicle_model: model === ALL ? undefined : model,
    status: status === ALL ? undefined : status,
  });
  const models = Array.from(new Set((all.data?.items ?? []).map((d) => d.vehicle_model))).sort();
  const hasAny = (all.data?.total ?? 0) > 0;

  return (
    <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-6 sm:px-6 lg:py-10">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Documents</h1>
          <p className="text-muted-foreground mt-1 text-sm">
            Brochures form a shared knowledge base. {all.data ? `${all.data.ready_count} ready for chat.` : ""}
          </p>
        </div>
        <UploadDialog />
      </div>

      {hasAny && (
        <div className="mt-6 flex flex-col gap-2 sm:flex-row">
          <div className="relative flex-1">
            <Search className="text-muted-foreground absolute top-1/2 left-3 size-4 -translate-y-1/2" />
            <Input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search by name"
              className="pl-9"
              aria-label="Search documents by name"
            />
          </div>
          <Select value={model} onValueChange={setModel}>
            <SelectTrigger className="sm:w-48" aria-label="Filter by vehicle model">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL}>All models</SelectItem>
              {models.map((m) => (
                <SelectItem key={m} value={m}>
                  {m}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={status} onValueChange={setStatus}>
            <SelectTrigger className="sm:w-40" aria-label="Filter by status">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL}>All statuses</SelectItem>
              <SelectItem value="ready">Ready</SelectItem>
              <SelectItem value="processing">Processing</SelectItem>
              <SelectItem value="queued">Queued</SelectItem>
              <SelectItem value="failed">Failed</SelectItem>
            </SelectContent>
          </Select>
        </div>
      )}

      <div className="mt-4">
        {all.isLoading || filtered.isLoading ? (
          <div className="space-y-2">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-16 w-full rounded-xl" />
            ))}
          </div>
        ) : all.isError ? (
          <p className="text-destructive text-sm">Could not load documents: {all.error.message}</p>
        ) : !hasAny ? (
          <div className="bg-card flex flex-col items-center justify-center gap-3 rounded-xl border border-dashed px-6 py-16 text-center">
            <div className="bg-primary/10 text-primary flex size-14 items-center justify-center rounded-2xl">
              <FileStack className="size-7" />
            </div>
            <h2 className="text-lg font-semibold">No brochures yet</h2>
            <p className="text-muted-foreground max-w-sm text-sm">
              Upload official Hyundai brochures (PDF). The assistant answers only from what they contain.
            </p>
            <UploadDialog
              trigger={
                <Button className="mt-2">
                  <Upload /> Upload your first brochure
                </Button>
              }
            />
          </div>
        ) : filtered.data && filtered.data.items.length === 0 ? (
          <p className="text-muted-foreground py-10 text-center text-sm">No documents match these filters.</p>
        ) : (
          <DocumentsTable docs={filtered.data?.items ?? []} />
        )}
      </div>
    </main>
  );
}

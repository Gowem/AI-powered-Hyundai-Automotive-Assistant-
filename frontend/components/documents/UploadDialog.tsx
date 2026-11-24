"use client";

import { useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, FileUp, Loader2, Upload, X, XCircle } from "lucide-react";
import { useCallback, useRef, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useVehicleModels } from "@/hooks/queries";
import { uploadBrochure } from "@/lib/upload";
import { detectVehicleFromFilename } from "@/lib/vehicles";
import { cn, formatBytes } from "@/lib/utils";

const MAX_MB = 50;
const AUTO = "__auto__";

type Row = {
  key: string;
  file: File;
  vehicle: string;
  otherText: string;
  displayName: string;
  progress: number;
  state: "idle" | "uploading" | "confirming" | "done" | "error";
  error?: string;
};

export function UploadDialog({ trigger }: { trigger?: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  const [rows, setRows] = useState<Row[]>([]);
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const { data: models } = useVehicleModels();
  const qc = useQueryClient();
  const running = rows.some((r) => r.state === "uploading" || r.state === "confirming");

  const addFiles = useCallback((files: FileList | File[]) => {
    const next: Row[] = [];
    for (const file of Array.from(files)) {
      if (!file.name.toLowerCase().endsWith(".pdf") || (file.type && file.type !== "application/pdf")) {
        toast.error(`${file.name}: only PDF files are allowed`);
        continue;
      }
      if (file.size > MAX_MB * 1024 * 1024) {
        toast.error(`${file.name}: exceeds the ${MAX_MB} MB limit`);
        continue;
      }
      next.push({
        key: `${file.name}-${file.size}-${Math.random()}`,
        file,
        vehicle: detectVehicleFromFilename(file.name) ?? AUTO,
        otherText: "",
        displayName: "",
        progress: 0,
        state: "idle",
      });
    }
    setRows((prev) => [...prev, ...next]);
  }, []);

  const update = (key: string, patch: Partial<Row>) =>
    setRows((prev) => prev.map((r) => (r.key === key ? { ...r, ...patch } : r)));

  async function uploadAll() {
    const pending = rows.filter((r) => r.state === "idle" || r.state === "error");
    await Promise.all(
      pending.map(async (r) => {
        update(r.key, { state: "uploading", progress: 0, error: undefined });
        const vehicle =
          r.vehicle === AUTO ? null : r.vehicle === "Other" ? (r.otherText.trim() ? `Other: ${r.otherText}` : "Other") : r.vehicle;
        try {
          await uploadBrochure({
            file: r.file,
            vehicleModel: vehicle,
            displayName: r.displayName.trim() || null,
            onProgress: (p) => update(r.key, { progress: p, state: p >= 100 ? "confirming" : "uploading" }),
          });
          update(r.key, { state: "done", progress: 100 });
        } catch (e) {
          update(r.key, { state: "error", error: e instanceof Error ? e.message : "Upload failed" });
        }
      }),
    );
    qc.invalidateQueries({ queryKey: ["documents"] });
  }

  function close(o: boolean) {
    if (!o && running) return;
    setOpen(o);
    if (!o) {
      const done = rows.filter((r) => r.state === "done").length;
      if (done) toast.success(`${done} brochure${done > 1 ? "s" : ""} uploaded and queued for processing`);
      setRows([]);
    }
  }

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogTrigger asChild>
        {trigger ?? (
          <Button>
            <Upload /> Upload brochure
          </Button>
        )}
      </DialogTrigger>
      <DialogContent className="sm:max-w-2xl" onInteractOutside={(e) => running && e.preventDefault()}>
        <DialogHeader>
          <DialogTitle>Upload brochures</DialogTitle>
          <DialogDescription>
            PDF only, up to {MAX_MB} MB each. Files are parsed, chunked and indexed automatically.
          </DialogDescription>
        </DialogHeader>

        <div
          role="button"
          tabIndex={0}
          onClick={() => inputRef.current?.click()}
          onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && inputRef.current?.click()}
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            addFiles(e.dataTransfer.files);
          }}
          className={cn(
            "hover:bg-accent/50 focus-visible:ring-ring/50 flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed px-4 py-8 text-center outline-none focus-visible:ring-[3px]",
            dragging && "border-primary bg-primary/5",
          )}
          aria-label="Choose PDF files or drag and drop"
        >
          <FileUp className="text-primary size-8" />
          <p className="text-sm font-medium">Drag & drop PDFs here, or click to browse</p>
          <p className="text-muted-foreground text-xs">The vehicle model is pre-filled from the filename</p>
          <input
            ref={inputRef}
            type="file"
            accept="application/pdf,.pdf"
            multiple
            hidden
            onChange={(e) => {
              if (e.target.files) addFiles(e.target.files);
              e.target.value = "";
            }}
          />
        </div>

        {rows.length > 0 && (
          <ul className="max-h-[45dvh] space-y-3 overflow-y-auto pr-1">
            {rows.map((r) => {
              const editable = r.state === "idle" || r.state === "error";
              return (
                <li key={r.key} className="rounded-lg border p-3">
                  <div className="flex items-start gap-2">
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium">{r.file.name}</p>
                      <p className="text-muted-foreground text-xs">{formatBytes(r.file.size)}</p>
                    </div>
                    {r.state === "done" && <CheckCircle2 className="size-5 text-emerald-600" aria-label="Uploaded" />}
                    {r.state === "error" && <XCircle className="text-destructive size-5" aria-label="Failed" />}
                    {(r.state === "uploading" || r.state === "confirming") && (
                      <Loader2 className="text-primary size-5 animate-spin" />
                    )}
                    {editable && (
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        aria-label={`Remove ${r.file.name}`}
                        onClick={() => setRows((prev) => prev.filter((x) => x.key !== r.key))}
                      >
                        <X />
                      </Button>
                    )}
                  </div>
                  {editable && (
                    <div className="mt-3 grid gap-2 sm:grid-cols-2">
                      <div className="grid gap-1">
                        <label className="text-muted-foreground text-xs" htmlFor={`m-${r.key}`}>
                          Vehicle model
                        </label>
                        <Select value={r.vehicle} onValueChange={(v) => update(r.key, { vehicle: v })}>
                          <SelectTrigger id={`m-${r.key}`}>
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value={AUTO}>Detect automatically</SelectItem>
                            {(models?.models ?? []).map((m) => (
                              <SelectItem key={m} value={m}>
                                {m}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                        {r.vehicle === "Other" && (
                          <Input
                            placeholder="Model name"
                            value={r.otherText}
                            maxLength={60}
                            onChange={(e) => update(r.key, { otherText: e.target.value })}
                            aria-label="Other model name"
                          />
                        )}
                      </div>
                      <div className="grid gap-1">
                        <label className="text-muted-foreground text-xs" htmlFor={`n-${r.key}`}>
                          Display name (optional)
                        </label>
                        <Input
                          id={`n-${r.key}`}
                          placeholder={r.file.name.replace(/\.pdf$/i, "")}
                          value={r.displayName}
                          maxLength={200}
                          onChange={(e) => update(r.key, { displayName: e.target.value })}
                        />
                      </div>
                    </div>
                  )}
                  {(r.state === "uploading" || r.state === "confirming" || r.state === "done") && (
                    <div className="mt-2">
                      <Progress value={r.progress} aria-label={`Upload progress ${r.progress}%`} />
                      <p className="text-muted-foreground mt-1 text-xs">
                        {r.state === "uploading" && `Uploading… ${r.progress}%`}
                        {r.state === "confirming" && "Verifying file…"}
                        {r.state === "done" && "Uploaded · queued for processing"}
                      </p>
                    </div>
                  )}
                  {r.error && <p className="text-destructive mt-2 text-xs">{r.error}</p>}
                </li>
              );
            })}
          </ul>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={() => close(false)} disabled={running}>
            {rows.some((r) => r.state === "done") ? "Done" : "Cancel"}
          </Button>
          <Button
            onClick={uploadAll}
            disabled={running || !rows.some((r) => r.state === "idle" || r.state === "error")}
          >
            {running && <Loader2 className="animate-spin" />}
            Upload {rows.filter((r) => r.state === "idle" || r.state === "error").length || ""}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

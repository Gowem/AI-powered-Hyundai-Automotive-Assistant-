import { CheckCircle2, Clock, Loader2, XCircle } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { DocumentItem } from "@/lib/types";

export function StatusBadge({ doc }: { doc: DocumentItem }) {
  switch (doc.status) {
    case "ready":
      return (
        <Badge variant="success">
          <CheckCircle2 /> Ready
        </Badge>
      );
    case "processing":
      return (
        <div className="flex flex-col gap-1">
          <Badge variant="info">
            <Loader2 className="animate-spin" /> Processing
          </Badge>
          {doc.status_detail && <span className="text-muted-foreground text-[11px]">{doc.status_detail}</span>}
        </div>
      );
    case "failed":
      return (
        <Tooltip>
          <TooltipTrigger asChild>
            <Badge variant="danger" tabIndex={0} className="cursor-help">
              <XCircle /> Failed
            </Badge>
          </TooltipTrigger>
          <TooltipContent>{doc.status_detail ?? "Processing failed"}</TooltipContent>
        </Tooltip>
      );
    default:
      return (
        <Badge variant="muted">
          <Clock /> Queued
        </Badge>
      );
  }
}

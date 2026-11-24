"use client";

import { FileText } from "lucide-react";

import type { DocumentItem } from "@/lib/types";
import { formatBytes, formatDate } from "@/lib/utils";

import { DocumentActions } from "./DocumentActions";
import { StatusBadge } from "./StatusBadge";

export function DocumentsTable({ docs }: { docs: DocumentItem[] }) {
  return (
    <>
      {/* desktop / tablet */}
      <div className="bg-card hidden overflow-x-auto rounded-xl border shadow-xs md:block">
        <table className="w-full text-sm">
          <thead className="bg-muted/50 text-muted-foreground text-left text-xs">
            <tr>
              <th scope="col" className="px-4 py-3 font-medium">Document name</th>
              <th scope="col" className="px-4 py-3 font-medium">Vehicle model</th>
              <th scope="col" className="px-4 py-3 font-medium">Upload date</th>
              <th scope="col" className="px-4 py-3 text-right font-medium">Pages</th>
              <th scope="col" className="px-4 py-3 text-right font-medium">Chunks</th>
              <th scope="col" className="px-4 py-3 font-medium">Status</th>
              <th scope="col" className="px-4 py-3 text-right font-medium">Actions</th>
            </tr>
          </thead>
          <tbody>
            {docs.map((d) => (
              <tr key={d.id} className="hover:bg-muted/30 border-t">
                <td className="max-w-[280px] px-4 py-3">
                  <div className="flex items-center gap-2.5">
                    <FileText className="text-primary size-4 shrink-0" />
                    <div className="min-w-0">
                      <p className="truncate font-medium" title={d.display_name}>
                        {d.display_name}
                      </p>
                      <p className="text-muted-foreground truncate text-xs" title={d.original_filename}>
                        {d.original_filename} · {formatBytes(d.file_size_bytes)}
                      </p>
                    </div>
                  </div>
                </td>
                <td className="px-4 py-3">
                  {d.vehicle_model}
                  {d.model_year && <span className="text-muted-foreground"> · {d.model_year}</span>}
                </td>
                <td className="text-muted-foreground px-4 py-3 whitespace-nowrap">{formatDate(d.uploaded_at)}</td>
                <td className="px-4 py-3 text-right tabular-nums">{d.page_count ?? "–"}</td>
                <td className="px-4 py-3 text-right tabular-nums">{d.chunk_count || "–"}</td>
                <td className="px-4 py-3">
                  <StatusBadge doc={d} />
                </td>
                <td className="px-4 py-3">
                  <DocumentActions doc={d} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* mobile cards */}
      <ul className="space-y-3 md:hidden">
        {docs.map((d) => (
          <li key={d.id} className="bg-card rounded-xl border p-4 shadow-xs">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="truncate font-medium">{d.display_name}</p>
                <p className="text-muted-foreground mt-0.5 text-xs">
                  {d.vehicle_model} · {formatDate(d.uploaded_at)}
                </p>
              </div>
              <StatusBadge doc={d} />
            </div>
            <div className="text-muted-foreground mt-3 flex items-center justify-between text-xs">
              <span>
                {d.page_count ?? "–"} pages · {d.chunk_count || "–"} chunks · {formatBytes(d.file_size_bytes)}
              </span>
              <DocumentActions doc={d} />
            </div>
          </li>
        ))}
      </ul>
    </>
  );
}

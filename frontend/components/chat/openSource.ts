import { toast } from "sonner";

import { api } from "@/lib/api";

/** Open the brochure PDF at a page in a new tab (signed, short-lived URL). */
export async function openSourcePdf(documentId: string, page?: number) {
  // Open synchronously to avoid popup blockers, then point it at the signed URL.
  const win = window.open("about:blank", "_blank");
  try {
    const { url } = await api<{ url: string }>(`/api/documents/${documentId}/view-url`);
    const absolute = new URL(url, window.location.origin).toString();
    const target = page ? `${absolute}#page=${page}` : absolute;
    if (win) {
      win.opener = null;
      win.location.href = target;
    } else window.open(target, "_blank", "noopener");
  } catch (e) {
    win?.close();
    toast.error(e instanceof Error ? e.message : "Could not open the brochure");
  }
}

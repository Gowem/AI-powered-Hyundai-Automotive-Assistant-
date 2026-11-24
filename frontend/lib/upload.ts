import { createClient } from "@supabase/supabase-js";

import { api, ApiError } from "@/lib/api";
import type { DocumentItem, UploadUrlResponse } from "@/lib/types";

const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL ?? "";
const SUPABASE_ANON_KEY = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ?? "";
const BUCKET = process.env.NEXT_PUBLIC_SUPABASE_BUCKET ?? "brochures";

function xhrPut(
  url: string,
  file: File,
  headers: Record<string, string>,
  onProgress: (pct: number) => void,
  signal?: AbortSignal,
): Promise<void> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("PUT", url);
    xhr.withCredentials = true;
    Object.entries(headers).forEach(([k, v]) => xhr.setRequestHeader(k, v));
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) onProgress(Math.round((e.loaded / e.total) * 100));
    };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) resolve();
      else {
        let msg = `Upload failed (${xhr.status})`;
        try {
          const body = JSON.parse(xhr.responseText) as { detail?: string; message?: string };
          msg = body.detail ?? body.message ?? msg;
        } catch {
          /* ignore */
        }
        reject(new ApiError(xhr.status, msg));
      }
    };
    xhr.onerror = () => reject(new ApiError(0, "Network error during upload"));
    xhr.onabort = () => reject(new ApiError(0, "Upload cancelled"));
    signal?.addEventListener("abort", () => xhr.abort());
    xhr.send(file);
  });
}

async function uploadToSupabase(
  info: UploadUrlResponse,
  file: File,
  onProgress: (pct: number) => void,
  signal?: AbortSignal,
) {
  if (!SUPABASE_URL || !SUPABASE_ANON_KEY || !info.token) {
    throw new ApiError(0, "Supabase is not configured on the frontend");
  }
  const url = `${SUPABASE_URL}/storage/v1/object/upload/sign/${BUCKET}/${info.path}?token=${encodeURIComponent(info.token)}`;
  try {
    // XHR gives real progress events; same endpoint uploadToSignedUrl uses.
    await xhrPut(
      url,
      file,
      {
        apikey: SUPABASE_ANON_KEY,
        Authorization: `Bearer ${SUPABASE_ANON_KEY}`,
        "Content-Type": "application/pdf",
        "x-upsert": "true",
      },
      onProgress,
      signal,
    );
  } catch (err) {
    if (signal?.aborted) throw err;
    // Fallback to the official client helper (no progress events).
    const supabase = createClient(SUPABASE_URL, SUPABASE_ANON_KEY, { auth: { persistSession: false } });
    const { error } = await supabase.storage
      .from(BUCKET)
      .uploadToSignedUrl(info.path, info.token, file, { contentType: "application/pdf", upsert: true });
    if (error) throw new ApiError(0, error.message);
    onProgress(100);
  }
}

export async function uploadBrochure(opts: {
  file: File;
  vehicleModel: string | null;
  displayName: string | null;
  onProgress: (pct: number) => void;
  signal?: AbortSignal;
}): Promise<DocumentItem> {
  const { file, vehicleModel, displayName, onProgress, signal } = opts;
  const info = await api<UploadUrlResponse>("/api/documents/upload-url", {
    method: "POST",
    json: {
      filename: file.name,
      file_size_bytes: file.size,
      vehicle_model: vehicleModel || null,
      display_name: displayName || null,
    },
  });
  if (info.mode === "local") {
    if (!info.upload_url || !info.token) throw new ApiError(0, "Invalid upload response");
    await xhrPut(
      `${info.upload_url}?token=${encodeURIComponent(info.token)}`,
      file,
      { "Content-Type": "application/pdf" },
      onProgress,
      signal,
    );
  } else {
    await uploadToSupabase(info, file, onProgress, signal);
  }
  return api<DocumentItem>(`/api/documents/${info.document_id}/confirm`, { method: "POST" });
}

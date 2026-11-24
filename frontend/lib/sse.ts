/** Minimal Server-Sent Events reader over fetch (EventSource cannot POST). */

export type SSEEvent = { event: string; data: unknown };

export async function* readSSE(res: Response, signal?: AbortSignal): AsyncGenerator<SSEEvent> {
  if (!res.body) throw new Error("No response body");
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    while (true) {
      if (signal?.aborted) return;
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let idx: number;
      while ((idx = buffer.search(/\r?\n\r?\n/)) !== -1) {
        const raw = buffer.slice(0, idx);
        buffer = buffer.slice(idx).replace(/^\r?\n\r?\n/, "");
        let event = "message";
        const dataLines: string[] = [];
        for (const line of raw.split(/\r?\n/)) {
          if (line.startsWith("event:")) event = line.slice(6).trim();
          else if (line.startsWith("data:")) dataLines.push(line.slice(5).trimStart());
        }
        if (!dataLines.length) continue;
        const text = dataLines.join("\n");
        let data: unknown = text;
        try {
          data = JSON.parse(text);
        } catch {
          /* keep raw text */
        }
        yield { event, data };
      }
    }
  } finally {
    reader.releaseLock();
  }
}

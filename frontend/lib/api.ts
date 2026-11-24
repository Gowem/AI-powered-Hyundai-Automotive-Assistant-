/** Fetch wrapper: same-origin /api/* (proxied by Next.js rewrites), cookies included, 401 -> /login. */

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

const AUTH_PATHS = ["/api/auth/login", "/api/auth/register", "/api/auth/me"];

export function redirectToLogin() {
  if (typeof window === "undefined") return;
  const { pathname, search } = window.location;
  if (pathname.startsWith("/login") || pathname.startsWith("/register")) return;
  const next = encodeURIComponent(pathname + search);
  window.location.href = `/login?next=${next}`;
}

export async function parseError(res: Response): Promise<string> {
  try {
    const data = (await res.json()) as { detail?: unknown };
    if (typeof data.detail === "string") return data.detail;
  } catch {
    /* not JSON */
  }
  if (res.status === 429) return "Too many attempts. Please wait a minute and try again.";
  if (res.status >= 500) return "The server had a problem. Please try again.";
  return `Request failed (${res.status})`;
}

export async function api<T>(path: string, init: RequestInit & { json?: unknown } = {}): Promise<T> {
  const { json, headers, ...rest } = init;
  const res = await fetch(path, {
    credentials: "include",
    ...rest,
    headers: {
      ...(json !== undefined ? { "Content-Type": "application/json" } : {}),
      ...headers,
    },
    body: json !== undefined ? JSON.stringify(json) : rest.body,
  });
  if (res.status === 401 && !AUTH_PATHS.includes(path)) {
    redirectToLogin();
  }
  if (!res.ok) throw new ApiError(res.status, await parseError(res));
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

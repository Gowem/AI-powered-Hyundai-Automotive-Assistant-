import { NextResponse, type NextRequest } from "next/server";

const COOKIE = process.env.AUTH_COOKIE_NAME ?? "hyundai_session";
const PROTECTED = ["/chat", "/documents"];
const AUTH_PAGES = ["/login", "/register"];

/** Only checks that the cookie exists; the backend validates it on every API call. */
export function middleware(req: NextRequest) {
  const { pathname, search } = req.nextUrl;
  const hasCookie = Boolean(req.cookies.get(COOKIE)?.value);

  if (PROTECTED.some((p) => pathname === p || pathname.startsWith(`${p}/`)) && !hasCookie) {
    const url = req.nextUrl.clone();
    url.pathname = "/login";
    url.search = `?next=${encodeURIComponent(pathname + search)}`;
    return NextResponse.redirect(url);
  }
  if (AUTH_PAGES.includes(pathname) && hasCookie) {
    const url = req.nextUrl.clone();
    url.pathname = "/chat";
    url.search = "";
    return NextResponse.redirect(url);
  }
  return NextResponse.next();
}

// Never match /api so uploads and SSE are proxied without middleware buffering.
export const config = {
  matcher: ["/chat/:path*", "/documents/:path*", "/login", "/register"],
};

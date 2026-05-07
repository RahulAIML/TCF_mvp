import { NextRequest, NextResponse } from "next/server";

const PROTECTED_PREFIX = "/tcf";
const COOKIE_NAME = "tcf_auth";
const PUBLIC_PATHS = ["/login", "/register", "/"];

export function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;

  // Only guard /tcf routes
  if (!pathname.startsWith(PROTECTED_PREFIX)) {
    return NextResponse.next();
  }

  // Allow if auth cookie present (set on login)
  const token = req.cookies.get(COOKIE_NAME)?.value;
  if (token) {
    return NextResponse.next();
  }

  // No token → send to landing page, preserving intended destination
  const url = req.nextUrl.clone();
  url.pathname = "/";
  url.searchParams.set("next", pathname);
  return NextResponse.redirect(url);
}

export const config = {
  matcher: ["/tcf/:path*"],
};

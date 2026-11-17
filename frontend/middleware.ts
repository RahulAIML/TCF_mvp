import { NextRequest, NextResponse } from "next/server";

const COOKIE_NAME = "tcf_auth";
const PRIVATE_PATHS = ["/tcf/dashboard"];

export function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;

  if (!PRIVATE_PATHS.some((p) => pathname === p || pathname.startsWith(p + "/"))) {
    return NextResponse.next();
  }

  const token = req.cookies.get(COOKIE_NAME)?.value;
  if (token) return NextResponse.next();

  const url = req.nextUrl.clone();
  url.pathname = "/";
  url.searchParams.set("next", pathname);
  return NextResponse.redirect(url);
}

export const config = {
  matcher: ["/tcf/:path*"],
};

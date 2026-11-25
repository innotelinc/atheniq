import { NextResponse } from "next/server";
import { PORTAL_COOKIE } from "@/lib/portal";

export const dynamic = "force-dynamic";

/** Signing out only clears the cookie; the account and the records stay put. */
export async function POST(request: Request) {
  const origin = new URL(request.url);
  const host = request.headers.get("x-forwarded-host") || request.headers.get("host");
  const proto = request.headers.get("x-forwarded-proto") || origin.protocol.replace(":", "");
  const target = host ? `${proto}://${host}/portal/login` : new URL("/portal/login", request.url).toString();
  const response = NextResponse.redirect(target, 303);
  response.cookies.set(PORTAL_COOKIE, "", { httpOnly: true, path: "/", maxAge: 0 });
  return response;
}

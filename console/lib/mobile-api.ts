import { NextResponse } from "next/server";

/**
 * The app calls this API cross-origin (a native client does not care, but the
 * Expo web preview does), and it authenticates with a bearer token rather than
 * a cookie, so there is nothing for a wildcard origin to leak.
 */
const CORS: Record<string, string> = {
  "access-control-allow-origin": "*",
  "access-control-allow-headers": "authorization, content-type",
  "access-control-allow-methods": "GET, POST, OPTIONS",
  "access-control-max-age": "86400",
};

export function ok<T>(data: T, status = 200) {
  return NextResponse.json({ ok: true, data }, { status, headers: CORS });
}

export function fail(error: string, status = 400, extra?: Record<string, unknown>) {
  return NextResponse.json({ ok: false, error, ...extra }, { status, headers: CORS });
}

export function preflight() {
  return new NextResponse(null, { status: 204, headers: CORS });
}

export function text(value: unknown, max = 500): string {
  return typeof value === "string" ? value.trim().slice(0, max) : "";
}

export function passwordProblem(value: string): string | null {
  if (value.length < 8) return "Choose a password of at least 8 characters.";
  if (value.length > 200) return "That password is too long.";
  return null;
}

export function validEmail(value: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);
}

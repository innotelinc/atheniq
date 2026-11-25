import { NextResponse } from "next/server";
import { getDb, logAuthEvent, mutate, nowIso } from "@/lib/store";
import { verifyPassword } from "@/lib/staff";
import { PORTAL_COOKIE, issuePortalSession } from "@/lib/portal";

export const dynamic = "force-dynamic";

/**
 * Student sign-in for the portal.
 *
 * Accepts a plain <form> submission as well as JSON, and answers a form post with
 * a 303 so the page works before hydration — the same shape the staff sign-in
 * uses. The password is checked against the learner's existing scrypt hash.
 */
interface Body {
  email?: string;
  password?: string;
}

function redirect(request: Request, to: string): NextResponse {
  const url = new URL(to, request.url);
  const origin = new URL(request.url);
  // Behind the proxy the request URL can name the container, not the browser.
  const host = request.headers.get("x-forwarded-host") || request.headers.get("host");
  const proto = request.headers.get("x-forwarded-proto") || origin.protocol.replace(":", "");
  const target = host ? `${proto}://${host}${url.pathname}${url.search}` : url.toString();
  return NextResponse.redirect(target, 303);
}

export async function POST(request: Request) {
  const contentType = request.headers.get("content-type") || "";
  const form = contentType.includes("form") ? await request.formData() : null;
  const body = form
    ? ({ email: String(form.get("email") || ""), password: String(form.get("password") || "") } as Body)
    : ((await request.json().catch(() => null)) as Body | null);

  const isForm = Boolean(form);
  const email = (body?.email || "").trim().toLowerCase().slice(0, 200);
  const password = typeof body?.password === "string" ? body.password : "";

  const refuse = (message: string, status = 401) =>
    isForm ? redirect(request, "/portal/login?error=1") : NextResponse.json({ ok: false, error: message }, { status });

  if (!email || !password) return refuse("Enter your email and password.");

  const db = getDb();
  const learner = db.learners.find(
    (record) => record.email.toLowerCase() === email && Boolean(record.passwordHash),
  );
  if (!learner?.passwordHash || !verifyPassword(password, learner.passwordHash)) {
    await mutate((store) => {
      logAuthEvent(
        store,
        email,
        learner ? "invalid_password" : "unknown_account",
        learner ? "Password did not match the learner account." : "No learner account uses that address.",
        "the student portal",
      );
    });
    return refuse("That email and password do not match an account.");
  }

  await mutate((store) => {
    const record = store.learners.find((item) => item.id === learner.id);
    if (record) record.lastSeenAt = nowIso();
    logAuthEvent(store, email, "success", "Signed in to the student portal.", "the student portal");
  });

  const session = issuePortalSession(learner.id);
  const response = isForm
    ? redirect(request, "/portal")
    : NextResponse.json({ ok: true, data: { name: learner.name } });
  response.cookies.set(PORTAL_COOKIE, session.value, {
    httpOnly: true,
    sameSite: "lax",
    secure: new URL(request.url).protocol === "https:" || request.headers.get("x-forwarded-proto") === "https",
    path: "/",
    maxAge: session.maxAge,
  });
  return response;
}

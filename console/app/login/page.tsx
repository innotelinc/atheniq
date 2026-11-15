import Link from "next/link";
import { authEnabled, safeNext } from "@/lib/session";
import { ssoEnabled } from "@/lib/sso";
import { getDb } from "@/lib/store";
import { PasskeySignIn } from "@/components/PasskeySignIn";

export const dynamic = "force-dynamic";

const ERRORS: Record<string, string> = {
  required: "Enter the console password.",
  invalid: "That password is not right.",
  domain: "That account is not on a registered domain, so it cannot sign in.",
  expired: "That sign-in attempt expired. Sign in again.",
  locked: "Too many refused attempts for that address. Wait a few minutes and try again.",
  sso_unknown:
    "That single sign-on account has no console account here. Ask a registrar to add your address.",
  sso_group:
    "That single sign-on account is not in the group this console allows. Ask for the AthenIQ admin group.",
};

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ next?: string; error?: string }>;
}) {
  const params = await searchParams;
  const next = safeNext(params.next);
  const enabled = authEnabled();
  const error = params.error ? (ERRORS[params.error] ?? "Could not sign in.") : null;
  const db = getDb();
  const twoFactor = db.settings.auth.require2fa;
  // One account needs no address to tell it apart; several do.
  const accounts = db.staff.filter((member) => !member.disabled).length;
  const showEmail = accounts > 1;

  return (
    <div style={{ display: "grid", placeItems: "center", minHeight: "64vh" }}>
      <div className="card" style={{ width: "100%", maxWidth: 440 }}>
        <div className="card-body stack">
          <span className="eyebrow">Innotel Labs · AthenIQ</span>
          <h1 style={{ fontSize: 22, margin: 0 }}>Registrar console</h1>
          {!enabled && (
            <p className="muted" style={{ margin: 0 }}>
              No console password is set on this host, so the console is open. Set AUTH_PASSWORD in .env to require a
              sign-in.
            </p>
          )}

          {enabled ? (
            <form method="post" action="/api/auth/login" className="stack">
              <input type="hidden" name="next" value={next} />
              {showEmail && (
                <label className="stack-sm">
                  <span className="small muted">Email</span>
                  <input name="email" type="email" autoComplete="username" required />
                </label>
              )}
              <label className="stack-sm">
                <span className="small muted">Password</span>
                <input name="password" type="password" required autoFocus autoComplete="current-password" />
              </label>
              {error && <span className="chip danger">{error}</span>}
              <button className="btn primary" type="submit">
                Sign in
              </button>
              {twoFactor && (
                <span className="tiny muted">A six-digit authenticator code follows the password.</span>
              )}
              {ssoEnabled() && (
                <a className="btn" href={`/api/auth/sso/start?next=${encodeURIComponent(next)}`}>
                  Sign in with single sign-on
                </a>
              )}
            </form>
          ) : (
            <Link className="btn primary" href={next}>
              Open the console
            </Link>
          )}

          {enabled && (
            <div className="stack-sm">
              <span className="tiny muted" style={{ textAlign: "center" }}>
                or
              </span>
              <PasskeySignIn next={next} />
            </div>
          )}

          <p className="tiny muted" style={{ margin: 0 }}>
            No account yet? <Link href="/request-access">Request staff access</Link>. Credential verification at{" "}
            <Link href="/verify">/verify</Link> stays public either way.
          </p>
        </div>
      </div>
    </div>
  );
}

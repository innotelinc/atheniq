"use client";

import { useState } from "react";

export function SignOutButton() {
  const [busy, setBusy] = useState(false);

  async function signOut() {
    setBusy(true);
    const response = await fetch("/api/auth/logout", { method: "POST" }).catch(() => undefined);
    const body = await response?.json().catch(() => null);
    const data = (body?.data ?? body) as { ssoSignOut?: string | null } | null;
    // Behind the SSO proxy the console session is one of two, and ending only
    // this one would let the next page load sign the person back in.
    window.location.assign(data?.ssoSignOut || "/login");
  }

  return (
    <button className="btn small" type="button" onClick={signOut} disabled={busy}>
      {busy ? "Signing out…" : "Sign out"}
    </button>
  );
}

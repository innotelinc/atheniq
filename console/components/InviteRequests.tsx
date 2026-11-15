"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { api } from "@/lib/client";

export interface PendingRequest {
  id: string;
  name: string;
  email: string;
  title: string;
  reason: string;
  createdAt: string;
}

export function InviteRequests({ requests }: { requests: PendingRequest[] }) {
  const router = useRouter();
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  async function decide(request: PendingRequest, action: "approve" | "decline") {
    setBusy(request.id);
    setError(null);
    setNotice(null);
    const result = await api<{
      vaultPassword?: string;
      vault?: { email: string; url: string };
      vaultError?: string;
    }>("/api/access-requests", {
      method: "PATCH",
      body: JSON.stringify({ id: request.id, action }),
    });
    setBusy(null);
    if (!result.ok) {
      setError(result.error ?? "That did not work.");
      return;
    }
    if (action === "decline") {
      setNotice(`${request.name}'s request was declined.`);
    } else {
      const vault = result.data?.vault;
      const password = result.data?.vaultPassword;
      setNotice(
        `${request.name} can now sign in with the password they chose and enrol two-factor.` +
          (vault && password
            ? ` Vault account ${vault.email} created at ${vault.url} — temporary password: ${password} (shown once).`
            : result.data?.vaultError
              ? ` Vault account not linked: ${result.data.vaultError}`
              : ""),
      );
    }
    router.refresh();
  }

  if (requests.length === 0) {
    return <span className="small muted">No one is waiting for an account.</span>;
  }

  return (
    <div className="stack-sm">
      {requests.map((request) => (
        <div key={request.id} className="between" style={{ alignItems: "flex-start" }}>
          <div>
            <div className="strong small">{request.name}</div>
            <div className="tiny muted">
              {request.email}
              {request.title ? ` · ${request.title}` : ""} · asked {request.createdAt.slice(0, 10)}
            </div>
            {request.reason && <div className="tiny">{request.reason}</div>}
          </div>
          <div className="row" style={{ gap: 6 }}>
            <button
              className="btn small primary"
              type="button"
              disabled={busy === request.id}
              onClick={() => decide(request, "approve")}
            >
              Approve
            </button>
            <button
              className="btn small ghost"
              type="button"
              disabled={busy === request.id}
              onClick={() => decide(request, "decline")}
            >
              Decline
            </button>
          </div>
        </div>
      ))}
      {notice && <span className="chip ok">{notice}</span>}
      {error && <span className="chip danger">{error}</span>}
    </div>
  );
}

"use client";

import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { api } from "@/lib/client";

export interface ApplicationRow {
  id: string;
  name: string;
  email: string;
  phone: string;
  programName: string;
  termLabel: string;
  goals: string;
  status: string;
  statusLabel: string;
  note: string;
  createdAt: string;
  transcript: { fileName: string; bytes: number } | null;
}

const STATUSES: { value: string; label: string }[] = [
  { value: "received", label: "Received" },
  { value: "reviewing", label: "Under review" },
  { value: "accepted", label: "Accepted" },
  { value: "waitlisted", label: "Waitlisted" },
  { value: "declined", label: "Declined" },
];

const CHIP: Record<string, string> = {
  received: "chip",
  reviewing: "chip muted",
  accepted: "chip ok",
  waitlisted: "chip muted",
  declined: "chip danger",
};

function size(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

/**
 * Admissions' working list: one row per applicant, the goals they wrote, the
 * transcript they sent, and the status a registrar sets. Each row saves on its
 * own, so a decision is one click and not a form submission for the whole page.
 */
export function ApplicationsQueue({ applications }: { applications: ApplicationRow[] }) {
  const router = useRouter();
  const [filter, setFilter] = useState("open");
  const [search, setSearch] = useState("");
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [statuses, setStatuses] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const visible = useMemo(() => {
    const term = search.trim().toLowerCase();
    return applications.filter((entry) => {
      const matchesStatus =
        filter === "all" ||
        (filter === "open" ? entry.status === "received" || entry.status === "reviewing" : entry.status === filter);
      if (!matchesStatus) return false;
      if (!term) return true;
      return [entry.name, entry.email, entry.programName, entry.goals].join(" ").toLowerCase().includes(term);
    });
  }, [applications, filter, search]);

  async function save(entry: ApplicationRow) {
    const status = statuses[entry.id] ?? entry.status;
    const note = notes[entry.id] ?? entry.note;
    setBusy(entry.id);
    setError(null);
    setNotice(null);
    const result = await api<{ status: string }>("/api/applications", {
      method: "PATCH",
      body: JSON.stringify({ id: entry.id, status, note }),
    });
    setBusy(null);
    if (!result.ok) {
      setError(result.error ?? "That did not save.");
      return;
    }
    setNotice(`${entry.name} is now ${STATUSES.find((item) => item.value === status)?.label ?? status}.`);
    router.refresh();
  }

  return (
    <div className="stack">
      <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
        <select className="input" value={filter} onChange={(event) => setFilter(event.target.value)} style={{ maxWidth: 200 }}>
          <option value="open">Needs an answer</option>
          <option value="all">Every application</option>
          {STATUSES.map((status) => (
            <option key={status.value} value={status.value}>
              {status.label}
            </option>
          ))}
        </select>
        <input
          className="input"
          placeholder="Search name, email, program or goals"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          style={{ maxWidth: 320 }}
        />
        <span className="chip muted">
          {visible.length} of {applications.length}
        </span>
      </div>

      {notice && <span className="chip ok">{notice}</span>}
      {error && <span className="chip danger">{error}</span>}

      {visible.length === 0 ? (
        <span className="small muted">Nothing here. New applications arrive as soon as they are submitted.</span>
      ) : (
        visible.map((entry) => (
          <div key={entry.id} className="card" style={{ background: "transparent" }}>
            <div className="card-body stack-sm">
              <div className="between" style={{ alignItems: "flex-start", gap: 12 }}>
                <div>
                  <div className="strong">{entry.name}</div>
                  <div className="tiny muted">
                    {entry.email}
                    {entry.phone ? ` · ${entry.phone}` : ""} · applied {entry.createdAt.slice(0, 10)}
                  </div>
                  <div className="tiny muted">
                    {entry.programName} · {entry.termLabel}
                  </div>
                </div>
                <span className={CHIP[entry.status] ?? "chip"}>{entry.statusLabel}</span>
              </div>

              <p className="small" style={{ margin: 0, whiteSpace: "pre-wrap" }}>
                {entry.goals}
              </p>

              <div className="row" style={{ gap: 10, flexWrap: "wrap", alignItems: "center" }}>
                {entry.transcript ? (
                  <a className="btn small ghost" href={`/api/applications/${entry.id}/transcript`}>
                    Transcript · {entry.transcript.fileName} ({size(entry.transcript.bytes)})
                  </a>
                ) : (
                  <span className="chip danger">No transcript</span>
                )}
                <span className="tiny muted">ref {entry.id}</span>
              </div>

              <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
                <select
                  className="input"
                  aria-label={`Status for ${entry.name}`}
                  value={statuses[entry.id] ?? entry.status}
                  onChange={(event) =>
                    setStatuses((current) => ({ ...current, [entry.id]: event.target.value }))
                  }
                  style={{ maxWidth: 200 }}
                >
                  {STATUSES.map((status) => (
                    <option key={status.value} value={status.value}>
                      {status.label}
                    </option>
                  ))}
                </select>
                <input
                  className="input"
                  aria-label={`Note for ${entry.name}`}
                  placeholder="Note for the record (optional)"
                  value={notes[entry.id] ?? entry.note}
                  onChange={(event) => setNotes((current) => ({ ...current, [entry.id]: event.target.value }))}
                  style={{ flex: 1, minWidth: 220 }}
                />
                <button
                  className="btn small primary"
                  type="button"
                  disabled={busy === entry.id}
                  onClick={() => save(entry)}
                >
                  {busy === entry.id ? "Saving…" : "Save"}
                </button>
              </div>
            </div>
          </div>
        ))
      )}
    </div>
  );
}

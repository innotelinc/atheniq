"use client";

import { useState } from "react";

// Kept as a literal rather than imported from lib/applications: that module
// reads and writes files, and it must not end up in a client bundle.
const TRANSCRIPT_HELP = "PDF, PNG or JPEG, up to 10 MB.";

export interface ProgramOption {
  id: string;
  name: string;
  credential: string;
}

export interface TermOption {
  value: string;
  label: string;
}

/**
 * The one application form.
 *
 * It posts multipart to the console so the record and the transcript arrive
 * together: a stored application always has something admissions can read. The
 * fetch deliberately leaves Content-Type alone, so the browser writes the
 * multipart boundary.
 */
export function ApplicationForm({
  programs,
  terms,
}: {
  programs: ProgramOption[];
  terms: TermOption[];
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sent, setSent] = useState<{ id: string; program: string; term: string } | null>(null);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formElement = event.currentTarget;
    const data = new FormData(formElement);
    setBusy(true);
    setError(null);

    try {
      const response = await fetch("/api/applications", { method: "POST", body: data });
      const body = (await response.json().catch(() => null)) as
        | { ok?: boolean; error?: string; data?: { id?: string } }
        | null;
      if (!response.ok || !body?.ok) {
        setError(body?.error ?? "The application could not be sent. Try again, or email admissions.");
        return;
      }
      const programId = String(data.get("programId") ?? "");
      const term = String(data.get("term") ?? "");
      setSent({
        id: body.data?.id ?? "",
        program: programs.find((entry) => entry.id === programId)?.name ?? "your program",
        term: terms.find((entry) => entry.value === term)?.label ?? term,
      });
    } catch {
      setError("The application could not be sent. Check your connection and try again.");
    } finally {
      setBusy(false);
    }
  }

  if (sent) {
    return (
      <div className="stack">
        <span className="chip ok">Application received</span>
        <p style={{ margin: 0 }}>
          Your application to <strong>{sent.program}</strong> for <strong>{sent.term}</strong> is with
          admissions. Every application is read by a person, and you will hear back at the address you
          gave us.
        </p>
        <p className="small muted" style={{ margin: 0 }}>
          Keep this reference: <strong>{sent.id}</strong>
        </p>
        <p className="tiny muted" style={{ margin: 0 }}>
          Sent the wrong file, or need to change something? Email{" "}
          <a href="mailto:admissions@atheniq.institute">admissions@atheniq.institute</a> with the
          reference above.
        </p>
      </div>
    );
  }

  return (
    <form onSubmit={submit} className="stack">
      <div className="split">
        <label className="stack-sm">
          <span className="small muted">Full name</span>
          <input className="input" name="name" maxLength={120} autoComplete="name" required />
        </label>
        <label className="stack-sm">
          <span className="small muted">Email</span>
          <input className="input" name="email" type="email" maxLength={200} autoComplete="email" required />
        </label>
      </div>

      <label className="stack-sm">
        <span className="small muted">Phone (optional)</span>
        <input className="input" name="phone" maxLength={40} autoComplete="tel" />
      </label>

      <div className="split">
        <label className="stack-sm">
          <span className="small muted">Program</span>
          <select className="input" name="programId" required defaultValue="">
            <option value="" disabled>
              Choose a program
            </option>
            {programs.map((program) => (
              <option key={program.id} value={program.id}>
                {program.credential} · {program.name}
              </option>
            ))}
          </select>
        </label>
        <label className="stack-sm">
          <span className="small muted">Term</span>
          <select className="input" name="term" required defaultValue={terms[0]?.value ?? ""}>
            {terms.map((term) => (
              <option key={term.value} value={term.value}>
                {term.label}
              </option>
            ))}
          </select>
        </label>
      </div>

      <label className="stack-sm">
        <span className="small muted">Goals statement</span>
        <textarea
          className="input"
          name="goals"
          rows={6}
          minLength={40}
          maxLength={4000}
          required
          placeholder="What you want to study, why now, and what you plan to do with it."
        />
        <span className="tiny muted">A few sentences is enough. This is read, not scored.</span>
      </label>

      <label className="stack-sm">
        <span className="small muted">Transcript — {TRANSCRIPT_HELP}</span>
        <input
          className="input"
          name="transcript"
          type="file"
          accept=".pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg"
          required
        />
        <span className="tiny muted">
          An unofficial copy is enough to start. Admissions asks for the official one before you register.
        </span>
      </label>

      {error && <span className="chip danger">{error}</span>}

      <button className="btn primary" type="submit" disabled={busy}>
        {busy ? "Sending…" : "Submit application"}
      </button>
      <span className="tiny muted">
        Submitted applications are readable only by the registrar who reviews admissions.
      </span>
    </form>
  );
}

"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { api } from "@/lib/client";
import type { Credential } from "@/lib/types";

type Kind = "course_certificate" | "track_credential" | "degree_conferral";

interface Props {
  learners: { id: string; name: string; email: string }[];
  courses: { key: string; label: string }[];
  tracks: { id: string; label: string }[];
  programs: { id: string; label: string }[];
  defaults: { learner: string; program: string; course: string };
  autoSign: boolean;
}

export function IssueCredentialForm({ learners, courses, tracks, programs, defaults, autoSign }: Props) {
  const router = useRouter();
  const initialKind: Kind = defaults.program ? "degree_conferral" : defaults.course ? "course_certificate" : "course_certificate";
  const [kind, setKind] = useState<Kind>(initialKind);
  const [subjectRef, setSubjectRef] = useState(
    initialKind === "degree_conferral" ? defaults.program : defaults.course,
  );
  const [learnerId, setLearnerId] = useState(defaults.learner);
  const [manual, setManual] = useState({ name: "", email: "" });
  const [grade, setGrade] = useState("");
  const [override, setOverride] = useState(false);
  const [sign, setSign] = useState(autoSign);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const subjects =
    kind === "course_certificate"
      ? courses.map((c) => ({ value: c.key, label: c.label }))
      : kind === "track_credential"
        ? tracks.map((t) => ({ value: t.id, label: t.label }))
        : programs.map((p) => ({ value: p.id, label: p.label }));

  function changeKind(next: Kind) {
    setKind(next);
    setSubjectRef("");
    setError(null);
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    const result = await api<Credential>("/api/credentials", {
      method: "POST",
      body: JSON.stringify({
        type: kind,
        subjectRef,
        learnerId: learnerId || undefined,
        learner: !learnerId && manual.email ? { name: manual.name, email: manual.email } : undefined,
        grade: grade || undefined,
        override,
        autoSign: sign,
      }),
    });
    setBusy(false);
    if (!result.ok || !result.data) {
      setError(result.error ?? "Could not create the award.");
      return;
    }
    router.push(`/credentials/${result.data.id}`);
  }

  return (
    <div className="card" id="issue">
      <div className="card-head">
        <div>
          <h2 className="card-title">Award a credential</h2>
          <div className="card-sub">Eligibility is checked against the LMS record before anything is signed.</div>
        </div>
      </div>
      <form onSubmit={submit} className="card-body stack">
        <div className="field">
          <label className="label">Award type</label>
          <div className="row" style={{ gap: 6 }}>
            {(
              [
                ["course_certificate", "Course certificate"],
                ["track_credential", "Track credential"],
                ["degree_conferral", "Degree conferral"],
              ] as [Kind, string][]
            ).map(([value, label]) => (
              <button
                key={value}
                type="button"
                className={`btn small${kind === value ? " primary" : ""}`}
                onClick={() => changeKind(value)}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        <div className="field">
          <label className="label" htmlFor="subject">
            {kind === "course_certificate" ? "Course" : kind === "track_credential" ? "Track" : "Program"}
          </label>
          <select
            id="subject"
            className="select"
            value={subjectRef}
            onChange={(e) => setSubjectRef(e.target.value)}
            required
          >
            <option value="">Select…</option>
            {subjects.map((subject) => (
              <option key={subject.value} value={subject.value}>
                {subject.label}
              </option>
            ))}
          </select>
        </div>

        <div className="field">
          <label className="label" htmlFor="learner">Learner</label>
          <select id="learner" className="select" value={learnerId} onChange={(e) => setLearnerId(e.target.value)}>
            <option value="">New learner…</option>
            {learners.map((learner) => (
              <option key={learner.id} value={learner.id}>
                {learner.name} — {learner.email}
              </option>
            ))}
          </select>
        </div>

        {!learnerId && (
          <div className="form-grid">
            <div className="field">
              <label className="label">Name</label>
              <input
                className="input"
                value={manual.name}
                onChange={(e) => setManual((prev) => ({ ...prev, name: e.target.value }))}
                required
              />
            </div>
            <div className="field">
              <label className="label">Email</label>
              <input
                className="input"
                type="email"
                value={manual.email}
                onChange={(e) => setManual((prev) => ({ ...prev, email: e.target.value }))}
                required
              />
            </div>
          </div>
        )}

        <div className="field">
          <label className="label">Grade (optional)</label>
          <input
            className="input"
            value={grade}
            onChange={(e) => setGrade(e.target.value)}
            placeholder="Uses the LMS grade when left blank"
          />
        </div>

        <label className="checkbox">
          <input type="checkbox" checked={sign} onChange={(e) => setSign(e.target.checked)} />
          Sign through Signara now
        </label>
        <label className="checkbox">
          <input type="checkbox" checked={override} onChange={(e) => setOverride(e.target.checked)} />
          Override eligibility (registrar decision)
        </label>

        {error && (
          <div className="banner bad">
            <div>{error}</div>
          </div>
        )}

        <button className="btn primary" type="submit" disabled={busy || !subjectRef}>
          {busy ? "Submitting to Signara…" : sign ? "Create & sign" : "Stage award"}
        </button>
        <span className="tiny muted">
          {sign
            ? "The certificate is rendered, uploaded to Signara, signed by the configured signatory and issued."
            : "The award is rendered and held locally until you submit it for signing."}
        </span>
      </form>
    </div>
  );
}

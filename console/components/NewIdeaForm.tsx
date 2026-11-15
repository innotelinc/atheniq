"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { api } from "@/lib/client";
import type { GenSession } from "@/lib/types";

const EXAMPLES = [
  "A short course teaching clinic front-desk staff to use AI for patient intake without breaking HIPAA",
  "A practical course on reading a P&L for first-time managers with no finance background",
  "A capstone course where nursing students run a deteriorating-patient simulation and defend their decisions",
];

export function NewIdeaForm({
  configured,
  departments,
  defaultTerm,
}: {
  configured: boolean;
  departments: string[];
  defaultTerm: string;
}) {
  const router = useRouter();
  const [idea, setIdea] = useState("");
  const [audience, setAudience] = useState("");
  const [level, setLevel] = useState(100);
  const [credits, setCredits] = useState(3);
  const [department, setDepartment] = useState(departments[0] ?? "General Studies");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    const result = await api<{ session: GenSession; engine: string; modelError: string | null }>(
      "/api/generate",
      {
        method: "POST",
        body: JSON.stringify({ idea, audience, level, credits, department, term: defaultTerm }),
      },
    );
    setBusy(false);
    if (!result.ok || !result.data) {
      setError(result.error ?? "The studio could not draft that course.");
      return;
    }
    router.push(`/generate/${result.data.session.id}`);
  }

  return (
    <form onSubmit={submit} className="stack">
      <div className="field">
        <label className="label" htmlFor="idea">The idea</label>
        <textarea
          id="idea"
          className="textarea"
          style={{ minHeight: 110 }}
          value={idea}
          onChange={(e) => setIdea(e.target.value)}
          placeholder="What should this course make someone able to do?"
          required
          minLength={12}
        />
        <div className="row" style={{ gap: 6 }}>
          {EXAMPLES.map((example) => (
            <button
              key={example}
              type="button"
              className="btn small ghost"
              onClick={() => setIdea(example)}
            >
              {example.split(" ").slice(0, 4).join(" ")}…
            </button>
          ))}
        </div>
      </div>

      <div className="field">
        <label className="label" htmlFor="audience">Audience</label>
        <input
          id="audience"
          className="input"
          value={audience}
          onChange={(e) => setAudience(e.target.value)}
          placeholder="Who is this for? e.g. incumbent workers at Massachusetts employers"
        />
      </div>

      <div className="form-grid">
        <div className="field">
          <label className="label" htmlFor="department">Department</label>
          <select id="department" className="select" value={department} onChange={(e) => setDepartment(e.target.value)}>
            {departments.map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label className="label" htmlFor="level">Level</label>
          <select id="level" className="select" value={level} onChange={(e) => setLevel(Number(e.target.value))}>
            {[100, 200, 300, 400, 500].map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label className="label" htmlFor="credits">Credits</label>
          <input
            id="credits"
            className="input"
            type="number"
            min={1}
            max={6}
            value={credits}
            onChange={(e) => setCredits(Number(e.target.value))}
          />
        </div>
        <div className="field">
          <label className="label">Engine</label>
          <input className="input" value={configured ? "Model gateway" : "Curriculum rules"} readOnly />
          <span className="hint">{configured ? "Model drafts; rules catch failures." : "No model key — deterministic engine."}</span>
        </div>
      </div>

      {error && (
        <div className="banner bad">
          <div>{error}</div>
        </div>
      )}

      <button className="btn primary" type="submit" disabled={busy || idea.trim().length < 12}>
        {busy ? "Drafting the course…" : "Draft this course"}
      </button>
      <span className="tiny muted">
        Nothing is published by drafting. The course enters the catalog only when you accept it.
      </span>
    </form>
  );
}

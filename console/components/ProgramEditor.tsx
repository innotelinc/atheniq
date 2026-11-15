"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { api } from "@/lib/client";
import type { Program, Semester } from "@/lib/types";

interface Props {
  program: Program;
  programsUrl: string;
}

interface SemesterState {
  focus: string;
  credits: number;
  courses: string;
}

export function ProgramEditor({ program }: Props) {
  const router = useRouter();
  const [name, setName] = useState(program.name);
  const [credential, setCredential] = useState(program.credential);
  const [summary, setSummary] = useState(program.summary);
  const [totalCredits, setTotalCredits] = useState(program.totalCredits);
  const [perCredit, setPerCredit] = useState((program.tuitionPerCreditCents / 100).toFixed(2));
  const [status, setStatus] = useState(program.status);
  const [accreditation, setAccreditation] = useState(program.accreditation);
  const [semesters, setSemesters] = useState<SemesterState[]>(
    program.semesters.map((semester) => ({
      focus: semester.focus,
      credits: semester.credits,
      courses: semester.courses.map((c) => `${c.code} ${c.title}`).join("\n"),
    })),
  );
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ tone: "ok" | "bad"; text: string } | null>(null);

  function updateSemester(index: number, patch: Partial<SemesterState>) {
    setSemesters((prev) => prev.map((s, i) => (i === index ? { ...s, ...patch } : s)));
  }

  async function save() {
    setSaving(true);
    setMessage(null);
    const payload: Semester[] = semesters.map((semester, i) => ({
      number: i + 1,
      focus: semester.focus,
      credits: semester.credits,
      courses: semester.courses
        .split("\n")
        .map((line) => line.trim())
        .filter(Boolean)
        .map((line) => {
          const [code, ...rest] = line.split(/\s+/);
          return { code: code.toUpperCase(), title: rest.join(" ") || code };
        }),
    }));

    const result = await api<Program>(`/api/programs`, {
      method: "PATCH",
      body: JSON.stringify({
        id: program.id,
        name,
        credential,
        summary,
        totalCredits,
        tuitionPerCreditCents: Math.round(Number(perCredit) * 100) || 0,
        status,
        accreditation,
        semesters: payload,
      }),
    });
    setSaving(false);
    if (!result.ok) {
      setMessage({ tone: "bad", text: result.error ?? "Could not save the plan." });
      return;
    }
    setMessage({ tone: "ok", text: "Plan saved. The institute catalog is built from this record." });
    router.refresh();
  }

  const scheduled = semesters.reduce((n, s) => n + Number(s.credits || 0), 0);

  return (
    <div className="card">
      <div className="card-head">
        <div>
          <h2 className="card-title">Published plan</h2>
          <div className="card-sub">Semester structure, credit totals and the tuition the program bills.</div>
        </div>
        <span className={`chip ${scheduled === totalCredits ? "ok" : "warn"}`}>
          {scheduled} / {totalCredits} credits scheduled
        </span>
      </div>
      <div className="card-body stack">
        <div className="form-grid">
          <div className="field">
            <label className="label">Program name</label>
            <input className="input" value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="field">
            <label className="label">Credential conferred</label>
            <input className="input" value={credential} onChange={(e) => setCredential(e.target.value)} />
          </div>
          <div className="field">
            <label className="label">Total credits</label>
            <input
              className="input"
              type="number"
              min={1}
              value={totalCredits}
              onChange={(e) => setTotalCredits(Number(e.target.value))}
            />
          </div>
          <div className="field">
            <label className="label">Tuition per credit (USD)</label>
            <input className="input" type="number" min={0} step="0.01" value={perCredit} onChange={(e) => setPerCredit(e.target.value)} />
          </div>
          <div className="field">
            <label className="label">Status</label>
            <select className="select" value={status} onChange={(e) => setStatus(e.target.value as Program["status"])}>
              <option value="active">active</option>
              <option value="draft">draft</option>
              <option value="retired">retired</option>
            </select>
          </div>
          <div className="field">
            <label className="label">Accreditation statement</label>
            <input className="input" value={accreditation} onChange={(e) => setAccreditation(e.target.value)} />
          </div>
          <div className="field span-2">
            <label className="label">Summary</label>
            <textarea className="textarea" value={summary} onChange={(e) => setSummary(e.target.value)} />
          </div>
        </div>

        <div className="stack">
          <div className="between">
            <span className="label">Semester plan</span>
            <button
              type="button"
              className="btn small"
              onClick={() => setSemesters((prev) => [...prev, { focus: "New semester", credits: 15, courses: "" }])}
            >
              + Add semester
            </button>
          </div>
          {semesters.map((semester, index) => (
            <div className="module" key={index}>
              <div className="module-head">
                <div className="row" style={{ flex: 1 }}>
                  <span className="module-num">{index + 1}</span>
                  <input
                    className="input"
                    value={semester.focus}
                    onChange={(e) => updateSemester(index, { focus: e.target.value })}
                    aria-label={`Semester ${index + 1} focus`}
                  />
                  <input
                    className="input"
                    style={{ maxWidth: 90 }}
                    type="number"
                    min={0}
                    value={semester.credits}
                    onChange={(e) => updateSemester(index, { credits: Number(e.target.value) })}
                    aria-label="Credits"
                  />
                </div>
                <button
                  type="button"
                  className="btn small ghost"
                  onClick={() => setSemesters((prev) => prev.filter((_, i) => i !== index))}
                >
                  Remove
                </button>
              </div>
              <div style={{ padding: "10px 15px" }}>
                <textarea
                  className="textarea mono"
                  style={{ minHeight: 74, fontSize: 12 }}
                  value={semester.courses}
                  onChange={(e) => updateSemester(index, { courses: e.target.value })}
                  placeholder={"BUS101 Introduction to Business\nACCT201 Financial Accounting"}
                  aria-label={`Semester ${index + 1} courses`}
                />
                <span className="hint">One course per line: CODE Title.</span>
              </div>
            </div>
          ))}
        </div>

        {message && (
          <div className={`banner ${message.tone === "ok" ? "ok" : "bad"}`}>
            <div>{message.text}</div>
          </div>
        )}
      </div>
      <div className="card-foot">
        <div className="between">
          <span className="small muted">
            Tuition for the full program: ${((Number(perCredit) || 0) * totalCredits).toLocaleString("en-US")}
          </span>
          <button className="btn primary" type="button" onClick={save} disabled={saving}>
            {saving ? "Saving…" : "Save plan"}
          </button>
        </div>
      </div>
    </div>
  );
}

"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { api } from "@/lib/client";
import type { Course } from "@/lib/types";

interface Props {
  departments: string[];
  programs: { id: string; label: string }[];
  tracks: { id: string; label: string }[];
  terms: string[];
  defaultTerm: string;
  suggestedCode: string;
  creditsPerCourse: number;
}

export function CourseNewForm({ departments, programs, tracks, terms, defaultTerm, suggestedCode, creditsPerCourse }: Props) {
  const router = useRouter();
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState({
    title: "",
    code: suggestedCode,
    department: departments.includes("Applied AI") ? "Applied AI" : departments[0] ?? "General Studies",
    term: defaultTerm,
    credits: creditsPerCourse,
    level: 100,
    plan: "premium",
    amountCents: "",
    summary: "",
    description: "",
    outcomes: "",
    audience: "",
    prerequisites: "",
    programId: "",
    trackId: "",
  });

  function set<K extends keyof typeof form>(key: K, value: (typeof form)[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    const result = await api<Course>("/api/courses", {
      method: "POST",
      body: JSON.stringify({
        title: form.title,
        code: form.code,
        department: form.department,
        term: form.term,
        credits: form.credits,
        level: form.level,
        plan: form.plan || null,
        amountCents: form.amountCents ? Math.round(Number(form.amountCents) * 100) : null,
        summary: form.summary,
        description: form.description || form.summary,
        outcomes: form.outcomes.split("\n").map((s) => s.trim()).filter(Boolean),
        audience: form.audience,
        prerequisites: form.prerequisites.split("\n").map((s) => s.trim()).filter(Boolean),
        programIds: form.programId ? [form.programId] : [],
        trackIds: form.trackId ? [form.trackId] : [],
      }),
    });
    setSaving(false);
    if (!result.ok || !result.data) {
      setError(result.error ?? "Could not create the course.");
      return;
    }
    router.push(`/courses/${result.data.id}`);
  }

  return (
    <form onSubmit={submit} className="card">
      <div className="card-body">
        <div className="form-grid">
          <div className="field span-2">
            <label className="label" htmlFor="title">Course title</label>
            <input
              id="title"
              className="input"
              value={form.title}
              onChange={(e) => set("title", e.target.value)}
              placeholder="e.g. Clinical Documentation with AI"
              required
            />
            <span className="hint">The catalog displays this after the course code.</span>
          </div>

          <div className="field">
            <label className="label" htmlFor="code">Course code</label>
            <input
              id="code"
              className="input"
              value={form.code}
              onChange={(e) => set("code", e.target.value.toUpperCase())}
              pattern="[A-Za-z]{2,8}[0-9]{2,4}"
              required
            />
            <span className="hint">2–8 letters, then 2–4 digits — e.g. HCA201.</span>
          </div>

          <div className="field">
            <label className="label" htmlFor="department">Department</label>
            <select
              id="department"
              className="select"
              value={form.department}
              onChange={(e) => set("department", e.target.value)}
            >
              {departments.map((department) => (
                <option key={department} value={department}>
                  {department}
                </option>
              ))}
            </select>
          </div>

          <div className="field">
            <label className="label" htmlFor="term">Term</label>
            <select id="term" className="select" value={form.term} onChange={(e) => set("term", e.target.value)}>
              {Array.from(new Set([...terms, form.term])).map((term) => (
                <option key={term} value={term}>
                  {term}
                </option>
              ))}
            </select>
            <span className="hint">Part of the runtime key: course-v1:ORG+CODE+TERM.</span>
          </div>

          <div className="field">
            <label className="label" htmlFor="credits">Credits</label>
            <input
              id="credits"
              className="input"
              type="number"
              min={1}
              max={6}
              value={form.credits}
              onChange={(e) => set("credits", Number(e.target.value))}
            />
          </div>

          <div className="field">
            <label className="label" htmlFor="level">Level</label>
            <select
              id="level"
              className="select"
              value={form.level}
              onChange={(e) => set("level", Number(e.target.value))}
            >
              {[100, 200, 300, 400, 500].map((level) => (
                <option key={level} value={level}>
                  {level}
                </option>
              ))}
            </select>
          </div>

          <div className="field">
            <label className="label" htmlFor="plan">Access plan</label>
            <select id="plan" className="select" value={form.plan} onChange={(e) => set("plan", e.target.value)}>
              <option value="premium">premium — Magnate entitlement</option>
              <option value="standard">standard</option>
              <option value="">Free</option>
            </select>
          </div>

          <div className="field">
            <label className="label" htmlFor="amount">One-off price (USD, optional)</label>
            <input
              id="amount"
              className="input"
              type="number"
              min={0}
              step="0.01"
              value={form.amountCents}
              onChange={(e) => set("amountCents", e.target.value)}
              placeholder="e.g. 49.00"
            />
            <span className="hint">Leave blank to gate on the plan instead.</span>
          </div>

          <div className="field">
            <label className="label" htmlFor="program">Degree program</label>
            <select
              id="program"
              className="select"
              value={form.programId}
              onChange={(e) => set("programId", e.target.value)}
            >
              <option value="">Not on a program</option>
              {programs.map((program) => (
                <option key={program.id} value={program.id}>
                  {program.label}
                </option>
              ))}
            </select>
          </div>

          <div className="field">
            <label className="label" htmlFor="track">Workforce track</label>
            <select id="track" className="select" value={form.trackId} onChange={(e) => set("trackId", e.target.value)}>
              <option value="">Not on a track</option>
              {tracks.map((track) => (
                <option key={track.id} value={track.id}>
                  {track.label}
                </option>
              ))}
            </select>
          </div>

          <div className="field span-2">
            <label className="label" htmlFor="summary">Catalog summary</label>
            <textarea
              id="summary"
              className="textarea"
              value={form.summary}
              onChange={(e) => set("summary", e.target.value)}
              placeholder="One or two sentences that will appear on the catalog card and the course about page."
            />
          </div>

          <div className="field span-2">
            <label className="label" htmlFor="description">Description</label>
            <textarea
              id="description"
              className="textarea"
              value={form.description}
              onChange={(e) => set("description", e.target.value)}
              placeholder="The longer overview shown on the course page. Leave blank to reuse the summary."
            />
          </div>

          <div className="field">
            <label className="label" htmlFor="outcomes">Learning outcomes (one per line)</label>
            <textarea
              id="outcomes"
              className="textarea"
              value={form.outcomes}
              onChange={(e) => set("outcomes", e.target.value)}
              placeholder={"Explain …\nApply …\nJudge …"}
            />
          </div>

          <div className="field">
            <label className="label" htmlFor="prerequisites">Prerequisites (one per line)</label>
            <textarea
              id="prerequisites"
              className="textarea"
              value={form.prerequisites}
              onChange={(e) => set("prerequisites", e.target.value)}
              placeholder="None"
            />
          </div>

          <div className="field span-2">
            <label className="label" htmlFor="audience">Audience</label>
            <input
              id="audience"
              className="input"
              value={form.audience}
              onChange={(e) => set("audience", e.target.value)}
              placeholder="Working adults and career changers"
            />
          </div>
        </div>

        {error && (
          <div className="banner bad mt">
            <div>
              <div className="banner-title">Could not create the course</div>
              {error}
            </div>
          </div>
        )}
      </div>

      <div className="card-foot">
        <div className="between">
          <span className="small muted">
            The course is created as a draft; the curriculum editor opens next.
          </span>
          <div className="row">
            <button className="btn" type="button" onClick={() => history.back()} disabled={saving}>
              Cancel
            </button>
            <button className="btn primary" type="submit" disabled={saving}>
              {saving ? "Creating…" : "Create course"}
            </button>
          </div>
        </div>
      </div>
    </form>
  );
}

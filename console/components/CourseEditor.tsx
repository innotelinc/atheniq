"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { api } from "@/lib/client";
import type { Course, CourseModule, LessonType } from "@/lib/types";

const LESSON_TYPES: LessonType[] = ["reading", "video", "lab", "discussion", "quiz", "project", "exam"];

interface Props {
  course: Course;
  programs: { id: string; label: string }[];
  tracks: { id: string; label: string }[];
  terms: string[];
}

type Tab = "overview" | "curriculum" | "placement";

export function CourseEditor({ course, programs, tracks, terms }: Props) {
  const router = useRouter();
  const [tab, setTab] = useState<Tab>("overview");
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ tone: "ok" | "bad"; text: string } | null>(null);

  const [title, setTitle] = useState(course.title.replace(`${course.code} — `, ""));
  const [summary, setSummary] = useState(course.summary);
  const [description, setDescription] = useState(course.description);
  const [audience, setAudience] = useState(course.audience);
  const [outcomes, setOutcomes] = useState(course.outcomes.join("\n"));
  const [prerequisites, setPrerequisites] = useState(course.prerequisites.join("\n"));
  const [credits, setCredits] = useState(course.credits);
  const [level, setLevel] = useState(course.level);
  const [department, setDepartment] = useState(course.department);
  const [term, setTerm] = useState(course.term);
  const [modules, setModules] = useState<CourseModule[]>(course.modules);
  const [plan, setPlan] = useState(course.price.plan ?? "");
  const [amount, setAmount] = useState(
    course.price.amountCents ? (course.price.amountCents / 100).toFixed(2) : "",
  );
  const [programIds, setProgramIds] = useState<string[]>(course.programIds);
  const [trackIds, setTrackIds] = useState<string[]>(course.trackIds);

  function updateModule(index: number, patch: Partial<CourseModule>) {
    setModules((prev) => prev.map((module, i) => (i === index ? { ...module, ...patch } : module)));
  }

  function addModule() {
    setModules((prev) => [
      ...prev,
      {
        id: `m${prev.length + 1}`,
        title: `Module ${prev.length + 1}`,
        summary: "",
        assessment: "Module problem set (graded)",
        lessons: [
          { id: `m${prev.length + 1}-l1`, title: "Lesson 1", type: "reading", minutes: 45 },
        ],
      },
    ]);
  }

  function addLesson(moduleIndex: number) {
    setModules((prev) =>
      prev.map((module, i) =>
        i === moduleIndex
          ? {
              ...module,
              lessons: [
                ...module.lessons,
                {
                  id: `${module.id}-l${module.lessons.length + 1}`,
                  title: `Lesson ${module.lessons.length + 1}`,
                  type: "reading" as LessonType,
                  minutes: 45,
                },
              ],
            }
          : module,
      ),
    );
  }

  async function save() {
    setSaving(true);
    setMessage(null);
    const result = await api<Course>(`/api/courses/${course.id}`, {
      method: "PATCH",
      body: JSON.stringify({
        title,
        summary,
        description,
        audience,
        credits,
        level,
        department,
        term,
        outcomes: outcomes.split("\n").map((s) => s.trim()).filter(Boolean),
        prerequisites: prerequisites.split("\n").map((s) => s.trim()).filter(Boolean),
        modules,
        plan: plan || null,
        amountCents: amount ? Math.round(Number(amount) * 100) : null,
        programIds,
        trackIds,
      }),
    });
    setSaving(false);
    if (!result.ok) {
      setMessage({ tone: "bad", text: result.error ?? "Could not save." });
      return;
    }
    setMessage({ tone: "ok", text: "Saved. The record and the curriculum are up to date." });
    router.refresh();
  }

  return (
    <div className="card">
      <div className="card-head" style={{ paddingBottom: 0, borderBottom: "none" }}>
        <div>
          <h2 className="card-title">Course record</h2>
          <div className="card-sub">Everything the catalog, the LMS package and the syllabus are built from.</div>
        </div>
        <span className="chip plain muted">
          {modules.length} modules · {modules.reduce((n, m) => n + m.lessons.length, 0)} lessons
        </span>
      </div>

      <div className="tabs" style={{ padding: "0 18px", marginBottom: 0 }}>
        {([
          ["overview", "Overview"],
          ["curriculum", "Curriculum"],
          ["placement", "Price & placement"],
        ] as [Tab, string][]).map(([value, label]) => (
          <button
            key={value}
            type="button"
            className={`tab${tab === value ? " active" : ""}`}
            onClick={() => setTab(value)}
          >
            {label}
          </button>
        ))}
      </div>

      <div className="card-body">
        {tab === "overview" && (
          <div className="form-grid">
            <div className="field span-2">
              <label className="label">Title</label>
              <input className="input" value={title} onChange={(e) => setTitle(e.target.value)} />
            </div>
            <div className="field span-2">
              <label className="label">Catalog summary</label>
              <textarea className="textarea" value={summary} onChange={(e) => setSummary(e.target.value)} />
              <span className="hint">{summary.length} characters — the catalog needs 40 or more.</span>
            </div>
            <div className="field span-2">
              <label className="label">Description</label>
              <textarea
                className="textarea"
                style={{ minHeight: 130 }}
                value={description}
                onChange={(e) => setDescription(e.target.value)}
              />
            </div>
            <div className="field">
              <label className="label">Department</label>
              <input className="input" value={department} onChange={(e) => setDepartment(e.target.value)} />
            </div>
            <div className="field">
              <label className="label">Audience</label>
              <input className="input" value={audience} onChange={(e) => setAudience(e.target.value)} />
            </div>
            <div className="field">
              <label className="label">Credits</label>
              <input
                className="input"
                type="number"
                min={1}
                max={6}
                value={credits}
                onChange={(e) => setCredits(Number(e.target.value))}
              />
            </div>
            <div className="field">
              <label className="label">Level</label>
              <select className="select" value={level} onChange={(e) => setLevel(Number(e.target.value) as Course["level"])}>
                {[100, 200, 300, 400, 500].map((value) => (
                  <option key={value} value={value}>
                    {value}
                  </option>
                ))}
              </select>
            </div>
            <div className="field">
              <label className="label">Term</label>
              <select className="select" value={term} onChange={(e) => setTerm(e.target.value)}>
                {Array.from(new Set([...terms, term])).map((value) => (
                  <option key={value} value={value}>
                    {value}
                  </option>
                ))}
              </select>
              <span className="hint">Changing the term changes the runtime key.</span>
            </div>
            <div className="field">
              <label className="label">Outcomes (one per line)</label>
              <textarea
                className="textarea"
                value={outcomes}
                onChange={(e) => setOutcomes(e.target.value)}
              />
            </div>
            <div className="field">
              <label className="label">Prerequisites (one per line)</label>
              <textarea
                className="textarea"
                value={prerequisites}
                onChange={(e) => setPrerequisites(e.target.value)}
              />
            </div>
          </div>
        )}

        {tab === "curriculum" && (
          <div className="stack">
            {modules.map((module, index) => (
              <div className="module" key={module.id}>
                <div className="module-head">
                  <div className="row" style={{ flex: 1 }}>
                    <span className="module-num">{index + 1}</span>
                    <input
                      className="input"
                      value={module.title}
                      onChange={(e) => updateModule(index, { title: e.target.value })}
                      aria-label={`Module ${index + 1} title`}
                    />
                  </div>
                  <button
                    type="button"
                    className="btn small ghost"
                    onClick={() => setModules((prev) => prev.filter((_, i) => i !== index))}
                  >
                    Remove
                  </button>
                </div>
                <div style={{ padding: "12px 15px" }}>
                  <div className="field">
                    <label className="label">Module summary</label>
                    <textarea
                      className="textarea"
                      style={{ minHeight: 60 }}
                      value={module.summary}
                      onChange={(e) => updateModule(index, { summary: e.target.value })}
                    />
                  </div>
                  <div className="field mt-sm">
                    <label className="label">Assessment</label>
                    <input
                      className="input"
                      value={module.assessment}
                      onChange={(e) => updateModule(index, { assessment: e.target.value })}
                    />
                  </div>
                </div>
                {module.lessons.map((lesson, lessonIndex) => (
                  <div className="lesson" key={lesson.id}>
                    <select
                      className="select"
                      style={{ maxWidth: 120 }}
                      value={lesson.type}
                      aria-label="Lesson type"
                      onChange={(e) =>
                        updateModule(index, {
                          lessons: module.lessons.map((l, i) =>
                            i === lessonIndex ? { ...l, type: e.target.value as LessonType } : l,
                          ),
                        })
                      }
                    >
                      {LESSON_TYPES.map((type) => (
                        <option key={type} value={type}>
                          {type}
                        </option>
                      ))}
                    </select>
                    <input
                      className="input"
                      value={lesson.title}
                      aria-label="Lesson title"
                      onChange={(e) =>
                        updateModule(index, {
                          lessons: module.lessons.map((l, i) =>
                            i === lessonIndex ? { ...l, title: e.target.value } : l,
                          ),
                        })
                      }
                    />
                    <input
                      className="input"
                      style={{ maxWidth: 82 }}
                      type="number"
                      min={5}
                      max={360}
                      value={lesson.minutes}
                      aria-label="Minutes"
                      onChange={(e) =>
                        updateModule(index, {
                          lessons: module.lessons.map((l, i) =>
                            i === lessonIndex ? { ...l, minutes: Number(e.target.value) } : l,
                          ),
                        })
                      }
                    />
                    <button
                      type="button"
                      className="btn small ghost"
                      aria-label="Remove lesson"
                      onClick={() =>
                        updateModule(index, {
                          lessons: module.lessons.filter((_, i) => i !== lessonIndex),
                        })
                      }
                    >
                      ×
                    </button>
                  </div>
                ))}
                <div className="lesson" style={{ background: "var(--surface-2)" }}>
                  <button type="button" className="btn small ghost" onClick={() => addLesson(index)}>
                    + Add lesson
                  </button>
                </div>
              </div>
            ))}
            <button type="button" className="btn" onClick={addModule}>
              + Add module
            </button>
          </div>
        )}

        {tab === "placement" && (
          <div className="stack">
            <div className="form-grid">
              <div className="field">
                <label className="label">Access plan</label>
                <select className="select" value={plan} onChange={(e) => setPlan(e.target.value)}>
                  <option value="premium">premium — Magnate entitlement</option>
                  <option value="standard">standard</option>
                  <option value="">Free</option>
                </select>
              </div>
              <div className="field">
                <label className="label">One-off price (USD)</label>
                <input
                  className="input"
                  type="number"
                  min={0}
                  step="0.01"
                  value={amount}
                  onChange={(e) => setAmount(e.target.value)}
                  placeholder="blank = plan only"
                />
              </div>
            </div>

            <div className="field">
              <label className="label">Degree programs</label>
              <div className="stack-sm">
                {programs.map((program) => (
                  <label className="checkbox" key={program.id}>
                    <input
                      type="checkbox"
                      checked={programIds.includes(program.id)}
                      onChange={(e) =>
                        setProgramIds((prev) =>
                          e.target.checked ? [...prev, program.id] : prev.filter((id) => id !== program.id),
                        )
                      }
                    />
                    {program.label}
                  </label>
                ))}
              </div>
            </div>

            <div className="field">
              <label className="label">Workforce tracks</label>
              <div className="stack-sm">
                {tracks.map((track) => (
                  <label className="checkbox" key={track.id}>
                    <input
                      type="checkbox"
                      checked={trackIds.includes(track.id)}
                      onChange={(e) =>
                        setTrackIds((prev) =>
                          e.target.checked ? [...prev, track.id] : prev.filter((id) => id !== track.id),
                        )
                      }
                    />
                    {track.label}
                  </label>
                ))}
              </div>
              <span className="hint">Track membership is written into config/workforce-tracks.json on publish.</span>
            </div>
          </div>
        )}

        {message && (
          <div className={`banner ${message.tone === "ok" ? "ok" : "bad"} mt`}>
            <div>{message.text}</div>
          </div>
        )}
      </div>

      <div className="card-foot">
        <div className="between">
          <span className="small muted">Saving updates the catalog record and the generated OLX package.</span>
          <button className="btn primary" type="button" onClick={save} disabled={saving}>
            {saving ? "Saving…" : "Save changes"}
          </button>
        </div>
      </div>
    </div>
  );
}

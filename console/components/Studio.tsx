"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/client";
import { draftIssues } from "@/lib/curriculum";
import type { Course, GenSession } from "@/lib/types";

interface Props {
  session: GenSession;
  programs: { id: string; label: string }[];
  tracks: { id: string; label: string }[];
  terms: string[];
  modelName: string;
}

const QUICK = [
  "Make it more practical, with a lab in every module",
  "Add a compliance and evidence module",
  "Make it shorter — 2 credits",
  "Raise it to 400 level and add a capstone",
  "Add more formative quizzes",
  "Rewrite it for first-line supervisors",
];

export function Studio({ session: initialSession, programs, tracks, terms, modelName }: Props) {
  const router = useRouter();
  const [session, setSession] = useState<GenSession>(initialSession);
  const [instruction, setInstruction] = useState("");
  const [busy, setBusy] = useState(false);
  const [accepting, setAccepting] = useState(false);
  const [publishNow, setPublishNow] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [accept, setAccept] = useState({
    code: initialSession.draft?.code ?? "",
    term: initialSession.term,
    plan: "premium",
    programId: "",
    trackId: "",
  });
  const chatRef = useRef<HTMLDivElement>(null);

  const draft = session.draft;
  const issues = draft ? draftIssues(draft) : ["No draft yet."];

  useEffect(() => {
    chatRef.current?.scrollTo({ top: chatRef.current.scrollHeight, behavior: "smooth" });
  }, [session.messages.length]);

  async function refine(event: React.FormEvent) {
    event.preventDefault();
    const text = instruction.trim();
    if (text.length < 3) return;
    setBusy(true);
    setError(null);
    const result = await api<{ session: GenSession; engine: string; modelError: string | null }>(
      `/api/generate/${session.id}/message`,
      { method: "POST", body: JSON.stringify({ instruction: text }) },
    );
    setBusy(false);
    if (!result.ok || !result.data) {
      setError(result.error ?? "The revision failed.");
      return;
    }
    setSession(result.data.session);
    setInstruction("");
  }

  async function acceptDraft() {
    setAccepting(true);
    setError(null);
    const result = await api<{ course: Course }>(`/api/generate/${session.id}/accept`, {
      method: "POST",
      body: JSON.stringify({ ...accept, publishNow }),
    });
    setAccepting(false);
    if (!result.ok || !result.data) {
      setError(result.error ?? "Could not accept the draft.");
      return;
    }
    router.push(`/courses/${result.data.course.id}`);
  }

  return (
    <div className="stack">
      <div className="page-head" style={{ marginBottom: 4 }}>
        <div>
          <div className="eyebrow">Course studio session</div>
          <h1 className="page-title">{draft?.title ?? "Untitled draft"}</h1>
          <div className="page-sub">{session.idea}</div>
        </div>
        <div className="row">
          <span className={`chip ${session.engine === "model" ? "ok" : "warn"}`}>
            {session.engine === "model" ? `Drafted by ${modelName}` : "Curriculum rules engine"}
          </span>
          <span className="chip plain muted">{session.versions.length} versions</span>
          <span className="chip plain muted">{session.credits} credits</span>
        </div>
      </div>

      <div className="studio">
        <div className="card">
          <div className="card-head">
            <div>
              <h2 className="card-title">Refine the course</h2>
              <div className="card-sub">Every instruction produces a versioned revision of the whole course.</div>
            </div>
          </div>
          <div className="card-body">
            <div className="chat" ref={chatRef}>
              {session.messages.map((message) => (
                <div className={`msg ${message.role}`} key={message.id}>
                  <div className="msg-role">
                    {message.role === "user" ? "You" : message.engine === "model" ? "Studio · model" : "Studio · rules"}
                  </div>
                  <div style={{ whiteSpace: "pre-wrap" }}>{message.content}</div>
                  {message.changes && message.changes.length > 0 && (
                    <div className="changes">
                      <strong>Changes</strong>
                      <ul style={{ margin: "4px 0 0" }}>
                        {message.changes.map((change, i) => (
                          <li key={i}>{change}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              ))}
              {busy && (
                <div className="msg assistant">
                  <div className="msg-role">Studio</div>
                  Applying the revision…
                </div>
              )}
            </div>

            <form onSubmit={refine} className="composer">
              <textarea
                className="textarea"
                value={instruction}
                onChange={(e) => setInstruction(e.target.value)}
                placeholder="What should change? e.g. “make it practical and add a compliance module”"
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    refine(e as unknown as React.FormEvent);
                  }
                }}
              />
              <button className="btn primary" type="submit" disabled={busy || instruction.trim().length < 3}>
                {busy ? "…" : "Revise"}
              </button>
            </form>

            <div className="row" style={{ gap: 6, marginTop: 10 }}>
              {QUICK.map((quick) => (
                <button
                  key={quick}
                  type="button"
                  className="btn small ghost"
                  onClick={() => setInstruction(quick)}
                  disabled={busy}
                >
                  {quick}
                </button>
              ))}
            </div>

            {error && (
              <div className="banner bad mt">
                <div>{error}</div>
              </div>
            )}
          </div>
        </div>

        <div className="stack">
          {draft && (
            <div className="draft-panel">
              <div className="card-head">
                <div>
                  <h2 className="card-title">Draft</h2>
                  <div className="card-sub">
                    {draft.modules.length} modules ·{" "}
                    {draft.modules.reduce((n, m) => n + m.lessons.length, 0)} lessons · level {draft.level} ·{" "}
                    {draft.credits} credits
                  </div>
                </div>
                <span className="chip plain muted">{draft.department}</span>
              </div>
              <div className="card-body stack-sm" style={{ maxHeight: "46vh", overflowY: "auto" }}>
                <p className="small">{draft.summary}</p>
                <div className="stack-sm">
                  {draft.modules.map((module, i) => (
                    <div key={module.id} className="module">
                      <div className="module-head">
                        <div className="row">
                          <span className="module-num">{i + 1}</span>
                          <span className="strong small">{module.title}</span>
                        </div>
                        <span className="tiny muted">{module.lessons.length} lessons</span>
                      </div>
                      {module.lessons.map((lesson) => (
                        <div className="lesson" key={lesson.id}>
                          <span className={`lesson-type ${lesson.type}`}>{lesson.type}</span>
                          <span className="small">{lesson.title}</span>
                          <span className="right tiny muted">{lesson.minutes}m</span>
                        </div>
                      ))}
                      <div className="lesson" style={{ background: "var(--surface-2)" }}>
                        <span className="tiny muted">Assessment: {module.assessment}</span>
                      </div>
                    </div>
                  ))}
                </div>
                <div className="mt-sm">
                  <div className="label">Grading</div>
                  <div className="stack-sm" style={{ marginTop: 4 }}>
                    {draft.grading.map((component) => (
                      <div className="between small" key={component.component}>
                        <span>{component.component}</span>
                        <span className="muted">{component.weight}%</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              <div className="card-foot">
                {session.courseId ? (
                  <span className="small">Accepted into the catalog.</span>
                ) : (
                  <div className="stack-sm">
                    <div className="label">Accept into the catalog</div>
                    {issues.length > 0 && (
                      <div className="banner bad">
                        <div>{issues.join(" ")}</div>
                      </div>
                    )}
                    <div className="form-grid" style={{ gap: 8 }}>
                      <div className="field">
                        <label className="label">Code</label>
                        <input
                          className="input"
                          value={accept.code}
                          onChange={(e) => setAccept((prev) => ({ ...prev, code: e.target.value.toUpperCase() }))}
                        />
                      </div>
                      <div className="field">
                        <label className="label">Term</label>
                        <select
                          className="select"
                          value={accept.term}
                          onChange={(e) => setAccept((prev) => ({ ...prev, term: e.target.value }))}
                        >
                          {Array.from(new Set([...terms, accept.term])).map((term) => (
                            <option key={term} value={term}>
                              {term}
                            </option>
                          ))}
                        </select>
                      </div>
                      <div className="field">
                        <label className="label">Access</label>
                        <select
                          className="select"
                          value={accept.plan}
                          onChange={(e) => setAccept((prev) => ({ ...prev, plan: e.target.value }))}
                        >
                          <option value="premium">premium</option>
                          <option value="standard">standard</option>
                          <option value="">Free</option>
                        </select>
                      </div>
                      <div className="field">
                        <label className="label">Program (optional)</label>
                        <select
                          className="select"
                          value={accept.programId}
                          onChange={(e) => setAccept((prev) => ({ ...prev, programId: e.target.value }))}
                        >
                          <option value="">None</option>
                          {programs.map((program) => (
                            <option key={program.id} value={program.id}>
                              {program.label}
                            </option>
                          ))}
                        </select>
                      </div>
                      <div className="field span-2">
                        <label className="label">Track (optional)</label>
                        <select
                          className="select"
                          value={accept.trackId}
                          onChange={(e) => setAccept((prev) => ({ ...prev, trackId: e.target.value }))}
                        >
                          <option value="">None</option>
                          {tracks.map((track) => (
                            <option key={track.id} value={track.id}>
                              {track.label}
                            </option>
                          ))}
                        </select>
                      </div>
                    </div>
                    <label className="checkbox">
                      <input
                        type="checkbox"
                        checked={publishNow}
                        onChange={(e) => setPublishNow(e.target.checked)}
                      />
                      Publish immediately once the checks pass
                    </label>
                    <button
                      className="btn primary block"
                      type="button"
                      onClick={acceptDraft}
                      disabled={accepting || issues.length > 0}
                    >
                      {accepting
                        ? "Adding to the catalog…"
                        : publishNow
                          ? "Accept & publish"
                          : "Accept as a draft course"}
                    </button>
                    <span className="tiny muted">
                      You can still edit the curriculum, price and placement after accepting.
                    </span>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

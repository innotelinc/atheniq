"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { api } from "@/lib/client";
import type { Course, PublishManifest } from "@/lib/types";

interface Check {
  id: string;
  label: string;
  ok: boolean;
  detail: string;
}

interface ValidateResponse {
  mode: string;
  manifest: PublishManifest;
  blocking: string[];
  warnings: string[];
}

interface PublishResponse {
  course: Course;
  bundle: string;
  lms: { attempted: boolean; ok: boolean; status: number | null; detail: string };
  files: { path: string; bytes: number }[];
  checks: Check[];
  catalogPatches: number;
}

export function PublishPanel({ course }: { course: Course }) {
  const router = useRouter();
  const [busy, setBusy] = useState<"validate" | "publish" | null>(null);
  const [checks, setChecks] = useState<Check[] | null>(null);
  const [blocking, setBlocking] = useState<string[]>([]);
  const [result, setResult] = useState<PublishResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showFiles, setShowFiles] = useState(false);

  async function validate() {
    setBusy("validate");
    setError(null);
    setResult(null);
    const response = await api<ValidateResponse>(`/api/courses/${course.id}/publish`, {
      method: "POST",
      body: JSON.stringify({ mode: "validate" }),
    });
    setBusy(null);
    if (!response.ok || !response.data) {
      setError(response.error ?? "Validation failed.");
      return;
    }
    setChecks(response.data.manifest.checks);
    setBlocking(response.data.blocking);
  }

  async function publish() {
    setBusy("publish");
    setError(null);
    const response = await api<PublishResponse>(`/api/courses/${course.id}/publish`, {
      method: "POST",
      body: JSON.stringify({ mode: "publish" }),
    });
    setBusy(null);
    if (!response.ok || !response.data) {
      setError(response.error ?? "Publishing failed.");
      const extra = (response as { blocking?: string[] }).blocking;
      if (Array.isArray(extra)) setBlocking(extra);
      return;
    }
    setResult(response.data);
    setChecks(response.data.checks);
    setBlocking([]);
    router.refresh();
  }

  return (
    <div className="card">
      <div className="card-head">
        <div>
          <h2 className="card-title">Publish</h2>
          <div className="card-sub">
            Builds the OLX package, writes the catalog patches, and lists the course on the sites.
          </div>
        </div>
        <span className={`chip ${course.status === "published" ? "ok" : "warn"}`}>
          {course.status === "published" ? "Live" : "Not live"}
        </span>
      </div>

      <div className="card-body stack">
        <div className="row">
          <button className="btn" type="button" onClick={validate} disabled={busy !== null}>
            {busy === "validate" ? "Checking…" : "Run checks"}
          </button>
          <button className="btn primary" type="button" onClick={publish} disabled={busy !== null}>
            {busy === "publish" ? "Publishing…" : course.status === "published" ? "Republish" : "Publish course"}
          </button>
        </div>

        {blocking.length > 0 && (
          <div className="banner bad">
            <div>
              <div className="banner-title">Blocking</div>
              {blocking.join(" · ")}
            </div>
          </div>
        )}

        {error && (
          <div className="banner bad">
            <div>{error}</div>
          </div>
        )}

        {checks && (
          <div>
            {checks.map((check) => (
              <div className={`check ${check.ok ? "ok" : "bad"}`} key={check.id}>
                <span className="check-mark">{check.ok ? "✓" : "!"}</span>
                <div>
                  <div className="strong small">{check.label}</div>
                  <div className="tiny muted">{check.detail}</div>
                </div>
              </div>
            ))}
          </div>
        )}

        {result && (
          <div className="stack-sm">
            <div className="banner ok">
              <div>
                <div className="banner-title">Published</div>
                {result.catalogPatches} catalog patch(es) written to <span className="mono">{result.bundle}</span>
              </div>
            </div>
            <div className={`banner ${result.lms.ok ? "ok" : ""}`}>
              <div>
                <div className="banner-title">
                  {result.lms.attempted
                    ? result.lms.ok
                      ? "LMS import accepted"
                      : "LMS import not accepted"
                    : "LMS import pending"}
                </div>
                {result.lms.detail}
              </div>
            </div>
            <div className="row">
              <a className="btn small" href={`/api/courses/${course.id}/bundle`}>
                Download OLX archive
              </a>
              <button className="btn small ghost" type="button" onClick={() => setShowFiles((v) => !v)}>
                {showFiles ? "Hide" : "Show"} {result.files.length} files
              </button>
            </div>
            {showFiles && (
              <div className="code-box">
                {result.files.map((file) => `${file.path}  (${file.bytes} B)`).join("\n")}
              </div>
            )}
          </div>
        )}

        {!checks && (
          <p className="small muted">
            Checks cover the runtime key, credits, curriculum, grading weights, price and catalog placement.
            Publishing is blocked until everything that matters passes.
          </p>
        )}
      </div>

      <div className="card-foot">
        <div className="stack-sm">
          <span className="small">
            Runtime key <span className="mono">{course.key}</span>
          </span>
          <span className="tiny muted">
            The archive is the same tar.gz the repo pipeline imports; the patches are merge-ready for
            config/course-prices.json, workforce-tracks.json and the program plans.
          </span>
        </div>
      </div>
    </div>
  );
}

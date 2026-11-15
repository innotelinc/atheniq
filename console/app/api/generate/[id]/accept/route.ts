import { getDb, logActivity, mutate, nowIso } from "@/lib/store";
import { buildManifest, writeBundle } from "@/lib/publish";
import { courseFromDraft, normaliseCode } from "@/lib/courses";
import { draftIssues } from "@/lib/curriculum";
import { fail, num, ok, str } from "@/lib/api";
import { currentActor } from "@/lib/current-staff";
import type { Course, GenSession } from "@/lib/types";

export const dynamic = "force-dynamic";

interface Body {
  code?: string;
  term?: string;
  plan?: string | null;
  amountCents?: number | null;
  programId?: string;
  trackId?: string;
  publishNow?: boolean;
}

export async function POST(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const body = (await request.json().catch(() => ({}))) as Body;

  const actor = await currentActor();
  const db = getDb();
  const session = db.sessions.find((s) => s.id === id);
  if (!session) return fail("Generation session not found.", 404);
  if (!session.draft) return fail("This session has no draft to accept.", 409);

  const issues = draftIssues(session.draft);
  if (issues.length) return fail(issues.join(" "), 422);

  const code = normaliseCode(str(body.code) || session.draft.code);
  if (!code) return fail("A course code is required.");
  const term = str(body.term) || session.term;

  if (db.courses.some((course) => course.code === code && course.term === term)) {
    return fail(`${code} already exists in ${term}. Pick another code.`);
  }

  const course = await mutate((database) => {
    const target = database.sessions.find((s) => s.id === id) as GenSession;
    const created = courseFromDraft(target.draft!, database, {
      code,
      term,
      price: {
        plan: body.plan === undefined ? "premium" : body.plan || null,
        amountCents: body.amountCents ?? null,
      },
      programIds: body.programId ? [body.programId] : [],
      trackIds: body.trackId ? [body.trackId] : [],
      generationId: target.id,
    });

    database.courses.push(created);

    if (body.programId) {
      const program = database.programs.find((p) => p.id === body.programId);
      if (program) {
        const semester = program.semesters[program.semesters.length - 1];
        if (semester && !semester.courses.some((c) => c.code === created.code)) {
          semester.courses.push({ code: created.code, title: created.title.replace(`${created.code} — `, "") });
        }
      }
    }
    if (body.trackId) {
      const track = database.tracks.find((t) => t.id === body.trackId);
      if (track && !track.courses.includes(created.key)) track.courses.push(created.key);
    }

    if (body.publishNow) {
      const manifest = buildManifest(created, database);
      if (manifest.blocking.length === 0) {
        writeBundle(created, manifest);
        created.status = "published";
        created.publishedAt = nowIso();
        created.updatedAt = created.publishedAt;
        logActivity(
          database,
          "course.published",
          `Published ${created.code} — ${created.title.replace(`${created.code} — `, "")} to the catalog`,
          created.key,
          actor,
        );
      }
    }

    target.courseId = created.id;
    target.updatedAt = nowIso();
    target.messages.push({
      id: `msg-${Date.now().toString(36)}`,
      role: "assistant",
      at: nowIso(),
      content: `Accepted into the catalog as **${created.code} — ${created.title.replace(`${created.code} — `, "")}** (${created.key}). It is a draft: open the course to review the curriculum and publish it.`,
    });

    logActivity(database, "course.created", `Accepted generated course ${created.code}`, created.key, actor);
    return created;
  });

  return ok({ course: course as Course }, 201);
}

import { getDb, logActivity, mutate, newId, nowIso } from "@/lib/store";
import { nextCourseCode } from "@/lib/courses";
import { synthesizeDraft } from "@/lib/curriculum";
import { generateWithModel } from "@/lib/ai";
import { num, ok, str } from "@/lib/api";
import { seedTerm } from "@/lib/term";
import { currentActor } from "@/lib/current-staff";
import type { GenSession } from "@/lib/types";

export const dynamic = "force-dynamic";

export async function GET() {
  const db = getDb();
  return ok(
    db.sessions.map((session) => ({
      id: session.id,
      idea: session.idea,
      engine: session.engine,
      title: session.draft?.title ?? null,
      courseId: session.courseId,
      updatedAt: session.updatedAt,
      messages: session.messages.length,
    })),
  );
}

interface Body {
  idea?: string;
  audience?: string;
  level?: number;
  credits?: number;
  department?: string;
  term?: string;
}

export async function POST(request: Request) {
  const body = (await request.json().catch(() => null)) as Body | null;
  const idea = str(body?.idea);
  if (!idea || idea.length < 12) {
    return ok(null, 400);
  }

  const actor = await currentActor();
  const db = getDb();
  const department = str(body?.department) || "General Studies";
  const levelNum = num(body?.level, 100);
  const level = ([100, 200, 300, 400, 500] as const).includes(levelNum as 100)
    ? (levelNum as 100 | 200 | 300 | 400 | 500)
    : 100;
  const credits = Math.min(6, Math.max(1, num(body?.credits, 3)));
  const term = str(body?.term) || db.settings.defaultTerm || seedTerm();

  const draft = synthesizeDraft({
    idea,
    audience: str(body?.audience),
    level,
    credits,
    department,
    code: nextCourseCode(db, department),
  });

  const generated = await generateWithModel(
    db.settings.ai,
    { idea, audience: str(body?.audience) || draft.audience, level, credits, department },
    draft,
  );

  const finalDraft = generated.draft ?? draft;
  const engine = generated.draft ? "model" : "rules";
  const at = nowIso();

  const session: GenSession = {
    id: newId("gen"),
    idea,
    audience: str(body?.audience) || draft.audience,
    level,
    credits,
    term,
    department,
    engine,
    draft: finalDraft,
    versions: [{ id: newId("v"), at, label: "Initial draft", draft: finalDraft }],
    messages: [
      {
        id: newId("msg"),
        role: "assistant",
        at,
        engine,
        content: generated.draft
          ? `Drafted **${finalDraft.title}** — ${finalDraft.modules.length} modules, ${finalDraft.modules.reduce((n, m) => n + m.lessons.length, 0)} lessons, ${finalDraft.credits} credits. Tell me what to change: length, rigour, audience, a module to add, the title, the assessment mix.`
          : `Drafted **${finalDraft.title}** — ${finalDraft.modules.length} modules, ${finalDraft.modules.reduce((n, m) => n + m.lessons.length, 0)} lessons, ${finalDraft.credits} credits.\n\nI built this with the curriculum rules engine${generated.error ? ` (${generated.error})` : " because no model gateway is configured"}. The structure is complete and publishable; tell me what to change and I will apply it.`,
      },
    ],
    courseId: null,
    createdAt: at,
    updatedAt: at,
  };

  await mutate((database) => {
    database.sessions.unshift(session);
    logActivity(database, "session.created", `Generated a draft for “${idea.slice(0, 60)}”`, session.id, actor);
  });

  return ok({ session, engine, modelError: generated.error }, 201);
}

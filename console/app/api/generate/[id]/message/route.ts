import { getDb, logActivity, mutate, newId, nowIso } from "@/lib/store";
import { reviseDraft } from "@/lib/curriculum";
import { reviseWithModel } from "@/lib/ai";
import { fail, ok, str } from "@/lib/api";
import { currentActor } from "@/lib/current-staff";
import type { GenSession } from "@/lib/types";

export const dynamic = "force-dynamic";

interface Body {
  instruction?: string;
}

export async function POST(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const body = (await request.json().catch(() => null)) as Body | null;
  const instruction = str(body?.instruction);
  if (instruction.length < 3) return fail("Tell me what to change first.");

  const actor = await currentActor();
  const db = getDb();
  const session = db.sessions.find((s) => s.id === id);
  if (!session) return fail("Generation session not found.", 404);
  if (!session.draft) return fail("This session has no draft yet.", 409);

  const rules = reviseDraft(session.draft, instruction);
  const modeled = await reviseWithModel(db.settings.ai, session.draft, instruction);
  const nextDraft = modeled.draft ?? rules.draft;
  const engine = modeled.draft ? "model" : "rules";
  const changes = modeled.draft
    ? [`Applied the instruction with ${db.settings.ai.model || "the configured model"}.`]
    : rules.changes;

  const at = nowIso();
  const before = session.draft;
  const delta = summarize(before, nextDraft);

  const updated = await mutate((database) => {
    const target = database.sessions.find((s) => s.id === id) as GenSession;
    target.draft = nextDraft;
    target.engine = engine;
    target.updatedAt = at;
    target.messages.push({
      id: newId("msg"),
      role: "user",
      at,
      content: instruction,
    });
    target.messages.push({
      id: newId("msg"),
      role: "assistant",
      at,
      engine,
      content: `Done. ${delta}`,
      changes,
    });
    target.versions.push({ id: newId("v"), at, label: instruction.slice(0, 80), draft: nextDraft });
    if (target.versions.length > 12) target.versions.splice(0, target.versions.length - 12);
    logActivity(database, "session.revised", `Revised “${nextDraft.title}”`, target.id, actor);
    return target;
  });

  return ok({ session: updated, engine, modelError: modeled.error });
}

function summarize(before: NonNullable<GenSession["draft"]>, after: NonNullable<GenSession["draft"]>): string {
  const notes: string[] = [];
  if (before.title !== after.title) notes.push(`Retitled to “${after.title}”.`);
  if (before.credits !== after.credits) notes.push(`${after.credits} credits.`);
  if (before.level !== after.level) notes.push(`Level ${after.level}.`);
  if (before.modules.length !== after.modules.length) {
    notes.push(`${after.modules.length} modules (was ${before.modules.length}).`);
  }
  const beforeLessons = before.modules.reduce((n, m) => n + m.lessons.length, 0);
  const afterLessons = after.modules.reduce((n, m) => n + m.lessons.length, 0);
  if (beforeLessons !== afterLessons) notes.push(`${afterLessons} lessons (was ${beforeLessons}).`);
  if (!notes.length) notes.push("Updated the draft — review the changes on the right.");
  return `${notes.join(" ")} The draft is ready to accept into the catalog whenever you are.`;
}

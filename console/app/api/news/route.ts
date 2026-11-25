import { NextResponse } from "next/server";
import { allowed, currentActor } from "@/lib/current-staff";
import { getDb, logActivity, mutate, newId, nowIso } from "@/lib/store";
import type { ActorRef } from "@/lib/types";

export const dynamic = "force-dynamic";

/**
 * Publishing news, and taking it back.
 *
 * A student portal that only lists courses is a transcript. News is how the
 * institute actually talks to a cohort — a term date, a fee deadline, a
 * registrar's notice — so posting one is a registrar action, same guard as
 * deciding a payment.
 */
export async function POST(request: Request) {
  const origin = new URL(request.url).origin;
  const back = (note: string) =>
    NextResponse.redirect(new URL(`/news?note=${encodeURIComponent(note)}`, origin), 303);

  if (!(await allowed("award"))) return back("Only a registrar can publish news.");

  let form: FormData;
  try {
    form = await request.formData();
  } catch {
    return back("That post could not be read.");
  }

  const action = String(form.get("action") ?? "create").trim();
  const actor = (await currentActor()) as ActorRef | null;
  const author = actor?.name ?? "The registry";

  if (action === "delete") {
    const id = String(form.get("id") ?? "").trim();
    if (!id) return back("That notice was not named.");
    const removed = await mutate((store) => {
      const before = (store.news ?? []).length;
      store.news = (store.news ?? []).filter((post) => post.id !== id);
      if (store.news.length === before) return null;
      logActivity(store, "news.published", `${author} withdrew a notice from student portals.`, id, actor);
      return store.news.length;
    });
    if (removed === null) return back("That notice is already gone.");
    return back("Notice withdrawn.");
  }

  const title = String(form.get("title") ?? "").trim();
  const body = String(form.get("body") ?? "").trim();
  const audience = String(form.get("audience") ?? "all").trim() || "all";
  const pinned = String(form.get("pinned") ?? "") === "on";

  if (title.length < 3) return back("A notice needs a title.");
  if (body.length < 3) return back("A notice needs something to say.");
  if (title.length > 140) return back("That title is too long for the portal.");

  // An audience must be the whole school or a program that exists; a stray id
  // would publish to nobody and look like a delivery bug.
  const db = getDb();
  if (audience !== "all" && !db.programs.some((program) => program.id === audience)) {
    return back("That cohort no longer exists.");
  }

  await mutate((store) => {
    store.news = store.news ?? [];
    store.news.unshift({
      id: newId("news"),
      title,
      body: body.slice(0, 4000),
      audience,
      pinned,
      publishedAt: nowIso(),
      author,
    });
    logActivity(store, "news.published", `${author} published “${title}” to student portals.`, audience, actor);
  });

  return back(`Published “${title}”.`);
}

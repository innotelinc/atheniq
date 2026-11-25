import { NextResponse } from "next/server";
import { allowed, currentActor } from "@/lib/current-staff";
import { getDb, logActivity, mutate, newId, nowIso } from "@/lib/store";
import type { ActorRef, Completion } from "@/lib/types";

export const dynamic = "force-dynamic";

/**
 * Record a final grade for one learner in one course.
 *
 * This is the registrar's own act, not a copy of the app's progress: a
 * completion is what a credential can be issued against, and it marks the
 * enrollment finished so the student sees it as done in the portal.
 */
export async function POST(request: Request) {
  const origin = new URL(request.url).origin;
  const toList = (note: string) =>
    NextResponse.redirect(new URL(`/students?note=${encodeURIComponent(note)}`, origin), 303);

  if (!(await allowed("award"))) return toList("Only a registrar can record a grade.");

  // A body that is absent or not a form is a bad request, not a crash.
  let form: FormData;
  try {
    form = await request.formData();
  } catch {
    return toList("That grade form could not be read.");
  }
  const learnerId = String(form.get("learnerId") ?? "").trim();
  const courseKey = String(form.get("courseKey") ?? "").trim();
  const grade = String(form.get("grade") ?? "").trim().slice(0, 20);
  const status = String(form.get("status") ?? "pass").trim() === "fail" ? "fail" : "pass";

  const destination = learnerId && learnerId.startsWith("lrn") ? `/students/${learnerId}` : "/students";
  const respond = (note: string) =>
    NextResponse.redirect(new URL(`${destination}?note=${encodeURIComponent(note)}`, origin), 303);

  if (!learnerId || !courseKey) return respond("A grade needs a learner and a course.");
  if (!grade) return respond("Enter the grade that was awarded.");

  const db = getDb();
  if (!db.learners.some((item) => item.id === learnerId)) return toList("That learner no longer exists.");
  const enrolled = db.enrollments.some(
    (item) => item.learnerId === learnerId && item.courseKey === courseKey,
  );
  if (!enrolled) return respond("That learner is not enrolled in that course.");

  const actor = (await currentActor()) as ActorRef | null;
  const name = actor?.name ?? "The console";
  const completedOn = nowIso().slice(0, 10);

  await mutate((store) => {
    const completion: Completion = {
      id: newId("comp"),
      learnerId,
      courseKey,
      grade,
      completedOn,
      status,
    };
    // Newest first, matching how the console lists everything else.
    store.completions.unshift(completion);

    const enrollment = store.enrollments.find(
      (item) => item.learnerId === learnerId && item.courseKey === courseKey,
    );
    if (enrollment) {
      // A pass finishes the course; a fail leaves it open to try again.
      if (status === "pass") enrollment.completedAt = completedOn;
      else enrollment.completedAt = null;
    }

    const learner = store.learners.find((item) => item.id === learnerId);
    logActivity(
      store,
      "learner.completed",
      `${name} recorded ${status === "pass" ? "a pass" : "a fail"} (${grade}) for ${learner?.name ?? "a learner"} in ${courseKey}.`,
      courseKey,
      actor,
    );
  });

  return respond(`${status === "pass" ? "Pass" : "Fail"} recorded for ${courseKey}.`);
}

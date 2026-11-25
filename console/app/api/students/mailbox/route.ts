import { NextResponse } from "next/server";
import { allowed, currentActor } from "@/lib/current-staff";
import { getDb, logActivity, mutate, nowIso } from "@/lib/store";
import type { ActorRef } from "@/lib/types";

export const dynamic = "force-dynamic";

/**
 * Reserving a student's @atheniq.institute address.
 *
 * The name is the part that has to be decided once: a graduate keeps their
 * institute address, so it is derived from the name they enrolled under and
 * never silently reused. Allocation is deliberately separate from mailbox
 * creation — the address is on the student's portal the moment a registrar
 * reserves it, and `status` says honestly whether mail can be delivered yet.
 */

const DOMAIN = (process.env.INSTITUTE_MAIL_DOMAIN || "atheniq.institute").trim();

function localPart(name: string): string {
  const cleaned = name
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, ".")
    .replace(/^\.+|\.+$/g, "")
    .slice(0, 40);
  return cleaned || "student";
}

export async function POST(request: Request) {
  const origin = new URL(request.url).origin;
  const toDefault = (note: string) =>
    NextResponse.redirect(new URL(`/students?note=${encodeURIComponent(note)}`, origin), 303);

  if (!(await allowed("award"))) return toDefault("Only a registrar can allocate an address.");

  let form: FormData;
  try {
    form = await request.formData();
  } catch {
    return toDefault("That request could not be read.");
  }

  const learnerId = String(form.get("learnerId") ?? "").trim();
  const backRaw = String(form.get("back") ?? "").trim();
  const destination = backRaw.startsWith("/students/") ? backRaw : "/students";
  const respond = (note: string) =>
    NextResponse.redirect(new URL(`${destination}?note=${encodeURIComponent(note)}`, origin), 303);

  if (!learnerId) return respond("That request did not name a student.");

  const db = getDb();
  if (!db.learners.some((learner) => learner.id === learnerId)) {
    return respond("That student no longer exists.");
  }

  const actor = (await currentActor()) as ActorRef | null;
  const by = actor?.name ?? "The registry";

  const result = await mutate((store) => {
    const learner = store.learners.find((item) => item.id === learnerId);
    if (!learner) return null;
    if (learner.mailbox) {
      return { address: learner.mailbox.address, already: true };
    }

    const taken = new Set(
      store.learners
        .map((item) => item.mailbox?.address?.split("@")[0]?.toLowerCase())
        .filter((value): value is string => Boolean(value)),
    );

    const base = localPart(learner.name);
    let candidate = base;
    for (let n = 2; taken.has(candidate); n += 1) candidate = `${base}${n}`;

    const address = `${candidate}@${DOMAIN}`;
    learner.mailbox = { address, status: "allocated", createdAt: nowIso() };
    logActivity(
      store,
      "mailbox.allocated",
      `${by} reserved ${address} for ${learner.name}.`,
      address,
      actor,
    );
    return { address, already: false };
  });

  if (!result) return respond("That student disappeared while you were allocating.");
  return respond(
    result.already
      ? `${result.address} was already reserved.`
      : `Reserved ${result.address}. Mail delivery starts once the mailbox exists on the mail server.`,
  );
}

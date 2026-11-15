import { cookies } from "next/headers";
import { SESSION_COOKIE, readSession } from "./session";
import { sessionIsLive } from "./login-sessions";
import { getDb } from "./store";
import { can, type StaffRole } from "./staff-policy";
import type { ActorRef, Staff } from "./types";

export async function currentStaff(): Promise<Staff | null> {
  const token = (await cookies()).get(SESSION_COOKIE)?.value;
  const session = await readSession(token);
  if (!session) return null;
  const db = getDb();
  // Signed correctly is not enough: the session must still be live in the registry.
  if (!sessionIsLive(db, session.sid)) return null;
  return db.staff.find((member) => member.id === session.staffId && !member.disabled) ?? null;
}

/** Registry id of the session this request came from, so the session list can mark it. */
export async function currentSessionId(): Promise<string | null> {
  const token = (await cookies()).get(SESSION_COOKIE)?.value;
  return (await readSession(token))?.sid ?? null;
}

export async function currentActor(): Promise<ActorRef | null> {
  const staff = await currentStaff();
  if (!staff) return null;
  return { id: staff.id, name: staff.name, email: staff.email, role: staff.role };
}

/** True when the signed-in member may perform the action; open console always may. */
export async function allowed(action: "publish" | "award" | "settings" | "staff"): Promise<boolean> {
  if (!process.env.AUTH_PASSWORD) return true;
  const staff = await currentStaff();
  return can(staff?.role as StaffRole | undefined, action);
}

import { getDb } from "@/lib/store";
import { fail, ok } from "@/lib/api";

export const dynamic = "force-dynamic";

export async function GET(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const db = getDb();
  const session = db.sessions.find((s) => s.id === id);
  if (!session) return fail("Generation session not found.", 404);
  return ok(session);
}

export async function DELETE(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const { mutate } = await import("@/lib/store");
  const removed = await mutate((db) => {
    const index = db.sessions.findIndex((s) => s.id === id);
    if (index < 0) return false;
    db.sessions.splice(index, 1);
    return true;
  });
  if (!removed) return fail("Generation session not found.", 404);
  return ok({ deleted: id });
}

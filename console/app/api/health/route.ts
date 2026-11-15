import { getDb } from "@/lib/store";
import { integrationHealth } from "@/lib/health";
import { ok } from "@/lib/api";

export const dynamic = "force-dynamic";

/** JSON health for monitoring; middleware still requires a session. */
export async function GET() {
  const db = getDb();
  const health = await integrationHealth(db.settings);
  return ok({
    healthy: health.healthy,
    signaraKey: health.window,
    checks: health.checks.map((check) => ({
      id: check.id,
      ok: check.ok,
      configured: check.configured,
      detail: check.detail,
      http: check.http,
    })),
    checkedAt: new Date().toISOString(),
  });
}

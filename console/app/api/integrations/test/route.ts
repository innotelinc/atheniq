import { getDb } from "@/lib/store";
import { probeSignara } from "@/lib/signara";
import { probeModel } from "@/lib/ai";
import { fail, ok, str } from "@/lib/api";

export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  const body = (await request.json().catch(() => ({}))) as { target?: string };
  const target = str(body.target);
  const db = getDb();

  if (target === "signara") {
    const probe = await probeSignara({ ...db.settings.signara, apiKey: db.settings.signara.apiKey });
    return ok({ target, ...probe });
  }

  if (target === "ai") {
    const probe = await probeModel(db.settings.ai);
    return ok({ target, ...probe });
  }

  if (target === "lms") {
    const base = db.settings.lms.baseUrl.replace(/\/+$/, "");
    if (!base) return fail("No LMS URL configured.");
    try {
      const response = await fetch(`${base}/api/courses/v1/courses/?page_size=1`, {
        headers: db.settings.lms.apiToken
          ? { Authorization: `Bearer ${db.settings.lms.apiToken}` }
          : {},
        signal: AbortSignal.timeout(10_000),
      });
      const text = await response.text();
      let count: number | null = null;
      try {
        const parsed = JSON.parse(text) as { results?: unknown[]; pagination?: { count?: number } };
        count = parsed.pagination?.count ?? parsed.results?.length ?? null;
      } catch {
        /* not JSON */
      }
      return ok({
        target,
        ok: response.ok,
        http: response.status,
        detail: response.ok
          ? `LMS catalog answered${count !== null ? ` — ${count} course(s)` : ""}.`
          : `LMS returned HTTP ${response.status}: ${text.slice(0, 180)}`,
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      return ok({ target, ok: false, http: 0, detail: `Could not reach ${base}: ${message}` });
    }
  }

  return fail("Unknown target. Use signara, ai or lms.");
}

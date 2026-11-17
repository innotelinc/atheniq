import { getDb } from "@/lib/store";
import { ok, preflight } from "@/lib/mobile-api";

export const dynamic = "force-dynamic";

/** What the app calls to check it is pointed at a real console. */
export async function GET() {
  const db = getDb();
  return ok({
    name: "AthenIQ",
    version: 1,
    brand: db.settings.brand.siteName,
    courses: db.courses.filter((course) => course.status === "published").length,
  });
}

export function OPTIONS() {
  return preflight();
}

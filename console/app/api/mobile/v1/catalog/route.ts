import { getDb } from "@/lib/store";
import { ok, preflight } from "@/lib/mobile-api";
import { catalogCard } from "@/lib/mobile-shape";

export const dynamic = "force-dynamic";

/**
 * The catalog, open to anyone — the same courses the public site lists.
 * Enrolling is what needs an account.
 */
export async function GET() {
  const db = getDb();
  const programNames = new Map(db.programs.map((program) => [program.id, program.name]));
  const trackNames = new Map(db.tracks.map((track) => [track.id, track.title]));

  const courses = db.courses
    .filter((course) => course.status === "published")
    .sort((a, b) => a.code.localeCompare(b.code))
    .map((course) => ({
      ...catalogCard(course, programNames),
      tracks: course.trackIds.map((id) => trackNames.get(id)).filter(Boolean),
    }));

  return ok({
    courses,
    programs: db.programs
      .filter((program) => program.status === "active")
      .map((program) => ({
        id: program.id,
        name: program.name,
        credential: program.credential,
        credits: program.totalCredits,
        tuitionPerCreditCents: program.tuitionPerCreditCents,
      })),
    brand: {
      name: db.settings.brand.siteName,
      tagline: db.settings.brand.tagline,
      accent: db.settings.brand.accent,
    },
  });
}

export function OPTIONS() {
  return preflight();
}

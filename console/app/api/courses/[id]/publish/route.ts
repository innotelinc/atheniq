import fs from "node:fs";
import { getDb, logActivity, mutate } from "@/lib/store";
import { currentActor } from "@/lib/current-staff";
import { buildManifest, pushToLms, writeBundle } from "@/lib/publish";
import { fail, ok } from "@/lib/api";
import type { Course, PublishManifest } from "@/lib/types";

export const dynamic = "force-dynamic";

interface Body {
  mode?: "validate" | "publish";
}

export async function POST(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const body = (await request.json().catch(() => ({}))) as Body;
  const mode = body.mode === "publish" ? "publish" : "validate";

  const actor = await currentActor();
  const db = getDb();
  const course = db.courses.find((c) => c.id === id);
  if (!course) return fail("Course not found.", 404);

  const manifest: PublishManifest = buildManifest(course, db);

  if (mode === "validate") {
    return ok({
      mode,
      manifest: { ...manifest, olxFiles: manifest.olxFiles.map((f) => ({ path: f.path, bytes: f.bytes })) },
      blocking: manifest.blocking,
      warnings: manifest.warnings,
    });
  }

  if (manifest.blocking.length) {
    return fail("This course cannot be published yet.", 422, {
      blocking: manifest.blocking,
      checks: manifest.checks,
    });
  }

  const bundle = writeBundle(course, manifest);
  const archive = fs.readFileSync(bundle.archivePath);
  const lms = await pushToLms(course, db.settings, archive);

  const updated = await mutate((database) => {
    const target = database.courses.find((c) => c.id === id) as Course;
    target.status = "published";
    target.publishedAt = new Date().toISOString();
    target.updatedAt = target.publishedAt;
    logActivity(
      database,
      "course.published",
      `Published ${target.code} — ${target.title.replace(`${target.code} — `, "")} to the catalog`,
      target.key,
      actor,
    );
    return target;
  });

  return ok({
    mode,
    course: updated,
    bundle: bundle.relativeDir,
    archive: `/api/courses/${id}/bundle`,
    lms,
    files: manifest.olxFiles.map((f) => ({ path: f.path, bytes: f.bytes })),
    checks: manifest.checks,
    listing: manifest.listing,
    catalogPatches: manifest.programPatches.length + manifest.trackPatches.length + 1,
  });
}

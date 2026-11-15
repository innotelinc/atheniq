import fs from "node:fs";
import path from "node:path";
import { getDb } from "@/lib/store";
import { buildManifest, buildOlx, tarGz } from "@/lib/publish";
import { fail } from "@/lib/api";

export const dynamic = "force-dynamic";

/** Download the importable OLX archive for a course. */
export async function GET(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const db = getDb();
  const course = db.courses.find((c) => c.id === id);
  if (!course) return fail("Course not found.", 404);

  const safe = `${course.code}-${course.term}`.replace(/[^A-Za-z0-9_-]/g, "");
  const bundlePath = path.join(process.cwd(), "data", "published", safe, `${course.code}-${course.term}.tar.gz`);

  let bytes: Buffer;
  if (fs.existsSync(bundlePath)) {
    bytes = fs.readFileSync(bundlePath);
  } else {
    const manifest = buildManifest(course, db);
    bytes = tarGz(manifest.olxFiles.map((f) => ({ path: f.path, content: f.content })));
  }

  return new Response(new Uint8Array(bytes), {
    headers: {
      "Content-Type": "application/gzip",
      "Content-Disposition": `attachment; filename="${course.code}-${course.term}.tar.gz"`,
      "Cache-Control": "no-store",
    },
  });
}

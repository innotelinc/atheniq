import { fail } from "@/lib/api";
import { transcriptFile } from "@/lib/applications";
import { currentStaff } from "@/lib/current-staff";
import { authEnabled } from "@/lib/session";
import { can } from "@/lib/staff-policy";
import { getDb } from "@/lib/store";

export const dynamic = "force-dynamic";

/**
 * The transcript an applicant uploaded, streamed to a registrar.
 *
 * Staff-only: this path is deliberately not on the middleware's public list, so
 * the console session (or the edge's own sign-on) has already refused a stranger
 * before the handler runs. The record decides which file is served — the URL
 * carries an application id, never a filename.
 */
export async function GET(
  _request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  if (authEnabled()) {
    const me = await currentStaff();
    if (!can(me?.role, "staff")) return fail("Only a registrar can read transcripts.", 403);
  }

  const { id } = await params;
  const application = getDb().applications.find((entry) => entry.id === id);
  if (!application?.transcript) return fail("That application has no transcript.", 404);

  const file = transcriptFile(application.transcript.storedAs);
  if (!file) return fail("The transcript file is missing from the server. Ask the applicant to send it again.", 410);

  const bytes = await import("node:fs").then((fs) => fs.readFileSync(file.path));
  const name = application.transcript.fileName.replace(/["\\\r\n]/g, "");

  return new Response(new Uint8Array(bytes), {
    headers: {
      "content-type": application.transcript.mimeType || "application/octet-stream",
      "content-length": String(bytes.length),
      "content-disposition": `attachment; filename="${name}"`,
      "cache-control": "private, no-store",
    },
  });
}

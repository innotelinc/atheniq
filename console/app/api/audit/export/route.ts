import { NextResponse } from "next/server";
import { fail } from "@/lib/api";
import { auditCsv, auditFileName } from "@/lib/audit";
import { allowed } from "@/lib/current-staff";
import { getDb } from "@/lib/store";

export const dynamic = "force-dynamic";

/**
 * The audit trail as CSV. `?staffId=` narrows it to one account — the same
 * view the per-person audit page shows, in a form a registrar can keep.
 */
export async function GET(request: Request) {
  if (!(await allowed("staff"))) {
    return fail("Only a registrar can export the audit trail.", 403);
  }
  const staffId = new URL(request.url).searchParams.get("staffId");
  const db = getDb();
  return new NextResponse(auditCsv(db, staffId), {
    headers: {
      "Content-Type": "text/csv; charset=utf-8",
      "Content-Disposition": `attachment; filename="${auditFileName(db, staffId)}"`,
      "Cache-Control": "no-store",
    },
  });
}

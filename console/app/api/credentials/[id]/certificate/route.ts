import fs from "node:fs";
import path from "node:path";
import { getDb } from "@/lib/store";
import { buildCertificatePdf } from "@/lib/signara";
import { fail } from "@/lib/api";

export const dynamic = "force-dynamic";

/** The certificate document, rendered when it was signed. */
export async function GET(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const db = getDb();
  const credential = db.credentials.find((c) => c.id === id);
  if (!credential) return fail("Credential not found.", 404);

  const file = path.join(process.cwd(), "data", "certificates", `${credential.verifyId}.pdf`);
  const bytes = fs.existsSync(file) ? fs.readFileSync(file) : buildCertificatePdf(credential);
  const download = new URL(request.url).searchParams.get("download") === "1";
  const safeName = `${credential.learner.name.replace(/[^A-Za-z0-9]+/g, "-")}-${credential.verifyId.slice(0, 8)}.pdf`;

  return new Response(new Uint8Array(bytes), {
    headers: {
      "Content-Type": "application/pdf",
      "Content-Disposition": `${download ? "attachment" : "inline"}; filename="${safeName}"`,
      "Cache-Control": "no-store",
    },
  });
}

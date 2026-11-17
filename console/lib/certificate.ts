import fs from "node:fs";
import path from "node:path";
import { getDb } from "./store";
import { buildCertificatePdf } from "./signara";

/**
 * The signed document behind a credential.
 *
 * Looked up the way the verification page looks it up — internal id, exact
 * verification id, or the opening characters of one — so the link printed on a
 * certificate resolves here too. When the rendered file is missing the PDF is
 * rebuilt from the record instead of failing, which is what happens after a
 * volume is recreated: the signature lives in the register, the file is only
 * its rendering.
 */
export function certificateResponse(reference: string, download: boolean): Response | null {
  const id = reference.trim();
  if (!id) return null;

  const db = getDb();
  const credential = db.credentials.find(
    (c) => c.id === id || c.verifyId === id || c.verifyId.startsWith(id),
  );
  if (!credential) return null;

  const file = path.join(process.cwd(), "data", "certificates", `${credential.verifyId}.pdf`);
  const bytes = fs.existsSync(file) ? fs.readFileSync(file) : buildCertificatePdf(credential);
  const safeName = `${credential.learner.name.replace(/[^A-Za-z0-9]+/g, "-")}-${credential.verifyId.slice(0, 8)}.pdf`;

  return new Response(new Uint8Array(bytes), {
    headers: {
      "Content-Type": "application/pdf",
      "Content-Disposition": `${download ? "attachment" : "inline"}; filename="${safeName}"`,
      "Cache-Control": "no-store",
    },
  });
}

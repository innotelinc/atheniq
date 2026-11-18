import fs from "node:fs";
import path from "node:path";
import { getDb } from "./store";
import { buildCertificatePdf } from "./signara";
import type { Credential } from "./types";

/**
 * The signed document behind a credential, and what may be handed over.
 *
 * One lookup for the verification page, the public document path and the staff
 * API, so the three cannot disagree about who is entitled to the file.
 *
 * A revoked award is withheld. The PDF is the artefact an employer files and a
 * licence board keeps, so revocation has to reach the thing they hold rather
 * than only the page they looked at: the register keeps the record, and the
 * signed file stops being served while the revocation stands. Staff still see
 * the record and its reason; nobody downloads the certificate.
 */
export type CertificateLookup =
  | { kind: "document"; credential: Credential; response: Response }
  | { kind: "revoked"; credential: Credential }
  | { kind: "missing" };

export function lookupCredential(reference: string): Credential | undefined {
  const id = reference.trim();
  if (!id) return undefined;
  return getDb().credentials.find(
    (c) => c.id === id || c.verifyId === id || c.verifyId.startsWith(id),
  );
}

export function certificateDocument(reference: string, download: boolean): CertificateLookup {
  const credential = lookupCredential(reference);
  if (!credential) return { kind: "missing" };
  if (credential.status === "revoked") return { kind: "revoked", credential };

  const file = path.join(process.cwd(), "data", "certificates", `${credential.verifyId}.pdf`);
  const bytes = fs.existsSync(file) ? fs.readFileSync(file) : buildCertificatePdf(credential);
  const safeName = `${credential.learner.name.replace(/[^A-Za-z0-9]+/g, "-")}-${credential.verifyId.slice(0, 8)}.pdf`;

  const response = new Response(new Uint8Array(bytes), {
    headers: {
      "Content-Type": "application/pdf",
      "Content-Disposition": `${download ? "attachment" : "inline"}; filename="${safeName}"`,
      "Cache-Control": "no-store",
    },
  });

  return { kind: "document", credential, response };
}

/** The answer when there is no file to give: 404 for an unknown id, 410 for a revoked award. */
export function withheldResponse(lookup: CertificateLookup): Response | null {
  if (lookup.kind === "missing") {
    return new Response("No credential matches that verification id.\n", {
      status: 404,
      headers: { "Content-Type": "text/plain; charset=utf-8" },
    });
  }
  if (lookup.kind === "revoked") {
    const reason = lookup.credential.revokeReason ? ` Reason: ${lookup.credential.revokeReason}.` : "";
    return new Response(
      `This credential was revoked, so its signed document is no longer issued.${reason}\n` +
        `The register record is the check: https://${process.env.PUBLIC_SITE_DOMAIN || "atheniq.institute"}/verify/${lookup.credential.verifyId}\n`,
      { status: 410, headers: { "Content-Type": "text/plain; charset=utf-8" } },
    );
  }
  return null;
}

/** True when the register says this award still stands. */
export function credentialStands(credential: Credential): boolean {
  return credential.status === "issued" || credential.status === "signed";
}

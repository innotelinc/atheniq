import { createHash } from "node:crypto";
import type { Credential, Settings } from "./types";

/* ------------------------------------------------------------------ */
/* PDF — a minimal, dependency-free certificate renderer               */
/* ------------------------------------------------------------------ */

function pdfText(value: string): string {
  return value
    .replace(/[\u2018\u2019]/g, "'")
    .replace(/[\u201C\u201D]/g, '"')
    .replace(/[\u2013\u2014]/g, "-")
    .replace(/[^\x20-\x7E]/g, "")
    .replace(/([\\()])/g, "\\$1");
}

interface Line {
  text: string;
  font: "F1" | "F2" | "F3";
  size: number;
  y: number;
  align?: "center" | "left";
  x?: number;
}

function textWidth(text: string, size: number, font: Line["font"]): number {
  // Helvetica advance widths average ~0.5em; bold runs a little wider.
  const factor = font === "F1" ? 0.55 : 0.5;
  return text.length * size * factor;
}

function wrap(text: string, size: number, font: Line["font"], maxWidth: number): string[] {
  const words = text.split(/\s+/);
  const lines: string[] = [];
  let current = "";
  for (const word of words) {
    const candidate = current ? `${current} ${word}` : word;
    if (textWidth(candidate, size, font) > maxWidth && current) {
      lines.push(current);
      current = word;
    } else {
      current = candidate;
    }
  }
  if (current) lines.push(current);
  return lines;
}

/** Build a single-page A4-landscape PDF certificate. */
export function buildCertificatePdf(credential: Credential): Buffer {
  const isDegree = credential.type === "degree_conferral";
  const heading = isDegree ? "CERTIFICATE OF DEGREE CONFERRAL" : credential.type === "track_credential" ? "CERTIFICATE OF TRACK COMPLETION" : "CERTIFICATE OF COMPLETION";

  const lines: Line[] = [];
  const cx = 421;

  lines.push({ text: "ATHENIQ INSTITUTE", font: "F1", size: 12, y: 505, align: "center" });
  lines.push({ text: "An online university from Innotel Labs", font: "F3", size: 9, y: 488, align: "center" });
  lines.push({ text: heading, font: "F1", size: 20, y: 440, align: "center" });
  lines.push({ text: "This certifies that", font: "F2", size: 11, y: 400, align: "center" });
  lines.push({ text: credential.learner.name, font: "F1", size: 30, y: 355, align: "center" });

  const subject = credential.subjectLabel;
  const body = isDegree
    ? `has completed all requirements of the ${subject} and is hereby awarded the degree,`
    : `has successfully completed ${subject},`;
  wrap(body, 11, "F2", 620).forEach((line, i) => {
    lines.push({ text: line, font: "F2", size: 11, y: 315 - i * 16, align: "center" });
  });

  const detail = [
    credential.evidence.grade ? `Grade: ${credential.evidence.grade}` : null,
    credential.evidence.credits ? `Credits: ${credential.evidence.credits}` : null,
    credential.evidence.gpa ? `GPA: ${credential.evidence.gpa}` : null,
    `Completed: ${credential.evidence.completedOn ?? new Date(credential.createdAt).toISOString().slice(0, 10)}`,
  ]
    .filter(Boolean)
    .join("   |   ");
  lines.push({ text: detail, font: "F2", size: 10, y: 268, align: "center" });

  lines.push({ text: "Signed through Signara - verifiable at the source.", font: "F3", size: 9, y: 236, align: "center" });
  lines.push({ text: `Verification ID: ${credential.verifyId}`, font: "F2", size: 9, y: 220, align: "center" });

  lines.push({ text: "______________________________", font: "F2", size: 11, y: 150, x: 190 });
  lines.push({ text: credential.signer.name, font: "F1", size: 11, y: 132, x: 190 });
  lines.push({ text: credential.signer.title, font: "F2", size: 9, y: 119, x: 190 });
  lines.push({ text: credential.signer.email, font: "F2", size: 9, y: 107, x: 190 });

  lines.push({ text: "Evidence hash", font: "F1", size: 8, y: 150, x: 470 });
  wrap(credential.hash, 7, "F2", 300).forEach((line, i) => {
    lines.push({ text: line, font: "F2", size: 7, y: 138 - i * 9, x: 470 });
  });

  const content: string[] = [
    // outer frame + brand rule
    "0.02 0.42 0.29 RG 2 w 24 24 794 547 re S",
    "0.20 0.83 0.60 RG 2 w 24 500 794 3 re f",
  ];
  for (const line of lines) {
    const x = line.align === "center" ? cx - textWidth(line.text, line.size, line.font) / 2 : (line.x ?? 60);
    content.push(`BT /${line.font} ${line.size} Tf 0.06 0.09 0.13 rg 1 0 0 1 ${x.toFixed(1)} ${line.y} Tm (${pdfText(line.text)}) Tj ET`);
  }
  const stream = content.join("\n");

  const objects: string[] = [
    "<< /Type /Catalog /Pages 2 0 R >>",
    "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 842 595] /Resources << /Font << /F1 4 0 R /F2 5 0 R /F3 6 0 R >> >> /Contents 7 0 R >>",
    "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>",
    "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
    "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Oblique /Encoding /WinAnsiEncoding >>",
    `<< /Length ${Buffer.byteLength(stream, "latin1")} >>\nstream\n${stream}\nendstream`,
  ];

  let pdf = "%PDF-1.4\n";
  const offsets: number[] = [];
  objects.forEach((body, i) => {
    offsets.push(Buffer.byteLength(pdf, "latin1"));
    pdf += `${i + 1} 0 obj\n${body}\nendobj\n`;
  });
  const xrefOffset = Buffer.byteLength(pdf, "latin1");
  pdf += `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n`;
  for (const offset of offsets) {
    pdf += `${offset.toString().padStart(10, "0")} 00000 n \n`;
  }
  pdf += `trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xrefOffset}\n%%EOF\n`;

  return Buffer.from(pdf, "latin1");
}

/* ------------------------------------------------------------------ */
/* Signara — the DocumentOps signing workflow                          */
/* ------------------------------------------------------------------ */

export function evidenceHash(credential: Omit<Credential, "hash">): string {
  const canonical = JSON.stringify({
    verifyId: credential.verifyId,
    type: credential.type,
    title: credential.title,
    subject: credential.subjectRef,
    learner: credential.learner,
    evidence: credential.evidence,
    template: credential.template,
    signer: credential.signer,
  });
  return createHash("sha256").update(canonical).digest("hex");
}

interface SignaraResponse {
  status: number;
  body: Record<string, unknown> | null;
  error: string | null;
}

async function signaraFetch(
  settings: Settings["signara"],
  method: string,
  path: string,
  body?: BodyInit,
  contentType?: string,
  timeoutMs = 45_000,
): Promise<SignaraResponse> {
  const base = settings.baseUrl.replace(/\/+$/, "");
  const headers: Record<string, string> = { "X-API-Key": settings.apiKey };
  if (contentType) headers["Content-Type"] = contentType;
  try {
    const response = await fetch(`${base}${path}`, {
      method,
      headers,
      body,
      signal: AbortSignal.timeout(timeoutMs),
    });
    const text = await response.text();
    let parsed: Record<string, unknown> | null = null;
    try {
      parsed = text ? (JSON.parse(text) as Record<string, unknown>) : null;
    } catch {
      parsed = { raw: text.slice(0, 300) };
    }
    return {
      status: response.status,
      body: parsed,
      error: response.ok ? null : `HTTP ${response.status}: ${text.slice(0, 200)}`,
    };
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    return { status: 0, body: null, error: `Signara unreachable: ${message}` };
  }
}

function multipart(
  fields: Record<string, string>,
  file: { name: string; type: string; bytes: Buffer },
): { body: Buffer; contentType: string } {
  const boundary = `----atheniq${Date.now().toString(16)}`;
  const parts: Buffer[] = [];
  for (const [key, value] of Object.entries(fields)) {
    parts.push(
      Buffer.from(
        `--${boundary}\r\nContent-Disposition: form-data; name="${key}"\r\n\r\n${value}\r\n`,
        "utf8",
      ),
    );
  }
  parts.push(
    Buffer.from(
      `--${boundary}\r\nContent-Disposition: form-data; name="file"; filename="${file.name}"\r\nContent-Type: ${file.type}\r\n\r\n`,
      "utf8",
    ),
  );
  parts.push(file.bytes);
  parts.push(Buffer.from(`\r\n--${boundary}--\r\n`, "utf8"));
  return { body: Buffer.concat(parts), contentType: `multipart/form-data; boundary=${boundary}` };
}

export interface SignResult {
  status: "signed" | "partial" | "failed" | "queued_local";
  signara: Credential["signara"];
  timeline: { at: string; label: string; detail?: string }[];
  error: string | null;
  pdf: Buffer;
}

/**
 * Run the full AthenIQ → Signara flow for one award:
 * upload the rendered certificate, open the signing request, and — when
 * auto-sign is on — apply the issuer's typed signature.
 */
export async function submitToSignara(
  credential: Credential,
  settings: Settings["signara"],
): Promise<SignResult> {
  const now = () => new Date().toISOString();
  const pdf = buildCertificatePdf(credential);
  const timeline: { at: string; label: string; detail?: string }[] = [];
  const record: Credential["signara"] = {
    documentId: null,
    requestId: null,
    signerToken: null,
    apiBase: null,
    lastHttp: null,
    lastError: null,
  };

  if (!settings.apiKey) {
    timeline.push({
      at: now(),
      label: "Held locally — Signara is not configured",
      detail: "Set SIGNARA_API_KEY in Integrations to submit this award for signing.",
    });
    return { status: "queued_local", signara: record, timeline, error: null, pdf };
  }

  record.apiBase = settings.baseUrl;

  const title = credential.title;
  const description = `${credential.type.replace(/_/g, " ")} — ${credential.subjectLabel} (${credential.learner.name} <${credential.learner.email}>). Verify id ${credential.verifyId}.`;

  const upload = multipart(
    { title, description },
    { name: `atheniq-${credential.verifyId}.pdf`, type: "application/pdf", bytes: pdf },
  );
  const uploaded = await signaraFetch(
    settings,
    "POST",
    "/api/v1/documents/upload",
    new Uint8Array(upload.body),
    upload.contentType,
    90_000,
  );
  record.lastHttp = uploaded.status;
  if (uploaded.status >= 300 || !uploaded.body) {
    record.lastError = uploaded.error;
    timeline.push({ at: now(), label: "Document upload failed", detail: uploaded.error ?? "" });
    return { status: "failed", signara: record, timeline, error: uploaded.error, pdf };
  }
  record.documentId = String(uploaded.body.id ?? "");
  timeline.push({ at: now(), label: "Document uploaded", detail: record.documentId });

  const request = await signaraFetch(settings, "POST", "/api/v1/signatures/requests", JSON.stringify({
    documentId: record.documentId,
    title,
    message: description,
    mode: "SEQUENTIAL",
    sendInvites: false,
    signers: [
      {
        email: credential.signer.email || settings.baseUrl,
        name: credential.signer.name,
        role: "SIGNER",
        orderIndex: 0,
      },
    ],
  }), "application/json");
  record.lastHttp = request.status;
  if (request.status >= 300 || !request.body) {
    record.lastError = request.error;
    timeline.push({ at: now(), label: "Signing request failed", detail: request.error ?? "" });
    return { status: "partial", signara: record, timeline, error: request.error, pdf };
  }
  record.requestId = String(request.body.id ?? "");
  timeline.push({ at: now(), label: "Signing request created", detail: record.requestId });

  const signers = (request.body.signers as { token?: string }[] | undefined) ?? [];
  let token = signers[0]?.token ?? null;
  if (!token) {
    const fetched = await signaraFetch(settings, "GET", `/api/v1/signatures/requests/${record.requestId}`);
    const refreshed = (fetched.body?.signers as { token?: string }[] | undefined) ?? [];
    token = refreshed[0]?.token ?? null;
  }
  if (!token) {
    record.lastError = "Signara returned no signer token for the request.";
    timeline.push({ at: now(), label: "Awaiting signer token", detail: record.requestId });
    return { status: "partial", signara: record, timeline, error: record.lastError, pdf };
  }
  record.signerToken = token;

  if (!settings.autoSign) {
    timeline.push({ at: now(), label: "Awaiting signature", detail: "Auto-sign is off — sign in Signara." });
    return { status: "partial", signara: record, timeline, error: null, pdf };
  }

  const signed = await signaraFetch(
    settings,
    "POST",
    `/api/v1/signatures/public/${token}/sign`,
    JSON.stringify({ type: "TYPED", signatureData: credential.signer.name }),
    "application/json",
  );
  record.lastHttp = signed.status;
  if (signed.status >= 300) {
    record.lastError = signed.error;
    timeline.push({ at: now(), label: "Signature rejected", detail: signed.error ?? "" });
    return { status: "partial", signara: record, timeline, error: signed.error, pdf };
  }

  timeline.push({
    at: now(),
    label: `Signed by ${credential.signer.name}`,
    detail: "TYPED signature applied through Signara",
  });
  return { status: "signed", signara: record, timeline, error: null, pdf };
}

export interface SignaraProbe {
  ok: boolean;
  detail: string;
  http: number | null;
}

export async function probeSignara(settings: Settings["signara"]): Promise<SignaraProbe> {
  if (!settings.baseUrl) return { ok: false, detail: "No Signara base URL configured.", http: null };
  if (!settings.apiKey)
    return { ok: false, detail: "No API key configured — awards are held locally until one is set.", http: null };
  const result = await signaraFetch(settings, "GET", "/api/v1/signatures/requests?limit=1", undefined, undefined, 8000);
  if (result.status === 0) return { ok: false, detail: result.error ?? "Unreachable", http: 0 };
  if (result.status === 401 || result.status === 403)
    return { ok: false, detail: `Signara rejected the API key (HTTP ${result.status}).`, http: result.status };
  if (result.status === 404)
    return { ok: true, detail: "Signara reachable (this build answers a different route list).", http: 404 };
  return {
    ok: result.status < 300,
    detail: result.status < 300 ? `Signara reachable (HTTP ${result.status}).` : result.error ?? `HTTP ${result.status}`,
    http: result.status,
  };
}

import Link from "next/link";
import { notFound } from "next/navigation";
import { getDb } from "@/lib/store";
import { dateTime, shortDate } from "@/lib/format";
import { Badge, Card, Crumbs, Topbar } from "@/components/ui";
import { CredentialActions } from "@/components/CredentialActions";
import { credentialStands } from "@/lib/certificate";

export const dynamic = "force-dynamic";

export default async function CredentialPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const db = getDb();
  const credential = db.credentials.find((c) => c.id === id);
  if (!credential) notFound();

  return (
    <>
      <Topbar>
        <Crumbs items={[{ label: "Credentials", href: "/credentials" }, { label: credential.verifyId.slice(0, 8) }]} />
        <div className="row">
          {credentialStands(credential) && (
            <a className="btn small" href={`/api/credentials/${credential.id}/certificate?download=1`}>
              Download PDF
            </a>
          )}
          <Link className="btn small ghost" href={`/verify/${credential.verifyId}`}>
            Public verification
          </Link>
        </div>
      </Topbar>

      <div className="content">
        <div className="hero">
          <div className="between" style={{ alignItems: "flex-start" }}>
            <div>
              <div className="eyebrow">{credential.type.replace(/_/g, " ")}</div>
              <h1 className="page-title" style={{ fontSize: 25 }}>{credential.subjectLabel}</h1>
              <p className="page-sub">
                {credential.learner.name} · {credential.learner.email} · awarded {shortDate(credential.createdAt)}
              </p>
            </div>
            <Badge status={credential.status} />
          </div>
          <div className="hero-meta">
            <span className="chip plain mono">verify {credential.verifyId}</span>
            <span className="chip plain">{credential.template}</span>
            {credential.evidence.grade && <span className="chip plain">grade {credential.evidence.grade}</span>}
            {credential.evidence.credits && <span className="chip plain">{credential.evidence.credits} credits</span>}
            {credential.evidence.gpa && <span className="chip plain">GPA {credential.evidence.gpa}</span>}
          </div>
        </div>

        <div className="split mt">
          <div className="stack">
            <Card title="Certificate document" subtitle="The exact PDF submitted to Signara for signing.">
              <div className="card-body">
                {credentialStands(credential) ? (
                  <iframe
                    title="Certificate PDF"
                    src={`/api/credentials/${credential.id}/certificate`}
                    style={{ width: "100%", height: 520, border: "1px solid var(--line)", borderRadius: 10, background: "#fff" }}
                  />
                ) : (
                  <p className="small muted">
                    {credential.status === "revoked"
                      ? "Withheld: the signed file stops being served while the revocation stands, so a revoked award cannot keep circulating as a document. It remains in the register below."
                      : "Nothing to show yet: the document exists once the award is signed."}
                  </p>
                )}
              </div>
            </Card>

            <Card title="Signara ledger" subtitle="Document, request and signature for this award.">
              <div className="card-body stack-sm small">
                <Row label="API base" value={<span className="mono">{credential.signara.apiBase ?? "—"}</span>} />
                <Row label="Document id" value={<span className="mono">{credential.signara.documentId ?? "—"}</span>} />
                <Row label="Request id" value={<span className="mono">{credential.signara.requestId ?? "—"}</span>} />
                <Row label="Last HTTP" value={credential.signara.lastHttp ?? "—"} />
                <Row label="Signed" value={credential.signedAt ? dateTime(credential.signedAt) : "Not yet"} />
                <Row label="Issued" value={credential.issuedAt ? dateTime(credential.issuedAt) : "Not yet"} />
                {credential.signara.lastError && (
                  <div className="banner bad">
                    <div>{credential.signara.lastError}</div>
                  </div>
                )}
                <Row label="Signatory" value={`${credential.signer.name} · ${credential.signer.title}`} />
              </div>
            </Card>

            <Card title="Evidence">
              <div className="card-body stack-sm small">
                <Row label="Evidence hash" value={<span className="mono tiny">{credential.hash}</span>} />
                <Row label="Subject" value={<span className="mono">{credential.subjectRef}</span>} />
                {credential.evidence.completedOn && <Row label="Completed" value={credential.evidence.completedOn} />}
                {credential.evidence.program && <Row label="Program" value={credential.evidence.program} />}
                {credential.evidence.courses && credential.evidence.courses.length > 0 && (
                  <div>
                    <div className="label">Course evidence</div>
                    <div className="stack-sm" style={{ marginTop: 4 }}>
                      {credential.evidence.courses.map((course) => (
                        <span key={course} className="mono tiny">
                          {course}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </Card>
          </div>

          <div className="stack">
            <CredentialActions credential={credential} />

            <Card title="Timeline">
              <div className="card-body">
                <div className="timeline">
                  {credential.timeline
                    .slice()
                    .sort((a, b) => a.at.localeCompare(b.at))
                    .map((event, i) => (
                      <div className="tl-item" key={`${event.at}-${i}`}>
                        <span className={`tl-dot${event.label.toLowerCase().includes("held") ? " muted" : ""}`} />
                        <div>
                          <div className="small strong">{event.label}</div>
                          {event.detail && <div className="tiny muted">{event.detail}</div>}
                          <div className="tiny muted">{dateTime(event.at)}</div>
                        </div>
                      </div>
                    ))}
                </div>
              </div>
            </Card>

            {credential.status === "revoked" && (
              <Card title="Revoked">
                <div className="card-body small">
                  <p>{credential.revokeReason}</p>
                  <p className="muted" style={{ marginTop: 6 }}>
                    The public verification page reports this revocation and no signature file is served; the
                    register keeps the record and the document for the audit trail.
                  </p>
                </div>
              </Card>
            )}
          </div>
        </div>
      </div>
    </>
  );
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="between">
      <span className="muted">{label}</span>
      <span>{value}</span>
    </div>
  );
}

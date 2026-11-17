import Link from "next/link";
import { getDb } from "@/lib/store";
import { shortDate } from "@/lib/format";
import { currentStaff } from "@/lib/current-staff";
import { Badge, Card, PageHead, Topbar, Crumbs } from "@/components/ui";

export const dynamic = "force-dynamic";

export const metadata = { title: "Credential verification — AthenIQ" };

export default async function VerifyResultPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const db = getDb();
  // The registrar's own view of this record is behind the console session.
  // A visitor checking a certificate has no account, so the link is left out
  // rather than handed over as a sign-in wall.
  const staff = await currentStaff();
  const credential = db.credentials.find(
    (c) => c.verifyId === id || c.id === id || c.verifyId.startsWith(id),
  );

  const valid = Boolean(credential && ["issued", "signed"].includes(credential.status));

  return (
    <>
      <Topbar>
        <Crumbs items={[{ label: "Verification", href: "/verify" }, { label: id.slice(0, 10) }]} />
        <Link className="btn small ghost" href="/verify">
          Check another
        </Link>
      </Topbar>

      <div className="content">
        {!credential ? (
          <Card>
            <div className="card-body">
              <PageHead
                title="No credential found"
                subtitle={`Nothing in the register matches “${id}”. Check the verification id printed on the document.`}
              />
            </div>
          </Card>
        ) : (
          <>
            <PageHead
              eyebrow="Verification result"
              title={valid ? "Credential is valid" : credential.status === "revoked" ? "Credential was revoked" : "Credential is not yet issued"}
              subtitle={`${credential.subjectLabel} — awarded to ${credential.learner.name}.`}
              actions={<Badge status={credential.status} />}
            />

            <div className="split">
              <Card title="Award record">
                <div className="card-body stack-sm small">
                  <Row label="Verification id" value={<span className="mono">{credential.verifyId}</span>} />
                  <Row label="Credential" value={credential.subjectLabel} />
                  <Row label="Type" value={credential.type.replace(/_/g, " ")} />
                  <Row label="Learner" value={credential.learner.name} />
                  <Row label="Issued" value={credential.issuedAt ? shortDate(credential.issuedAt) : "Not issued"} />
                  {credential.evidence.grade && <Row label="Grade" value={credential.evidence.grade} />}
                  {credential.evidence.credits && <Row label="Credits" value={String(credential.evidence.credits)} />}
                  {credential.evidence.gpa && <Row label="GPA" value={credential.evidence.gpa} />}
                  {credential.evidence.completedOn && <Row label="Completed" value={credential.evidence.completedOn} />}
                  <Row label="Signed by" value={`${credential.signer.name} · ${credential.signer.title}`} />
                  <Row label="Evidence hash" value={<span className="mono tiny">{credential.hash}</span>} />
                  {credential.status === "revoked" && (
                    <div className="banner bad">
                      <div>
                        <div className="banner-title">Revoked {shortDate(credential.revokedAt)}</div>
                        {credential.revokeReason}
                      </div>
                    </div>
                  )}
                </div>
              </Card>

              <Card title="What this check proves">
                <div className="card-body small stack-sm">
                  <p className="muted">
                    The award was rendered by AthenIQ, signed through Signara by the institution&apos;s signatory,
                    and issued to the learner record. The evidence hash binds the certificate to the completion
                    data it was signed over.
                  </p>
                  <a className="btn" href={`/api/credentials/${credential.id}/certificate?download=1`}>
                    Download the signed PDF
                  </a>
                  {staff ? (
                    <Link className="btn ghost" href={`/credentials/${credential.id}`}>
                      Registrar view
                    </Link>
                  ) : null}
                </div>
              </Card>
            </div>
          </>
        )}
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
